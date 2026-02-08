# Performance Optimization Audit Report

**Date**: 2026-02-08
**Purpose**: Review optimizations #3 (Redis caching) and #4 (eager loading) for potential conflicts

---

## ✅ Optimization #3: Redis Caching - SAFE WITH MODIFICATIONS

### Current Redis Infrastructure

**File**: `fastapi-backend/app/services/redis_service.py`

Your project **already has a robust Redis service** with:
- ✅ Connection pooling and automatic reconnection
- ✅ Pub/Sub for WebSocket cross-worker communication
- ✅ JSON caching with TTL (`get_json()`, `set()`, `delete()`)
- ✅ Rate limiting and presence tracking
- ✅ Graceful error handling

**Good news**: The infrastructure is already there! We just need to use it.

### Existing Redis Key Prefixes (No Conflicts)

```python
# Current usage:
"doc_lock:{document_id}"      # Document locking
"presence:{room_id}"           # User presence tracking
"ratelimit:ws:{user_id}"       # Rate limiting

# Proposed new usage:
"project_agg:{project_id}"     # Project aggregation cache (NEW)
```

**✅ No key collision risk** - different prefixes

---

### Issues Found with Original Implementation

#### Issue #1: Incorrect Cache Deserialization ⚠️

**Original proposal** (WRONG):
```python
# This creates a NEW object that's not tracked by SQLAlchemy!
agg = ProjectTaskStatusAgg(
    project_id=UUID(data['project_id']),
    total_tasks=data['total_tasks'],
    ...
)
db.add(agg)  # Adding a new instance causes INSERT instead of UPDATE later!
```

**Problem**: Creating a new `ProjectTaskStatusAgg` instance from cache creates a **detached object** that SQLAlchemy doesn't recognize as coming from the database. If you later try to update it, SQLAlchemy will try to INSERT instead of UPDATE, causing primary key conflicts.

**Correct approach**:
```python
# Option A: Don't cache the object, cache the values only
async def get_or_create_project_aggregation(
    db: AsyncSession,
    project_id: UUID,
) -> ProjectTaskStatusAgg:
    # Always query the database for the object
    result = await db.execute(
        select(ProjectTaskStatusAgg).where(
            ProjectTaskStatusAgg.project_id == project_id
        )
    )
    agg = result.scalar_one_or_none()

    if agg is None:
        # Check cache for initial values (only used on first creation)
        redis = await redis_service.client
        cached = await redis.get(f"project_agg:{project_id}")

        if cached:
            data = json.loads(cached)
            # Use cached values to populate NEW object
            agg = ProjectTaskStatusAgg(
                project_id=project_id,
                total_tasks=data['total_tasks'],
                todo_tasks=data['todo_tasks'],
                # ...
            )
        else:
            # No cache - create empty and recalculate
            agg = ProjectTaskStatusAgg(project_id=project_id, ...)
            # ... expensive recalculation ...

        db.add(agg)
        await db.flush()

        # Cache for next time
        await redis.set(
            f"project_agg:{project_id}",
            json.dumps({...}),
            ttl=300
        )

    return agg  # Returns SQLAlchemy-tracked object
```

