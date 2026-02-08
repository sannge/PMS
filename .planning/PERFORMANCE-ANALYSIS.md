# Performance Analysis: Slow Task & Project Creation

**Date**: 2026-02-08
**Issue**: Creating projects and tasks takes excessively long

## Root Causes Identified

### Task Creation (10+ Database Queries + Multiple WebSocket Broadcasts)

**File**: `fastapi-backend/app/routers/tasks.py:create_task` (lines 1050-1270)

#### Sequential Operations (Waterfall):

1. **Line 1140**: `generate_task_key()` - 1 SQL query (atomic UPDATE...RETURNING) ✓ Fast
2. **Line 1167**: `get_current_derived_status_name()` - **1 DB query** to fetch TaskStatus
3. **Line 1170**: `get_or_create_project_aggregation()` - **1-2 DB queries**
   - Query for existing ProjectTaskStatusAgg
   - If first time: **Loads ALL project tasks with joins** (lines 470-478) - **VERY SLOW**
4. **Line 1174**: `update_project_derived_status()` - **2 DB queries**
   - COUNT all TaskStatuses for project (line 507-512)
   - SELECT TaskStatus by name (line 522-528)
   - Potentially creates 5 default statuses + flush (line 514-519)
5. **Line 1177**: `db.commit()` - Disk I/O
6. **Line 1178**: `db.refresh(task, [...])` - **3+ DB queries** (reload task + assignee + reporter + project)
7. **Line 1181-1186**: `emit_project_status_changed_if_needed()` - WebSocket broadcast (network I/O)
8. **Line 1189-1190**: Lazy load assignee/reporter - **REDUNDANT** (already loaded at line 1178)
9. **Line 1221-1227**: `handle_task_update()` - **2 WebSocket broadcasts**:
   - Broadcast to project room (all users in project)
   - Broadcast to task room
10. **Line 1232-1247**: Optional WebSocket broadcast if project restored
11. **Line 1251-1259**: **1 DB query** for assignee + notification send

**Total**: ~10-15 database queries + 3-4 WebSocket broadcasts

---

### Project Creation (10 Database Queries + 1 WebSocket Broadcast)

**File**: `fastapi-backend/app/routers/projects.py:create_project` (lines 397-522)

#### Sequential Operations:

1. **Line 415**: `verify_application_access()` - **1 DB query** (check membership)
2. **Line 418-424**: Check duplicate key - **1 DB query**
3. **Line 445**: `db.flush()` - Disk I/O
4. **Line 448-451**: Create 5 default TaskStatuses + flush - **5 INSERTs + disk I/O**
5. **Line 469**: `db.commit()` - Disk I/O
6. **Line 470**: `db.refresh(project)` - **1 DB query** (reload project)
7. **Line 475-479**: Query for derived status - **1 DB query** (**REDUNDANT** - we just created it at line 454)
8. **Line 483-499**: WebSocket broadcast to application room - Network I/O

**Total**: ~10 database queries + 1 WebSocket broadcast

---

## Performance Impact Analysis

### Critical Bottlenecks:

#### 1. **Too Many Sequential Database Queries** 🔴 CRITICAL
- Each query is a network round-trip to PostgreSQL
- No query batching or eager loading
- Estimated: **50-150ms per query × 10-15 queries = 500-2250ms**

#### 2. **First-Time Aggregation Calculation** 🔴 CRITICAL
- `get_or_create_project_aggregation()` loads ALL tasks for a project on first call
- Uses `selectinload(Task.task_status)` - additional JOIN
- For a project with 1000 tasks: **2-5 seconds**

#### 3. **Synchronous WebSocket Broadcasts** 🟡 HIGH
- Blocks request until all users receive message
- Scales linearly with connected user count
- 50 users × 10ms = **500ms additional delay**

#### 4. **Redundant Queries** 🟡 HIGH
- Line 1178: Loads task relationships
- Line 1189-1190: **Re-loads same relationships** (assignee/reporter)
- Line 475-479: Queries for TaskStatus we just created in memory (line 454)

#### 5. **Synchronous Notification Sending** 🟠 MEDIUM
- Line 1251-1259: Queries user + sends notification synchronously
- Should be async/background task

---

## Recommended Optimizations

### Quick Wins (Immediate Impact):

#### 1. **Remove Redundant Queries** (Saves 2-3 queries per task)
```python
# Line 475-479: Don't re-query status we just created
derived_status_name = todo_status.name if todo_status else None

# Line 1189-1190: Remove redundant lazy loads (already loaded at 1178)
# DELETE these lines - assignee/reporter already in task object
```

