# Blair AI Agent: Claude Code-Level Cognitive Pipeline

**Last updated**: 2026-03-02

## Context

Blair is currently a simple ReAct agent — the LLM either calls `sql_query` (generates raw SQL) or `query_knowledge` (vector search) and loops. No structured reasoning, no understanding phase, no clarification pipeline.

**Problem**: Blair doesn't truly understand the question. It blindly picks a tool and hopes for the best. Compare with Claude Code, which has distinct phases: read CLAUDE.md → understand intent → explore codebase → clarify if needed → verify → execute.

**Goal**: Transform Blair into a Claude Code-level cognitive pipeline with:
1. Structured multi-node workflow (understand → clarify → explore → verify → execute)
2. Comprehensive function tools (like Claude Code's Read/Glob/Grep) instead of raw SQL
3. Knowledge base vector search as the document search equivalent
4. Batched clarification (all questions at once, with A/B/C options + free text)

---

## Part A: Comprehensive Function Tools (Replace sql_query)

### Design Philosophy

Like Claude Code has ~8 well-scoped tools (Read, Write, Glob, Grep, Bash, etc.) instead of one "run any command" tool, Blair should have **domain-scoped composite tools** instead of one generic `sql_query`.

Each tool:
- Covers a **domain** (apps, projects, tasks, docs)
- Returns **composite/rich data** — the LLM filters what it needs
- Uses **parameters** for flexibility within the domain
- Enforces **RBAC** via the existing ContextVar mechanism

### New Tool Suite (22 READ tools + 4 WRITE tools + 1 fallback)

#### 1. Identity & Context (2 tools)

| Tool | Description | Returns |
|------|-------------|---------|
| `get_my_profile` | Current user's identity, role info, app count | name, email, apps I own, apps I'm member of, role per app |
| `get_my_workload` | My current assignments across all projects | tasks assigned to me grouped by project + status, overdue count |

#### 2. Application Domain (3 tools)

| Tool | Description | Returns |
|------|-------------|---------|
| `list_applications` | All apps I have access to | name, description, my role, member count, project count, created_at (already exists — ENHANCE) |
| `get_application_details(app)` | Deep dive into one app | name, desc, owner, all members+roles, project list+statuses, document count, folder count, recent activity |
| `get_application_members(app)` | Members of an app with their roles | user name, email, role, is_manager, projects they're in |

#### 3. Project Domain (5 tools)

| Tool | Description | Returns |
|------|-------------|---------|
| `list_projects(app)` | Projects in an app | name, key, status, due_date, owner, task counts, completion %, created/updated (already exists — ENHANCE with more data) |
| `get_project_details(project)` | Complete project overview | name, key, desc, owner, due_date, members+roles, status breakdown (todo/progress/review/issue/done counts), recent tasks, document count |
| `get_project_members(project)` | Project team composition | user name, email, role (admin/member), assigned task count, completion rate |
| `get_project_timeline(project)` | Recent activity + burndown | last 20 task changes (created/moved/completed), tasks by week, overdue trend |
| `get_overdue_tasks(scope?)` | Overdue tasks | task key, title, assignee, due_date, days overdue, project (already exists — keep as-is) |

#### 4. Task Domain (4 tools)

| Tool | Description | Returns |
|------|-------------|---------|
| `list_tasks(project, filters?)` | Tasks with flexible filtering | key, title, status, priority, assignee, due_date, checklist progress (already exists — ENHANCE with filters: status, assignee, priority, due_date range) |
| `get_task_detail(task)` | Full task with all related data | title, desc, status, priority, assignee, reporter, due_date, story_points, ALL comments (with author+body), ALL checklists+items, attachment list (name+type+size), subtasks, parent |
| `get_task_comments(task)` | All comments on a task with mentions | comment body, author, created_at, mentions, attachments |
| `get_blocked_tasks(project?)` | Tasks in "Issue" status + overdue | task key, title, status reason, assignee, blocked duration |

#### 5. Knowledge Base Domain (5 tools — the "Grep/Glob" equivalent)

| Tool | Description | Returns |
|------|-------------|---------|
| `search_knowledge(query)` | Hybrid RAG search (semantic + keyword + fuzzy) | document title, matched chunk text, heading context, score, source type (already exists as `query_knowledge` — RENAME for clarity) |
| `browse_folders(scope)` | Folder tree structure | folder hierarchy with doc counts per folder (already exists as `browse_knowledge` — RENAME) |
| `get_document_details(doc)` | Document metadata + stats | title, scope, folder path, created_by, created_at, updated_at, word count, tag list, embedding status, collaborators |
| `list_recent_documents(scope?)` | Recently modified docs | title, scope, last editor, updated_at, word count |
| `get_my_notes` | Personal scope documents | title, folder, updated_at, word count (filters to user_id scope) |

#### 6. Export (1 tool)

| Tool | Description | Returns |
|------|-------------|---------|
| `export_to_excel(data_type, scope, filters?)` | Export data to Excel file | Generates .xlsx via openpyxl, returns download URL. Supports: tasks, project_summary, team_workload, overdue_report. HITL confirmation before generating (write tool). |

`export_to_excel` is a write tool (generates a file) — uses `interrupt()` for user confirmation before generating. Accepts:
- `data_type`: "tasks", "project_summary", "team_workload", "overdue_report"
- `scope`: app or project name (fuzzy resolved)
- `filters`: optional status/assignee/date range filters

Uses `openpyxl` (already a dependency from Phase 3.1 spec). Stores the generated file in MinIO and returns a download URL.

#### 7. Utility (2 tools)

| Tool | Description | Returns |
|------|-------------|---------|
| `understand_image(url)` | Vision AI analysis | image description (already exists — keep as-is) |
| `sql_query(question)` | **LAST RESORT** — NL-to-SQL fallback | raw query results (already exists — DEPRIORITIZE in system prompt, like Bash in Claude Code) |

#### 8. Write Tools (5 tools)

| Tool | Description |
|------|-------------|
| `create_task(project, title, ...)` | Create task with HITL confirmation (unchanged) |
| `update_task_status(task, status)` | Move task status with HITL (unchanged) |
| `assign_task(task, user)` | Assign/reassign with HITL (unchanged) |
| `create_document(title, content, scope)` | Create doc with HITL (unchanged) |
| `export_to_excel(data_type, scope, filters?)` | Generate Excel report with HITL (NEW) |

### Fuzzy Name Matching (All Tools Accept Names, Not Just UUIDs)

**Problem**: Users say "tasks in the marketing project" — not UUIDs. Every tool must accept fuzzy names.

**How it works**: Each tool accepts a `str` parameter. Internally, it does:
1. Try parsing as UUID → fast path if in RBAC access list
2. Fuzzy ILIKE match → scoped to user's accessible entities only
3. 1 match → use it
4. 0 matches → return "not found" error
5. Multiple matches → return match list so LLM can pick or ask user

This logic is **shared** in `tools/helpers.py` to avoid repeating the same ~30 lines in every tool. The existing `_resolve_application` and `_resolve_project` already do this (ILIKE + RBAC scoping). We extend to all entity types:

| Entity | Accepts | Matches On |
|--------|---------|------------|
| Application | UUID or name | `name ILIKE %input%`, RBAC-scoped |
| Project | UUID or name | `name ILIKE %input%`, RBAC-scoped |
| Task | UUID, task_key, or title | `task_key = input` first, then `title ILIKE %input%` |
| User | UUID, email, or name | `email ILIKE` or `display_name ILIKE`, scoped to app/project members |
| Document | UUID or title | `title ILIKE %input%`, RBAC-scoped |

**Example flow**:
```
User: "show me tasks in marketing"
→ LLM calls list_tasks(project="marketing")
→ Internal: ILIKE match finds "Marketing Dashboard" project
→ Returns task list
```

```
User: "show me the project" (3 projects exist, ambiguous)
→ understand node: confidence=0.3, needs_clarification
→ clarify node: interrupt with options: "A) Alpha (12 tasks) B) Beta (8 tasks) C) Gamma (3 tasks)"
→ User picks "Alpha"
→ LLM calls get_project_details(project="Alpha")
```

### Archived Items Handling

Both `Project` and `Task` have `archived_at` columns. The scoped views (`v_tasks`) already filter `WHERE archived_at IS NULL`.

**Best practice**: Default to active-only, with an `include_archived` parameter on listing tools:

| Tool | Default | With `include_archived=True` |
|------|---------|------------------------------|
| `list_projects(app)` | Active projects only | Active + archived (archived ones marked with `[ARCHIVED]`) |
| `list_tasks(project, filters?)` | Active tasks only | Active + archived |
| `get_project_details(project)` | Active tasks in metrics | All tasks in metrics |
| `get_overdue_tasks()` | Active only (archived tasks can't be "overdue") | N/A — always active only |

- Tools that list items get `include_archived: bool = False` parameter
- Archived items are **clearly labeled** in output: `"[ARCHIVED] Marketing Dashboard (archived 2026-01-15)"`
- When user says "show me archived projects", LLM passes `include_archived=True`
- The resolver `_resolve_project` also searches archived projects when the LLM passes an archived project name (for `get_project_details` use case)
- Soft-deleted documents (`deleted_at IS NOT NULL`) are **never** returned — they're truly deleted, not "archived"

### Tool Count Summary

- **Current**: 12 read + 4 write = 16 tools
- **New**: 22 read + 5 write + 1 fallback = 28 tools
- **Net new tools**: 12 new tools (11 read + 1 write/export)
- **Renamed**: 2 (`query_knowledge` → `search_knowledge`, `browse_knowledge` → `browse_folders`)
- **Enhanced**: 4 (`list_applications`, `list_projects`, `list_tasks`, `get_task_detail`)
- **Removed from system prompt priority**: `sql_query` (kept but deprioritized)

### Tool Parameter Convention

**Every tool that references an entity uses `str` parameters (not UUID), with docstrings that tell the LLM it accepts fuzzy names:**

```python
@tool
async def get_project_details(project: str) -> str:
    """Get complete project overview including members, task metrics, and recent activity.

    Args:
        project: Project name, key, or UUID (partial match supported).
                 Examples: "Marketing", "MARK", "marketing dashboard"
    """
    ctx = _get_ctx()
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_project(project, db)
        if error:
            return error  # "Multiple projects match 'mar': ..." or "Not found"
        # ... fetch composite data using resolved UUID
```

**The LLM sees**: `get_project_details(project: str)` with "partial match supported" in the docstring.
**The user says**: "show me the marketing project"
**The LLM calls**: `get_project_details(project="marketing")`
**The resolver does**: ILIKE fuzzy match → finds "Marketing Dashboard" → returns composite data.

This means the LLM **never needs to call `list_applications` just to get an ID** — it passes the user's words directly and the resolver handles it. Just like Claude Code's `Read` tool accepts a file path without needing to `Glob` first.

---

## Part B: Multi-Node Cognitive Pipeline

### New State Schema

```python
# fastapi-backend/app/ai/agent/state.py

class RequestClassification(TypedDict, total=False):
    intent: Literal["info_query", "action_request", "needs_clarification",
                     "multi_step", "greeting", "follow_up"]
    confidence: float              # 0.0–1.0
    data_sources: list[str]        # ["projects", "tasks", "knowledge", "members"]
    entities: list[dict[str, str]] # [{"type": "project", "value": "Alpha"}]
    clarification_questions: list[str]
    complexity: Literal["simple", "moderate", "complex"]
    reasoning: str

class ResearchFindings(TypedDict, total=False):
    tool_results: list[dict[str, str]]  # [{"tool": "get_project_details", "result": "..."}]
    sources: list[dict]

class AgentState(TypedDict):
    # Core (unchanged)
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    accessible_app_ids: list[str]
    accessible_project_ids: list[str]
    # New pipeline fields
    current_phase: str
    classification: RequestClassification
    research: ResearchFindings
    total_tool_calls: int
    total_llm_calls: int
    iteration_count: int
    fast_path: bool
```

### Graph Topology (7 nodes)

```
[START]
   │
   ▼
┌─────────┐
│ intake   │  (0 LLM calls — load context, init counters, cache model)
└─────────┘
   │
   ▼
┌───────────┐
│ understand │  (1 LLM call — classify intent, entities, confidence)
└───────────┘
   │
   ├── confidence ≥ 0.7 + greeting/follow_up ──→ [respond] (fast path, 1 LLM)
   │
   ├── confidence < 0.5 OR needs_clarification ──→ [clarify]
   │                                                    │
   │                                              interrupt(questions[])
   │                                              user answers → resume
   │                                                    │
   │                                                    ▼
   │                                              [understand] (re-classify with answers)
   │                                                    │
   │                                              routes normally (→ explore or → clarify again)
   │
   └── everything else ──────────────────────────→ [explore]
                                                       │
                                                  ┌────┴────┐
                                                  │ ReAct   │
                                                  │ Loop    │
                                                  │         │
                                              ┌───▼───┐     │
                                              │explore │ LLM picks tools
                                              │_tools  │ ToolNode executes
                                              └───┬───┘     │
                                                  └─────────┘
                                                       │
                                              LLM done (no more tool_calls)
                                                       │
                                        ┌──────────────┴──────────────┐
                                        │                             │
                                   complex/multi_step            simple/moderate
                                        │                             │
                                        ▼                             │
                                 ┌────────────┐                       │
                                 │ synthesize  │ (1 LLM — organize    │
                                 │             │  findings, verify)    │
                                 └──────┬─────┘                       │
                                        │                             │
                              route_after_synthesize                   │
                              /                   \                    │
                             /                     \                   │
                      user corrects              approved              │
                      (any rejection)               |                  │
                           |                        |                  │
                           ▼                        ▼                  ▼
                      [understand]            ┌────────────┐
                      (re-classify)           │  respond    │ ──→ [END]
                      then routes             └────────────┘
                      normally
```

### Node Details

#### `intake` (0 LLM calls)
- Initialize `total_tool_calls`, `total_llm_calls`, `iteration_count` counters
- Cache the LangChain chat model (resolve provider from DB — same as current)
- Cache custom system prompt from `AiSystemPrompt` table
- Pure logic, no LLM call

#### `understand` (1 LLM call)
- Focused classification prompt (~500 input tokens, ~100 output tokens)
- Uses only last 6 messages for context (not full history)
- Returns structured JSON: intent, confidence, data_sources, entities, clarification_questions
- Sets `fast_path = True` for greetings/follow_ups with high confidence
- **Fallback**: If JSON parse fails, defaults to `{intent: "info_query", confidence: 0.7, complexity: "moderate"}` → routes to explore safely

#### `clarify` (0 LLM calls, uses interrupt)
- Triggered when confidence < 0.5 or intent is `needs_clarification`
- **Batches ALL questions** into one `interrupt()` call
- Payload format for frontend:
  ```json
  {
    "type": "clarification",
    "questions": [
      {"text": "Which project?", "options": ["Alpha", "Beta", "Gamma"]},
      {"text": "What time range?", "options": ["This week", "This month", "All time"]}
    ],
    "context": "I found 3 projects matching your query"
  }
  ```
- User responds via `/api/ai/chat/resume` (same existing HITL mechanism)
- After resume, injects user answers as HumanMessage and routes back to `understand` (re-classify with the new context — user's answers may change the intent, entities, or data sources needed)

#### `explore` (1–10 LLM calls, ReAct loop)
- Same ReAct pattern as current `agent_node` but with **enhanced system prompt** that includes:
  - Classification context (intent, entities found, data sources to use)
  - Accumulated research findings so far
  - **Tool selection guidance** (don't use sql_query if a specific tool covers it)
- Binds ALL 27 tools to the LLM
- Loops: `explore` → `explore_tools` → `explore` until LLM stops calling tools
- Safety limits enforced per-iteration: MAX_TOOL_CALLS=50, MAX_ITERATIONS=10, MAX_LLM_CALLS=15

#### `explore_tools` (0 LLM calls)
- Standard `ToolNode` execution (existing LangGraph pattern)
- Also accumulates tool results into `research.tool_results` for synthesis context
- Write tools still call `interrupt()` here — HITL works exactly as before

#### `synthesize` (1 LLM call, optional interrupt for verification)
- Only reached for `complex` or `multi_step` queries
- LLM receives all accumulated research and organizes into structured response
- For action requests: produces an execution plan the user can verify
- For comparisons: produces tables/structured data

**Verification with re-routing** (when user rejects synthesis):
- For action plans or uncertain findings, `synthesize` calls `interrupt()` with a verification payload:
  ```json
  {
    "type": "verification",
    "summary": "Here's what I found. Is this what you're looking for?",
    "findings": "...",
    "options": ["Yes, proceed", "No, I meant something different", "Refine the search"]
  }
  ```
- **User approves** → routes to `respond` (deliver final answer)
- **User corrects** → their correction is injected as a HumanMessage, routes back to `explore` with fresh context. The explore LLM sees the original query + findings + user correction, so it searches differently
- **User says "I meant something different"** → routes back to `clarify` with a follow-up clarification question

Re-routing logic: when the user rejects or corrects, route back through `understand` to re-classify. The user's correction is new input that may change intent, entities, or data sources:

```python
def route_after_synthesize(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    # Was the synthesis interrupted and user provided correction?
    if isinstance(last_msg, HumanMessage):
        # User correction = new input → re-classify via understand
        return "understand"
    return "respond"  # Synthesis completed normally → deliver response
```

**Best practice**: Always route corrections back through `understand` because:
- User's correction may change the intent ("no, I want to CREATE a task, not view tasks")
- New entities may be mentioned ("I meant the Beta project, not Alpha")
- Different data sources may be needed ("search the knowledge base, not the task list")
- The `understand` node is cheap (1 small LLM call) and prevents misrouted explorations
- If `understand` classifies with high confidence, it fast-tracks to `explore` (skips clarify)
- If `understand` detects ambiguity again, it routes to `clarify` for another round

#### `respond` (0–1 LLM calls)
- Fast path: 1 LLM call with full tools bound (handles greetings, simple follow-ups)
- Post-explore: 0 calls — response already in messages from explore phase
- Post-synthesize: 0 calls — response already in messages from synthesis
- **Misclassification recovery**: If fast-path LLM unexpectedly returns tool_calls, re-routes to `explore_tools`

### LLM Call Budget

| Scenario | LLM Calls | Current |
|----------|-----------|---------|
| Greeting ("hello") | 2 (understand + respond) | 1 |
| Simple query ("how many tasks in Alpha?") | 3–4 (understand + explore×2-3) | 2–3 |
| Complex query + clarification | 5–7 (understand + explore×3-4 + synthesize) | 3–5 |
| **Worst case** | 12 (understand + explore×10 + synthesize) | 11 |

The `understand` node adds 1 extra call but enables fast-pathing and better tool selection, net positive.

### SSE Phase Streaming (Shows Each Step in UI)

Like Claude Code shows "Reading file...", "Searching codebase...", Blair streams each pipeline phase to the frontend in real-time.

**New SSE event**: `phase_changed`
```
event: phase_changed
data: {"phase": "understand", "label": "Understanding your request..."}

event: phase_changed
data: {"phase": "explore", "label": "Researching..."}

event: phase_changed
data: {"phase": "synthesize", "label": "Analyzing results..."}
```

**Phase labels** (shown in UI):

| Phase | Label |
|-------|-------|
| `intake` | *(not shown — instant)* |
| `understand` | "Understanding your request..." |
| `clarify` | "Need some clarification..." |
| `explore` | "Researching..." |
| `explore_tools` | *(not shown — tool_call_start/end already handles this)* |
| `synthesize` | "Analyzing results..." |
| `respond` | "Preparing response..." |

**Backend**: Emitted from `_stream_agent` in `ai_chat.py` when detecting `on_chain_start` events for each node.

**Frontend changes needed** (small):
1. Add `phase_changed` to `VALID_SSE_EVENTS` set in `use-ai-chat.ts`
2. Add `PhaseChangedEvent` to `ChatStreamEvent` union in `types.ts`
3. Add `current_phase?: string` field to `ChatMessage` in `types.ts`
4. In `processSSEStream` case handler: update assistant message with `current_phase`
5. In `AiMessageRenderer`: show a phase indicator pill/label above the streaming text
   - Small, subtle label like: `🔍 Researching...` or `💡 Understanding your request...`
   - Disappears when text starts streaming or phase changes
   - Styled similar to existing `ToolExecutionCard` but more minimal

**Visual (in the chat):**
```
┌─────────────────────────────────┐
│ User: show me tasks in Alpha    │
├─────────────────────────────────┤
│ 💡 Understanding your request.. │  ← phase indicator (fades)
│ 🔍 Researching...              │  ← phase indicator (fades)
│ ┌─ get_project_details ───────┐ │  ← tool call card (existing)
│ │ ✓ Found project Alpha       │ │
│ └─────────────────────────────┘ │
│ ┌─ list_tasks ────────────────┐ │  ← tool call card (existing)
│ │ ✓ 12 tasks found            │ │
│ └─────────────────────────────┘ │
│                                 │
│ Here are the tasks in Alpha:    │  ← streamed text (existing)
│ 1. ALPHA-1: Fix login bug...    │
│ 2. ALPHA-2: Add dashboard...    │
└─────────────────────────────────┘
```

### System Prompt Updates

The `SYSTEM_PROMPT` gets restructured to reflect the tool hierarchy:

```python
SYSTEM_PROMPT = """You are Blair, the PM Desktop AI assistant...

## Available Tools (by domain)

### Identity & Context
- get_my_profile: Your identity, roles, applications
- get_my_workload: Your current task assignments across all projects

### Applications
- list_applications: All apps you have access to
- get_application_details(app): Deep dive — members, projects, docs
- get_application_members(app): Team composition with roles

### Projects
- list_projects(app): Projects with status and metrics
- get_project_details(project): Complete overview with team + tasks
- get_project_members(project): Team with assignment stats
- get_project_timeline(project): Recent activity and trends
- get_overdue_tasks(scope?): Overdue tasks

### Tasks
- list_tasks(project, filters?): Filtered task list
- get_task_detail(task): Full detail with comments, checklists, attachments
- get_task_comments(task): All comments with mentions
- get_blocked_tasks(project?): Tasks in Issue status

### Knowledge Base (document search)
- search_knowledge(query): Semantic + keyword + fuzzy search
- browse_folders(scope): Folder tree with doc counts
- get_document_details(doc): Document metadata and stats
- list_recent_documents(scope?): Recently modified documents
- get_my_notes: Your personal documents

### Vision
- understand_image(url): AI image analysis

### Fallback (use only when no specific tool covers the query)
- sql_query(question): Natural language to SQL — LAST RESORT only

## Tool Selection Rules
1. ALWAYS prefer a specific tool over sql_query
2. Use search_knowledge for content questions ("what did we decide about...")
3. Use get_project_details/list_tasks for structural questions ("how many tasks...")
4. Only use sql_query for truly unusual queries no tool covers
"""
```

---

## Part C: File Structure & Changes

### New Files

```
fastapi-backend/app/ai/agent/
    state.py                      # AgentState, RequestClassification, ResearchFindings
    prompts.py                    # SYSTEM_PROMPT, CLASSIFICATION_PROMPT, SYNTHESIS_PROMPT, EXPLORE_SUFFIX
    routing.py                    # route_after_understand, route_after_explore, route_after_respond
    nodes/
        __init__.py               # Export all node functions
        intake.py                 # intake_node
        understand.py             # understand_node + _parse_classification
        clarify.py                # clarify_node
        explore.py                # explore_node + explore_tools_wrapper
        synthesize.py             # synthesize_node
        respond.py                # respond_node
    tools/
        __init__.py               # Export ALL_READ_TOOLS, ALL_WRITE_TOOLS
        context.py                # _tool_context_var, set/clear/get context
        helpers.py                # _resolve_application, _resolve_project, _check_access
        identity_tools.py         # get_my_profile, get_my_workload (NEW)
        application_tools.py      # list_applications (ENHANCED), get_application_details (NEW), get_application_members (NEW)
        project_tools.py          # list_projects (ENHANCED), get_project_details (NEW), get_project_members (NEW), get_project_timeline (NEW), get_overdue_tasks (MOVED)
        task_tools.py             # list_tasks (ENHANCED), get_task_detail (ENHANCED), get_task_comments (NEW), get_blocked_tasks (NEW)
        knowledge_tools.py        # search_knowledge (RENAMED), browse_folders (RENAMED), get_document_details (NEW), list_recent_documents (NEW), get_my_notes (NEW)
        utility_tools.py          # understand_image (MOVED), sql_query (MOVED+DEPRIORITIZED)
        write_tools.py            # create_task, update_task_status, assign_task, create_document (MOVED)
```

### Deleted Files

| File | Reason |
|------|--------|
| `tools_read.py` | Replaced by `tools/` directory (split into domain modules) |
| `tools_write.py` | Replaced by `tools/write_tools.py` |

### Modified Files

| File | Changes |
|------|---------|
| `graph.py` | **Replace entirely** — New 7-node pipeline orchestrator. Same `build_agent_graph` signature. No rollback needed (not in prod). |
| `ai_chat.py` | **Minor** — Add `phase_changed` SSE event in `_stream_agent`. Update `_setup_agent_context` imports to `tools/context.py`. |

### Frontend Files (minor changes for phase streaming)

| File | Changes |
|------|---------|
| `use-ai-chat.ts` | Add `phase_changed` to `VALID_SSE_EVENTS`, add case handler in `processEvents` |
| `types.ts` | Add `PhaseChangedEvent` to union, add `current_phase?: string` to `ChatMessage` |
| `ai-message-renderer.tsx` | Show phase indicator pill above streaming text |

### Unchanged Files

- `rbac_context.py` — RBAC context builder, no changes needed
- `source_references.py` — Source citation accumulator, no changes
- `copilotkit_runtime.py` — CopilotKit bridge, no changes
- All model files — No DB changes needed

---

## Part D: Implementation Order

### Step 1: Tool infrastructure + domain tools
- Create `tools/` directory with all files
- `context.py` — extract from `tools_read.py`: `_tool_context_var`, `set_tool_context`, `clear_tool_context`, `_get_ctx`
- `helpers.py` — extract + extend: `_resolve_application`, `_resolve_project`, `_resolve_task` (NEW), `_resolve_user` (NEW), `_resolve_document` (NEW)
- Build all domain tool files: `identity_tools.py`, `application_tools.py`, `project_tools.py`, `task_tools.py`, `knowledge_tools.py`, `utility_tools.py`, `write_tools.py`
- `__init__.py` — exports `ALL_READ_TOOLS`, `ALL_WRITE_TOOLS`
- Delete `tools_read.py` and `tools_write.py`
- **Tests**: Unit tests for each tool file + resolver

### Step 2: Pipeline state, nodes, and graph
- Create `state.py`, `prompts.py`, `routing.py`
- Create `nodes/` directory with all node files
- Replace `graph.py` with new 7-node pipeline
- Update `ai_chat.py` imports + add `phase_changed` SSE event
- **Tests**: Unit tests for nodes + routing + integration tests

### Step 3: Frontend phase streaming
- Add `phase_changed` SSE event handling
- Add phase indicator in AI message renderer

### Step 4: Validation
- Run full test suite: `pytest tests/ -v`
- Run linter: `ruff check app/ai/agent/`
- Manual testing: greetings, simple queries, complex queries, clarification flow, write operations

---

## Part E: Testing Strategy

### Unit Tests (per file)

| Test File | Tests |
|-----------|-------|
| `test_identity_tools.py` | get_my_profile returns correct user data, get_my_workload groups by project |
| `test_application_tools.py` | list_applications RBAC filtering, get_application_details composite data |
| `test_project_tools.py` | list_projects with due dates, get_project_details includes members+tasks, get_project_timeline recent activity |
| `test_task_tools.py` | list_tasks filtering, get_task_detail includes comments+checklists+attachments, get_blocked_tasks finds Issue status |
| `test_knowledge_tools.py` | search_knowledge hybrid search, get_document_details metadata, get_my_notes personal scope |
| `test_routing.py` | route_after_understand all branches, route_after_explore all branches |
| `test_understand_node.py` | Classification output parsing, fallback on parse failure, fast_path detection |
| `test_clarify_node.py` | Batched questions interrupt payload, response parsing |
| `test_pipeline_integration.py` | Full scenarios: greeting→fast_path, query→explore→respond, ambiguous→clarify→explore |

### Key Scenarios

1. **Fast path**: "hello" → intake → understand(greeting) → respond → END (2 LLM calls)
2. **Simple query**: "how many tasks in Alpha?" → understand → explore(get_project_details) → respond (3 calls)
3. **Clarification**: "show me the project" (3 projects exist) → understand(needs_clarification) → clarify(interrupt: "Which project? A) Alpha B) Beta C) Gamma") → user picks → explore → respond
4. **Complex**: "compare Alpha and Beta progress" → understand(multi_step) → explore(get_project_details×2) → synthesize(comparison table) → respond
5. **Write action**: "create task Fix Login in Alpha" → understand(action_request) → explore(get_project_details for context) → explore_tools(create_task → HITL interrupt) → respond
6. **Misclassification recovery**: fast_path but LLM calls tools → re-route to explore_tools

### Verification

```bash
cd fastapi-backend
pytest tests/test_agent_*.py tests/test_*_tools.py -v
ruff check app/ai/agent/
```

---

## Part F: Safety & Limits

| Limit | Value | Scope |
|-------|-------|-------|
| MAX_TOOL_CALLS | 50 | Total tool invocations across all phases |
| MAX_ITERATIONS | 10 | ReAct loops within explore phase |
| MAX_LLM_CALLS | 15 | Total LLM invocations across all phases |
| STREAM_OVERALL_TIMEOUT_S | 120 | Max SSE stream duration |
| STREAM_IDLE_TIMEOUT_S | 30 | Max gap between SSE chunks |

Rollback: `git revert` if needed (not in production, clean replace).