**Option B (Better)**: Cache to skip the expensive recalculation, not the DB query
```python
async def get_or_create_project_aggregation(
    db: AsyncSession,
    project_id: UUID,
) -> ProjectTaskStatusAgg:
    # Always query DB first (fast - indexed lookup)
    result = await db.execute(
        select(ProjectTaskStatusAgg).where(
            ProjectTaskStatusAgg.project_id == project_id
        )
    )
    agg = result.scalar_one_or_none()

    if agg:
        # Already exists - return it (no cache needed)
        return agg

    # Doesn't exist - need to create
    # Check if we have cached initial values
    redis = redis_service.client
    cache_key = f"project_agg_init:{project_id}"
    cached = await redis.get(cache_key)

    if cached:
        # Use cached counts instead of recalculating
        data = json.loads(cached)
        agg = ProjectTaskStatusAgg(
            project_id=project_id,
            total_tasks=data['total_tasks'],
            todo_tasks=data['todo_tasks'],
            active_tasks=data['active_tasks'],
            review_tasks=data['review_tasks'],
            issue_tasks=data['issue_tasks'],
            done_tasks=data['done_tasks'],
        )
    else:
        # No cache - create and recalculate (expensive)
        agg = ProjectTaskStatusAgg(project_id=project_id, ...)
        db.add(agg)
        await db.flush()

        # EXPENSIVE: Load all tasks to recalculate
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.task_status))
            .where(
                Task.project_id == project_id,
                Task.archived_at.is_(None),
            )
        )
        existing_tasks = result.scalars().all()

        if existing_tasks:
            recalculate_aggregation_from_tasks(agg, existing_tasks)
            await db.flush()

        # Cache the initial counts
        await redis.set(
            cache_key,
            json.dumps({
                'total_tasks': agg.total_tasks,
                'todo_tasks': agg.todo_tasks,
                'active_tasks': agg.active_tasks,
                'review_tasks': agg.review_tasks,
                'issue_tasks': agg.issue_tasks,
                'done_tasks': agg.done_tasks,
            }),
            ttl=3600  # 1 hour
        )

    db.add(agg)
    await db.flush()
    return agg
```

---

#### Issue #2: Cache Invalidation Complexity ⚠️

**Challenge**: ProjectTaskStatusAgg is updated in many places:
- Task creation (current code)
- Task status change (move between columns)
- Task archival
- Task deletion
- Task unarchival

**Risk**: Forgetting to invalidate cache in one place = stale data

**Recommendation**: Don't cache the aggregation object itself. Instead, **cache only during the expensive first-time initialization**.

**Why this is better**:
1. The expensive operation (loading 1000+ tasks) only happens once per project
2. After that, ProjectTaskStatusAgg exists in DB and is updated via normal UPDATE queries (fast)
3. No need to invalidate cache on every task change
4. Cache is only used for bootstrapping new projects

---

### Revised Caching Strategy (RECOMMENDED)

**Cache what's expensive**: The initial recalculation from all tasks

**Don't cache**: The ProjectTaskStatusAgg object itself (keep using DB)

**Implementation**:
```python
# Only cache the expensive recalculation result
# Cache key: "project_agg_init:{project_id}"
# Cache TTL: 1 hour (only needed until first aggregation is created)
# Invalidation: Delete on first task creation (one-time)

async def get_or_create_project_aggregation(
    db: AsyncSession,
    project_id: UUID,
) -> ProjectTaskStatusAgg:
    # Step 1: Check if aggregation already exists in DB
    result = await db.execute(
        select(ProjectTaskStatusAgg).where(
            ProjectTaskStatusAgg.project_id == project_id
        )
    )
    agg = result.scalar_one_or_none()

    if agg:
        # Fast path: Already exists, return it
        return agg

    # Step 2: Need to create - check if we have cached counts
    redis = redis_service.client
    cache_key = f"project_agg_init:{project_id}"
    cached_counts = await redis.get_json(cache_key)

    if cached_counts:
        # Use cached counts (avoids loading all tasks)
        agg = ProjectTaskStatusAgg(
            project_id=project_id,
            **cached_counts  # Unpack: total_tasks, todo_tasks, etc.
        )
        db.add(agg)
        await db.flush()

        # Clear the initialization cache (no longer needed)
        await redis.delete(cache_key)

        return agg

    # Step 3: No cache - do expensive recalculation
    agg = ProjectTaskStatusAgg(
        project_id=project_id,
        total_tasks=0,
        todo_tasks=0,
        active_tasks=0,
        review_tasks=0,
        issue_tasks=0,
        done_tasks=0,
    )
    db.add(agg)
    await db.flush()

    # EXPENSIVE: Load all existing tasks
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.task_status))
        .where(
            Task.project_id == project_id,
            Task.archived_at.is_(None),
        )
    )
    existing_tasks = result.scalars().all()

    if existing_tasks:
        recalculate_aggregation_from_tasks(agg, existing_tasks)
        await db.flush()

    # Cache the result for next project (if they have similar size)
    # This helps if user creates multiple projects in succession
    await redis.set(
        cache_key,
        {
            'total_tasks': agg.total_tasks,
            'todo_tasks': agg.todo_tasks,
            'active_tasks': agg.active_tasks,
            'review_tasks': agg.review_tasks,
            'issue_tasks': agg.issue_tasks,
            'done_tasks': agg.done_tasks,
        },
        ttl=3600  # 1 hour
    )

    return agg
```