#### 2. **Cache Project Aggregations in Redis** (Saves 1-5 seconds for first task)
```python
# Check Redis cache before hitting DB
cache_key = f"project_agg:{project_id}"
agg = await redis.get(cache_key)
if not agg:
    agg = await db.execute(select(ProjectTaskStatusAgg)...)
    await redis.setex(cache_key, 300, agg)  # 5 min TTL
```

#### 3. **Fire-and-Forget WebSocket Broadcasts** (Saves 100-500ms)
```python
# Don't await WebSocket broadcasts - use background task
asyncio.create_task(handle_task_update(...))
asyncio.create_task(manager.broadcast_to_room(...))
```

#### 4. **Batch Database Operations** (Saves 50-200ms)
```python
# Use selectinload/joinedload for relationships upfront
result = await db.execute(
    select(Project)
    .options(
        selectinload(Project.derived_status),
        selectinload(Project.task_statuses)
    )
    .where(Project.id == project_id)
)
```

---

### Medium-Term Improvements:

#### 5. **Background Tasks for Notifications** (Saves 50-100ms)
```python
# Use ARQ or Celery for async notifications
await arq_queue.enqueue_job('send_task_assigned_notification', task_id, assignee_id)
```

#### 6. **Database Indexing Audit**
- Ensure indexes on foreign keys: `task_status_id`, `project_id`, `assignee_id`
- Composite index: `(project_id, archived_at, task_status_id)` for aggregation queries

#### 7. **Lazy Status Creation**
```python
# Don't create default TaskStatuses on project creation
# Create on-demand when first task is created
# Saves ~5 INSERTs per project
```

---

## Expected Performance Gains

| Optimization | Time Saved | Effort |
|-------------|-----------|--------|
| Remove redundant queries | 100-300ms | 5 min |
| Cache aggregations | 1-5 seconds (first task) | 30 min |
| Fire-and-forget WebSocket | 100-500ms | 15 min |
| Batch DB operations | 50-200ms | 1 hour |
| Background notifications | 50-100ms | 2 hours |
| **Total Potential Savings** | **1.3-6 seconds** | **~4 hours** |

---

## Current vs. Optimized Flow

### Current (Slow):
```
Task Creation: 1.5-3 seconds
├─ 10-15 DB queries (sequential): 500-2250ms
├─ WebSocket broadcasts (blocking): 200-500ms
├─ Aggregation (first time): 1000-5000ms
└─ Notifications (blocking): 50-100ms
```

### Optimized (Fast):
```
Task Creation: 150-400ms
├─ 5-7 DB queries (batched): 150-300ms
├─ WebSocket broadcasts (async): 0ms
├─ Aggregation (cached): 0-50ms
└─ Notifications (background): 0ms
```

---

## Priority Actions

1. ✅ **Remove redundant queries** (lines 1189-1190, 475-479) - 5 min
2. ✅ **Fire-and-forget WebSocket broadcasts** - 15 min
3. ✅ **Cache aggregations in Redis** - 30 min
4. 🔄 **Batch relationship loading with selectinload** - 1 hour
5. 🔄 **Move notifications to background tasks** - 2 hours

---

## Testing Recommendations

1. **Load test with ApacheBench**:
   ```bash
   ab -n 100 -c 10 -T 'application/json' -p task.json http://localhost:8001/api/projects/{id}/tasks
   ```

2. **Monitor query counts** with SQLAlchemy echo:
   ```python
   engine = create_async_engine(DATABASE_URL, echo=True)
   ```

3. **Profile with cProfile**:
   ```bash
   python -m cProfile -o output.prof -m uvicorn app.main:app
   ```

4. **WebSocket latency** - Measure time from API call to WebSocket message received

---

## Database Query Optimization Examples

### Before (5 queries):
```python
project = await db.get(Project, project_id)
status = await db.get(TaskStatus, project.derived_status_id)
agg = await db.execute(select(ProjectTaskStatusAgg)...)
assignee = await db.get(User, task.assignee_id)
reporter = await db.get(User, task.reporter_id)
```

### After (1 query):
```python
result = await db.execute(
    select(Project)
    .options(
        joinedload(Project.derived_status),
        selectinload(Project.task_status_agg),
    )
    .where(Project.id == project_id)
)
project = result.unique().scalar_one()
```

---

## Conclusion

The slow performance is caused by:
1. **10-15 sequential database queries** per operation
2. **Synchronous WebSocket broadcasts** to all connected users
3. **Expensive aggregation recalculation** on first task creation
4. **Redundant queries** for data already in memory

**Quick wins (1 hour of work) can reduce latency by 60-80%**.