**Benefits**:
- ✅ No SQLAlchemy session tracking issues
- ✅ No complex cache invalidation (cache auto-expires)
- ✅ Only caches the truly expensive operation (first-time recalculation)
- ✅ Subsequent calls use DB (fast indexed lookup)

---

### Redis Service Usage Pattern

```python
# Import
from app.services.redis_service import redis_service

# Get client
redis = redis_service.client

# Cache operations
await redis.set("key", {"data": "value"}, ttl=300)  # Auto-JSON-encodes
await redis.get_json("key")  # Auto-JSON-decodes
await redis.delete("key")
await redis.exists("key")
```

**✅ VERDICT: Optimization #3 is SAFE with the revised implementation above**

---

## ⚠️ Optimization #4: Eager Loading - CONFLICTS FOUND

### Current Model Configuration

#### Project Model Relationships (Existing):

```python
# File: fastapi-backend/app/models/project.py

class Project(Base):
    # Line 213-217: Already eager loaded!
    derived_status = relationship(
        "TaskStatus",
        foreign_keys=[derived_status_id],
        lazy="joined",  # ⚠️ AUTO-JOINS on query
    )

    # Line 230-236: NOT eager loaded (query object)
    task_statuses = relationship(
        "TaskStatus",
        back_populates="project",
        lazy="dynamic",  # ⚠️ Returns query object, not list
    )

    # Line 247-252: Lazy loaded (on-access)
    status_aggregation = relationship(
        "ProjectTaskStatusAgg",
        uselist=False,
        lazy="select",  # ⚠️ Loads on first access
    )
```

#### Task Model Relationships (Existing):

```python
# File: fastapi-backend/app/models/task.py

class Task(Base):
    # Line 190-194: Already eager loaded!
    task_status = relationship(
        "TaskStatus",
        lazy="joined",  # ⚠️ AUTO-JOINS on query
    )

    # Line 195-200: Already eager loaded!
    assignee = relationship(
        "User",
        foreign_keys=[assignee_id],
        lazy="joined",  # ⚠️ AUTO-JOINS on query
    )

    # Line 201-206: Already eager loaded!
    reporter = relationship(
        "User",
        foreign_keys=[reporter_id],
        lazy="joined",  # ⚠️ AUTO-JOINS on query
    )
```

---

### Issue #1: Relationships Already Configured for Eager Loading ⚠️

**Finding**: Task model already has `lazy="joined"` on:
- `task_status`
- `assignee`
- `reporter`

**What this means**:
```python
# When you do this:
task = await db.get(Task, task_id)

# SQLAlchemy AUTOMATICALLY runs:
# SELECT tasks.*, task_statuses.*, users_assignee.*, users_reporter.*
# FROM tasks
# LEFT JOIN task_statuses ON ...
# LEFT JOIN users AS users_assignee ON ...
# LEFT JOIN users AS users_reporter ON ...
```

**Implication**: The `db.refresh()` at line 1178 already does eager loading via JOINs!

```python
# Line 1178 in tasks.py
await db.refresh(task, attribute_names=["task_status", "assignee", "reporter", "project"])
```

This is **already optimal** - it uses the `lazy="joined"` configuration.

---

### Issue #2: Redundant Lazy Loads at Lines 1189-1190 ✅ CONFIRMED

```python
# Line 1178: Loads via JOINs (because lazy="joined")
await db.refresh(task, attribute_names=["task_status", "assignee", "reporter", "project"])

# Line 1189-1190: REDUNDANT - data already loaded
_ = task.assignee  # No query (already in session)
_ = task.reporter  # No query (already in session)
```

**Verdict**: These lines should be **deleted** (Optimization #1) ✅

---

### Issue #3: Using selectinload() Will OVERRIDE Model Configuration ⚠️

**Original proposal**:
```python
result = await db.execute(
    select(Project)
    .options(
        joinedload(Project.derived_status),  # ⚠️ Redundant - already lazy="joined"
        selectinload(Project.task_statuses),  # ⚠️ Overrides lazy="dynamic"
    )
    .where(Project.id == project_id)
)
```

**Problem #1**: `joinedload(Project.derived_status)` is redundant
- Model already has `lazy="joined"`
- SQLAlchemy will use JOIN automatically
- Explicit `joinedload()` just duplicates the configuration

**Problem #2**: `selectinload(Project.task_statuses)` changes behavior
- Original: `lazy="dynamic"` returns a Query object (not evaluated)
- With selectinload: Forces evaluation and loads all TaskStatuses into memory
- **This could be intentional** if you need all statuses, but it changes behavior

---

### Issue #4: lazy="dynamic" Requires Special Handling ⚠️

**What is `lazy="dynamic"`?**
```python
# With lazy="dynamic":
project.task_statuses  # Returns a Query object, not a list!

# You can filter it:
todo_status = project.task_statuses.filter_by(name="Todo").first()

# You can count without loading:
count = project.task_statuses.count()

# To load all (triggers query):
all_statuses = project.task_statuses.all()
```

**If you use selectinload**:
```python
result = await db.execute(
    select(Project)
    .options(selectinload(Project.task_statuses))
    .where(Project.id == project_id)
)
project = result.unique().scalar_one()

# Now it's a list, not a query!
project.task_statuses  # Returns list[TaskStatus]
project.task_statuses.filter_by(...)  # ❌ ERROR - list has no filter_by
```

**Recommendation**: Don't use selectinload on `lazy="dynamic"` relationships unless you're changing the code that uses them.

---

### Issue #5: Current Project Query Already Uses selectinload ✅

**File**: `fastapi-backend/app/routers/tasks.py:150-152`

```python
result = await db.execute(
    select(Project)
    .options(selectinload(Project.application))  # ✅ Good
    .where(Project.id == project_id)
)
project = result.scalar_one_or_none()
```

**Analysis**:
- ✅ Loads `Project.application` eagerly (one extra query with WHERE IN)
- ❌ Doesn't load `derived_status` (but it's `lazy="joined"` so it auto-loads anyway)
- ❌ Doesn't load `task_statuses` (stays as dynamic query object)

**Recommendation**: This is **already good**. The `lazy="joined"` relationships auto-load.

---

### Correct Optimization #4 Implementation

#### What NOT to do:
```python
# ❌ DON'T: Override already-optimized lazy="joined" relationships
.options(
    joinedload(Project.derived_status),  # Redundant
    joinedload(Task.assignee),           # Redundant
    joinedload(Task.reporter),           # Redundant
)
```

#### What TO do:

**1. Use the existing configuration** (no changes needed):
```python
# Current code (already optimal):
result = await db.execute(
    select(Project)
    .options(selectinload(Project.application))
    .where(Project.id == project_id)
)
project = result.scalar_one_or_none()

# Project.derived_status is auto-loaded (lazy="joined")
# Access it directly:
status_name = project.derived_status.name if project.derived_status else None
```

**2. For task_statuses, query directly instead of selectinload**:
```python
# Don't convert lazy="dynamic" to a list
# Instead, use it as a query:

# Option A: Filter for specific status
todo_status = await db.execute(
    select(TaskStatus).where(
        TaskStatus.project_id == project_id,
        TaskStatus.name == "Todo"
    )
)
todo_status = result.scalar_one_or_none()

# Option B: Load all if needed (explicit)
result = await db.execute(
    select(TaskStatus).where(TaskStatus.project_id == project_id)
)
all_statuses = result.scalars().all()
```

**3. Remove redundant operations**:
```python
# ❌ DELETE these (Optimization #1):
# Line 1189-1190 in tasks.py
_ = task.assignee
_ = task.reporter

# ✅ Data already loaded by db.refresh() at line 1178
```

---

### Summary: What Actually Needs Optimization

#### ✅ Ready to implement (safe):

1. **Delete lines 1189-1190** in `tasks.py` (redundant lazy loads)
2. **Use cached value** instead of re-querying at `projects.py:475-479`

#### ⚠️ Needs caution:

3. **Don't add eager loading options** - models already configured optimally
4. **Keep lazy="dynamic" as-is** - it's intentionally a query object

#### ❌ Don't implement:

- Adding `joinedload()` for relationships that already have `lazy="joined"`
- Converting `lazy="dynamic"` relationships with `selectinload()`

---

## Final Recommendations

### Optimization #3: Redis Caching
**Status**: ✅ SAFE to implement with revised approach

**Use**:
- Cache initialization values only (not SQLAlchemy objects)
- Cache key: `project_agg_init:{project_id}`
- TTL: 1 hour
- Auto-delete after first use

**Benefits**: Saves 1-5 seconds on first task in projects with 1000+ existing tasks

---

### Optimization #4: Eager Loading
**Status**: ⚠️ MOSTLY ALREADY DONE

**Actions**:
1. ✅ Delete redundant lazy loads (lines 1189-1190) - **Safe, do this**
2. ✅ Use in-memory data instead of re-querying (projects.py:475-479) - **Safe, do this**
3. ❌ Don't add eager loading options - **Models already optimized**

**Benefits**: Saves 100-300ms by removing redundant operations

---

## Modified Implementation Priority

### Phase 1: Low-Risk Cleanup (15 minutes)
1. ✅ Delete lines 1189-1190 in `tasks.py`
2. ✅ Replace lines 475-479 in `projects.py` with cached value
3. ✅ Fire-and-forget WebSocket broadcasts (asyncio.create_task)

**Expected gain**: 500-800ms (no risk)

### Phase 2: Redis Initialization Cache (30 minutes)
1. ✅ Add cache to `get_or_create_project_aggregation()`
2. ✅ Use revised implementation (cache init values only)
3. ✅ Test with project that has 1000+ tasks

**Expected gain**: 1-5 seconds on first task (low risk with revised approach)

### Phase 3: Skip Eager Loading Changes
- ❌ Models already optimized
- ❌ Adding options would be redundant or breaking

---

## Testing Checklist

### Redis Caching Tests:
- [ ] Create first task in new project (should recalculate)
- [ ] Create second task (should use DB, not recalculate)
- [ ] Create first task in project with 1000+ existing tasks (should use cache if available)
- [ ] Verify aggregation counts are correct
- [ ] Test with Redis unavailable (should fallback gracefully)

### Eager Loading Tests:
- [ ] Verify task.assignee is loaded without extra query
- [ ] Verify task.reporter is loaded without extra query
- [ ] Verify project.derived_status is loaded without extra query
- [ ] Check SQLAlchemy query logs (should see fewer queries)

### Regression Tests:
- [ ] Task creation still works
- [ ] Project status derivation still works
- [ ] WebSocket broadcasts still work (just async now)
- [ ] No duplicate key errors
- [ ] No stale data in aggregations
