# Phase 4: LangGraph Agent + Backend Tools

**Goal**: ReAct agent with all READ/WRITE tools. Testable via API (no frontend yet).

**Depends on**: Phase 1 (LLM providers), Phase 2 (retrieval), Phase 3 (graph search)
**Blocks**: Phase 5 (frontend needs agent backend)

---

## Task 4.1: Agent State & Graph

### New File: `fastapi-backend/app/ai/agent/__init__.py`

Empty init file for the agent package.

### New File: `fastapi-backend/app/ai/agent/graph.py`

```python
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

class AgentState(TypedDict):
    """
    State that flows through the agent graph.
    Persists across tool calls within a single conversation turn.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    accessible_app_ids: list[str]      # User's accessible applications
    accessible_project_ids: list[str]  # User's accessible projects


SYSTEM_PROMPT = """You are Blair, the PM Desktop AI assistant. You help users understand their projects, \
tasks, knowledge base, and relationships between them.

Be friendly, helpful, and proactive with suggestions. When presenting data, be concise but include \
key details. When you find related information, mention it proactively.

You have access to the user's applications, projects, tasks, and knowledge base documents \
(including both regular documents and canvas documents). You can also create tasks, update statuses, \
and create documents when the user asks — but always confirm before taking action.

Guidelines:
- When asked about projects or tasks, use the appropriate tools to fetch real data
- When asked to search knowledge, use query_knowledge for broad searches
- When asked about entity relationships, use query_entities for graph traversal
- For write operations (create task, update status, etc.), always show what you plan to do and wait for confirmation
- If information spans multiple sources, synthesize it into a coherent answer
- ALWAYS include source references when citing information — provide document title, section heading, \
  and a brief snippet so the user can click through to the exact location
- If the user sends images, analyze them and respond based on what you see
- If you don't find relevant information, say so honestly rather than guessing
- You can understand and search content from both regular documents and canvas documents

Clarification guidelines:
- If the user's request is ambiguous or could mean multiple things, ASK for clarification \
  before proceeding. Use the request_clarification tool to present options when helpful.
- If you search the knowledge base but don't find enough information, ask the user to \
  provide more context — e.g., which project, which document, what time frame, etc.
- If the user mentions something vague like "the document" or "that task", ask which \
  specific one they mean — offer a few likely candidates based on context.
- When there are multiple possible interpretations, present them as concrete options \
  so the user can pick one quickly rather than re-typing their request.
- Don't over-ask: if you have enough information to give a useful answer, just answer. \
  Only clarify when the ambiguity would lead to a wrong or unhelpful response.
"""


def build_agent_graph(tools: list, checkpointer=None) -> CompiledGraph:
    """
    Build Blair's ReAct agent graph with human-in-the-loop support.

    Flow:
    1. agent_node: LLM decides to call a tool or respond
    2. If tool call → tools_node executes the tool
    3. If write tool → interrupt() pauses graph, sends INTERRUPT to frontend
    4. User approves/rejects → graph resumes via Command(resume=...)
    5. Tool result feeds back to agent_node
    6. Repeat until agent responds without tool calls → END

    agent_node ──┐
        ▲        │
        │        ▼ (has tool call?)
        │       / \
        │     yes   no → END
        │      │
        │      ▼
        │   tools_node
        │      │
        │      ▼ (is write tool?)
        │     / \
        │   yes   no ──┐
        │    │          │
        │    ▼          │
        │  INTERRUPT    │
        │  (wait for    │
        │   user)       │
        │    │          │
        └────┴──────────┘
    """

    async def agent_node(state: AgentState) -> dict:
        """
        Core LLM reasoning node.
        1. Get chat/vision provider from registry (user_id for override resolution)
        2. Build messages: [system_prompt] + state.messages
        3. Call LLM with tool bindings
        4. Return {"messages": [response]}
        """

    def should_continue(state: AgentState) -> str:
        """
        Check if the last message has tool calls.
        Returns "continue" (go to tools) or "end" (finish).
        """
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "continue"
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", should_continue, {
        "continue": "tools",
        "end": END
    })
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    # Compile with checkpointer for interrupt/resume support
    # The checkpointer persists state across interrupt() calls,
    # allowing the graph to pause (HITL) and resume when user responds.
    return graph.compile(checkpointer=checkpointer)
```

### Acceptance Criteria
- [ ] `AgentState` TypedDict defined with correct fields
- [ ] System prompt sets friendly, helpful tone
- [ ] Graph compiles without errors
- [ ] ReAct loop: agent → tools → agent → ... → END
- [ ] `should_continue` correctly detects tool calls
- [ ] Maximum iterations configurable (prevent infinite loops)

---

## Task 4.2: READ Tools

### New File: `fastapi-backend/app/ai/agent/tools_read.py`

All read tools — these never modify data and don't require user confirmation.

### Tool: `query_knowledge`

```python
@tool
async def query_knowledge(
    query: str,
    application_id: str | None = None,
    project_id: str | None = None
) -> str:
    """
    Search the knowledge base for relevant documents and content.
    Use this when the user asks about documentation, specifications,
    meeting notes, or any written content.

    Args:
        query: The search query (natural language)
        application_id: Optional - limit search to specific application
        project_id: Optional - limit search to specific project
    """
    # 1. Get user's scope from AgentState
    # 2. Call HybridRetrievalService.retrieve()
    # 3. Format results as readable text with document titles and snippets
    # 4. Build SourceReference list for each retrieval result:
    #    - document_id, document_title, document_type ("document" or "canvas")
    #    - heading_context (for scroll-to navigation)
    #    - chunk_text (for text highlighting)
    #    - score, source_type ("semantic", "keyword", "fuzzy", "graph")
    # 5. Return ToolResultWithSources (text for LLM + sources for frontend)
    # 6. Sources attached to STATE_SNAPSHOT AG-UI event for frontend rendering
```

### Tool: `query_entities`

```python
@tool
async def query_entities(
    query: str,
    entity_name: str | None = None,
    entity_type: str | None = None
) -> str:
    """
    Search the knowledge graph for entities, relationships, and connections
    between concepts, people, systems, or any entity mentioned in documents.
    Use this when the user asks about what is known about a specific thing,
    how things relate to each other, or who works on what.

    Args:
        query: The search query (natural language)
        entity_name: Optional - get full context for a specific named entity
        entity_type: Optional - filter by type: "system", "person", "team",
                     "technology", "concept", "project"
    """
    # 1. If entity_name provided:
    #    a. Find entity by name via KnowledgeGraphService.search_entities()
    #    b. Get full context via KnowledgeGraphService.get_entity_context()
    #    c. Include relationships (outgoing + incoming) and source documents
    # 2. Else:
    #    a. Search entities matching query
    #    b. For top results, include relationship summaries
    # 3. Format as readable text:
    #    - Entity name, type, description
    #    - Key relationships: "depends_on Auth Service", "maintained_by Backend Team"
    #    - Source documents with snippets
```

### Tool: `get_projects`

```python
@tool
async def get_projects(
    application_id: str,
    status: str | None = None
) -> str:
    """
    List projects in an application with their completion percentage.
    Use this when the user asks about project status or wants an overview.

    Args:
        application_id: The application UUID
        status: Optional filter - "active", "completed", "archived"
    """
    # 1. Validate user has access to application_id (check AgentState.accessible_app_ids)
    # 2. Query Project + ProjectTaskStatusAgg models
    # 3. Calculate completion % from task status aggregates
    # 4. Format as table: Project Name | Status | Tasks (done/total) | % Complete
```

### Tool: `get_tasks`

```python
@tool
async def get_tasks(
    project_id: str,
    status: str | None = None,
    assignee: str | None = None,
    overdue_only: bool = False
) -> str:
    """
    List tasks in a project with optional filters.
    Use this when the user asks about specific tasks or task status.

    Args:
        project_id: The project UUID
        status: Optional filter - "todo", "in_progress", "done", etc.
        assignee: Optional filter - user name or ID
        overdue_only: If true, only return tasks past their due date
    """
    # 1. Validate project access via AgentState.accessible_project_ids
    # 2. Query Task model with filters
    # 3. Format: Task Key | Title | Status | Assignee | Due Date | Priority
```

### Tool: `get_task_detail`

```python
@tool
async def get_task_detail(task_id: str) -> str:
    """
    Get full details for a specific task including checklists, comments,
    and activity history.

    Args:
        task_id: The task UUID
    """
    # 1. Load task with selectinload (checklists, comments, assignee)
    # 2. Validate access
    # 3. Format complete task details including:
    #    - Title, description, status, priority
    #    - Assignee, reporter
    #    - Due date, created/updated timestamps
    #    - Checklist items (checked/unchecked)
    #    - Recent comments (last 5)
```

### Tool: `get_project_status`

```python
@tool
async def get_project_status(project_id: str) -> str:
    """
    Get aggregated project metrics: task counts by status,
    completion percentage, overdue count, and team activity.

    Args:
        project_id: The project UUID
    """
    # 1. Validate access
    # 2. Query ProjectTaskStatusAgg for task distribution
    # 3. Count overdue tasks (due_date < now())
    # 4. Format dashboard-style summary:
    #    - Todo: N | In Progress: N | Done: N
    #    - Completion: XX%
    #    - Overdue: N tasks
    #    - Recent activity: last 5 task updates
```

### Tool: `get_overdue_tasks`

```python
@tool
async def get_overdue_tasks(
    application_id: str | None = None
) -> str:
    """
    Get all tasks that are past their due date across accessible projects.
    Use this when the user asks about deadlines, late work, or overdue items.

    Args:
        application_id: Optional - limit to specific application
    """
    # 1. Resolve scope (all accessible or specific app)
    # 2. Query: Task.due_date < now() AND Task.status NOT IN ('done', 'cancelled')
    # 3. Group by project
    # 4. Format: Project → Task Key | Title | Due Date | Days Overdue | Assignee
```

### Tool: `get_team_members`

```python
@tool
async def get_team_members(
    application_id: str
) -> str:
    """
    List members of an application and their project assignments.
    Use this when the user asks about team composition or who works on what.

    Args:
        application_id: The application UUID
    """
    # 1. Validate access
    # 2. Query ApplicationMember + ProjectMember models
    # 3. Format: Name | Role | Projects Assigned
```

### Tool: `understand_image`

```python
@tool
async def understand_image(
    attachment_id: str,
    question: str | None = None
) -> str:
    """
    Analyze an embedded image using vision AI. Use this when the user asks
    about a diagram, screenshot, chart, or any image in their documents.

    Args:
        attachment_id: The attachment UUID from the document
        question: Optional specific question about the image
    """
    # 1. Download image from MinIO via minio_service
    # 2. Get vision provider from registry
    # 3. Send to VisionProvider.describe_image() with prompt:
    #    - Default: "Describe this image in detail. If it contains a diagram,
    #      flowchart, or chart, describe its structure and data."
    #    - Custom: Use provided question
    # 4. Return description
```

### Tool: `request_clarification`

```python
@tool
async def request_clarification(
    question: str,
    options: list[str] | None = None,
    context: str | None = None
) -> str:
    """
    Ask the user a clarifying question when you need more information
    to provide a good answer. Use this when:
    - The request is ambiguous (e.g., "the project" but multiple exist)
    - Search results are insufficient and you need the user to narrow scope
    - Multiple valid interpretations exist and you want the user to pick one
    - You need specific details before performing a write action

    Do NOT use this for general conversation — only when ambiguity would
    lead to a wrong or unhelpful response.

    Args:
        question: The clarifying question to ask the user
        options: Optional list of suggested answers (shown as clickable buttons).
                 Keep to 2-4 options. If None, user gets free-text input only.
        context: Optional context explaining why you're asking (shown as subtitle)
    """
    # 1. Build clarification payload:
    clarification = {
        "type": "clarification",
        "question": question,
        "options": options,      # e.g., ["Project Alpha", "Project Beta", "All projects"]
        "context": context       # e.g., "I found 3 projects matching your description"
    }
    # 2. Call interrupt(clarification) — pauses agent, sends to frontend
    # 3. Frontend renders inline clarification card with options + free-text input
    # 4. User responds (clicks option or types answer)
    # 5. Agent resumes with Command(resume={"answer": "..."})
    # 6. Return the user's answer as the tool result
    response = interrupt(clarification)
    return response.get("answer", "")
```

**When to use `request_clarification` vs. just asking in text:**
- **Use the tool** when you want structured options (buttons) that the user can click
- **Use regular text** for simple open-ended follow-ups where options wouldn't help
- The tool creates a richer UX (inline card with buttons) vs. a plain text question

### RBAC Enforcement

Every tool MUST:
1. Extract `user_id`, `accessible_app_ids`, `accessible_project_ids` from `AgentState`
2. Validate the requested resource is within scope
3. Return "Access denied" message if not authorized (don't raise — let agent explain)

### Acceptance Criteria
- [ ] All 10 read tools defined with `@tool` decorator (9 data tools + request_clarification)
- [ ] Each tool has a clear docstring (used by LLM for tool selection)
- [ ] RBAC validated on every tool call
- [ ] Results formatted as readable text (not raw JSON)
- [ ] Source citations included where applicable
- [ ] Error cases return helpful messages (not stack traces)
- [ ] Tools are async and use database sessions properly

---

## Task 4.3: WRITE Tools (with confirmation)

### New File: `fastapi-backend/app/ai/agent/tools_write.py`

All write tools use LangGraph's `interrupt()` to pause and request user confirmation via AG-UI INTERRUPT event.

### Tool: `create_task`

```python
@tool
async def create_task(
    project_id: str,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    assignee_id: str | None = None
) -> str:
    """
    Create a new task in a project. Requires user confirmation.

    Args:
        project_id: The project UUID
        title: Task title
        description: Optional task description
        priority: Optional - "low", "medium", "high", "critical"
        assignee_id: Optional - user UUID to assign
    """
    # 1. Validate RBAC: user can create tasks in project
    #    Reuse PermissionService.can_edit_task() or similar
    # 2. Resolve project name for confirmation message
    # 3. Build confirmation:
    confirmation = {
        "action": "create_task",
        "details": f"Create task '{title}' in {project_name}",
        "data": {
            "project_id": project_id,
            "title": title,
            "description": description,
            "priority": priority,
            "assignee": assignee_name
        }
    }
    # 4. Call interrupt(confirmation) — pauses agent, sends to frontend
    # 5. On user approval (agent resumes):
    #    - Create task via existing task creation service/router logic
    #    - Return "Task '{title}' created in {project_name} (key: {task_key})"
    # 6. On user rejection:
    #    - Return "Task creation cancelled by user."
```

### Tool: `update_task_status`

```python
@tool
async def update_task_status(
    task_id: str,
    new_status: str
) -> str:
    """
    Change a task's status. Requires user confirmation.

    Args:
        task_id: The task UUID
        new_status: Target status - "todo", "in_progress", "in_review", "done"
    """
    # 1. Load task, validate RBAC
    # 2. Build confirmation:
    #    "Move '{task_key}: {title}' from {current_status} to {new_status}?"
    # 3. interrupt() → wait for approval
    # 4. On approval: update task status, return confirmation
    # 5. On rejection: return cancellation message
```

### Tool: `assign_task`

```python
@tool
async def assign_task(
    task_id: str,
    assignee_id: str
) -> str:
    """
    Assign or reassign a task to a team member. Requires user confirmation.

    Args:
        task_id: The task UUID
        assignee_id: The user UUID to assign
    """
    # 1. Load task and assignee details, validate RBAC
    # 2. Build confirmation:
    #    "Assign '{task_key}: {title}' to {assignee_name}?"
    # 3. interrupt() → wait for approval
    # 4. On approval: update assignment, return confirmation
    # 5. On rejection: return cancellation message
```

### Tool: `create_document`

```python
@tool
async def create_document(
    title: str,
    content: str,
    scope: str,
    scope_id: str,
    folder_id: str | None = None
) -> str:
    """
    Create a new knowledge base document. Requires user confirmation.

    Args:
        title: Document title
        content: Document content (markdown — will be converted to TipTap JSON)
        scope: "application", "project", or "personal"
        scope_id: UUID of the application or project (or user for personal)
        folder_id: Optional target folder UUID
    """
    # 1. Validate RBAC based on scope
    # 2. Build confirmation:
    #    "Create document '{title}' in {scope_name} ({folder_path})?"
    # 3. interrupt() → wait for approval
    # 4. On approval:
    #    a. Convert markdown to TipTap JSON
    #    b. Create document via document service
    #    c. Trigger embedding job
    #    d. Return "Document '{title}' created. [Link to document]"
    # 5. On rejection: return cancellation message
```

### Interrupt Pattern

```python
from langgraph.types import interrupt

# Inside any write tool:
response = interrupt({
    "type": "confirmation",
    "action": "create_task",
    "summary": "Create task 'Fix login bug' in Project Alpha",
    "details": { ... }
})

if response.get("approved"):
    # Execute the write operation
    ...
else:
    return "Action cancelled by user."
```

### Acceptance Criteria
- [ ] All 4 write tools use `interrupt()` for confirmation
- [ ] Confirmation includes human-readable action summary
- [ ] RBAC checked BEFORE presenting confirmation (don't confirm then deny)
- [ ] Successful writes return confirmation with created entity details
- [ ] Rejections return clear cancellation message
- [ ] All tools use existing service layer for mutations (don't bypass business logic)
- [ ] Task key generated correctly when creating tasks

---

## Task 4.4: RBAC Context Injection

### New File: `fastapi-backend/app/ai/agent/rbac_context.py`

```python
class AgentRBACContext:
    """
    Resolves and caches a user's accessible scope for agent tool calls.
    """

    @staticmethod
    async def build_agent_context(
        user_id: UUID,
        db: AsyncSession
    ) -> dict:
        """
        Resolve user's accessible applications and projects.

        Implementation:
        1. Check Redis cache: agent:rbac:{user_id}
           - If hit and < 30s old, return cached
        2. Call search_service._get_user_application_ids(user_id, db)
        3. Call search_service._get_projects_in_applications(app_ids, db)
        4. Cache in Redis with 30s TTL (same as search_service pattern)
        5. Return:
           {
             "user_id": str(user_id),
             "accessible_app_ids": [str(id) for id in app_ids],
             "accessible_project_ids": [str(id) for id in project_ids]
           }

        Reuse:
        - search_service._get_user_application_ids()
        - search_service._get_projects_in_applications()
        """

    @staticmethod
    def validate_app_access(
        application_id: str,
        context: dict
    ) -> bool:
        """Check if application_id is in user's accessible_app_ids."""
        return application_id in context["accessible_app_ids"]

    @staticmethod
    def validate_project_access(
        project_id: str,
        context: dict
    ) -> bool:
        """Check if project_id is in user's accessible_project_ids."""
        return project_id in context["accessible_project_ids"]
```

### Acceptance Criteria
- [ ] Context resolved from DB on cache miss
- [ ] Redis cache with 30s TTL
- [ ] Reuses existing search_service RBAC functions
- [ ] Validation helpers work for both app and project scope
- [ ] Cache key includes user_id for per-user isolation

---

## Task 4.5: CopilotKit CoAgents Bridge

### New File: `fastapi-backend/app/ai/agent/copilotkit_runtime.py`

```python
from copilotkit.integrations.fastapi import copilotkit_messages_router
from copilotkit import CopilotKitSDK, LangGraphAgent

def create_copilotkit_sdk(agent_graph) -> CopilotKitSDK:
    """
    Create CopilotKit SDK instance configured with our LangGraph agent.

    The SDK handles:
    - AG-UI protocol (messages, tool calls, interrupts)
    - SSE streaming
    - Tool call → LangGraph tool node mapping
    - Interrupt (confirmation) → AG-UI INTERRUPT event
    """
    sdk = CopilotKitSDK(
        agents=[
            LangGraphAgent(
                name="blair",
                description="Blair — PM Desktop AI Copilot for projects, tasks, and knowledge base",
                graph=agent_graph,
            )
        ]
    )
    return sdk


def get_copilotkit_router(sdk: CopilotKitSDK):
    """
    Get the FastAPI router for CopilotKit runtime.
    Mounts at /api/copilotkit.
    """
    return copilotkit_messages_router(sdk)
```

### Acceptance Criteria
- [ ] CopilotKit SDK initialized with LangGraph agent
- [ ] AG-UI protocol handled (messages, tool calls, interrupts)
- [ ] SSE streaming works through the SDK
- [ ] Router mountable on FastAPI app

---

## Task 4.5b: Human-in-the-Loop Architecture (AG-UI + CopilotKit + LangGraph)

This section details how Blair's human-in-the-loop experience works end-to-end. The goal is to feel **agentic and seamless** — users see Blair thinking, searching, and acting in real-time, with natural confirmation flows for write actions.

### AG-UI Protocol Event Flow

The AG-UI protocol defines the SSE events streamed from backend to frontend. CopilotKit translates these into React state updates.

```
User sends message
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend (LangGraph + CopilotKit SDK)                        │
│                                                             │
│  RUN_STARTED ──────────────────────────────────────────────▶│ Frontend shows "Blair is thinking..."
│      │                                                      │
│  agent_node: LLM reasons, decides to call a tool            │
│      │                                                      │
│  TOOL_CALL_START {tool: "query_knowledge", args: {...}} ──▶│ Frontend shows "Searching knowledge base..."
│      │                                                      │
│  tools_node: executes query_knowledge()                     │
│      │                                                      │
│  TOOL_CALL_END {tool: "query_knowledge", result: {...}} ──▶│ Frontend shows collapsible tool result card
│      │                                                      │
│  agent_node: LLM has tool result, generates response        │
│      │                                                      │
│  TEXT_MESSAGE_START ───────────────────────────────────────▶│ Frontend starts rendering response
│  TEXT_MESSAGE_CONTENT {delta: "Based on..."} ─────────────▶│ Frontend streams text character by character
│  TEXT_MESSAGE_CONTENT {delta: "the API docs..."} ─────────▶│
│  TEXT_MESSAGE_END ─────────────────────────────────────────▶│ Frontend finalizes message, shows source links
│      │                                                      │
│  STATE_SNAPSHOT {sources: [...], tool_calls: [...]} ──────▶│ Frontend receives structured metadata
│      │                                                      │
│  RUN_FINISHED ─────────────────────────────────────────────▶│ Frontend shows "Blair" idle
└─────────────────────────────────────────────────────────────┘
```

### Write Action Flow (HITL Interrupt)

When Blair decides to perform a write action (create task, update status, etc.), the flow uses LangGraph's `interrupt()` to pause and wait for user approval:

```
User: "Create a task to fix the login bug in Project Alpha"
      │
      ▼
  agent_node: LLM decides to call create_task tool
      │
  TOOL_CALL_START {tool: "create_task"} ──────────────────▶ Frontend: "Blair wants to create a task..."
      │
  create_task() runs:
    1. Validates RBAC ✓
    2. Resolves project name ✓
    3. Calls interrupt({...}) ◀── graph PAUSES here
      │
  AG-UI INTERRUPT event ──────────────────────────────────▶ Frontend renders INLINE confirmation card:
                                                            ┌──────────────────────────────────────┐
                                                            │ Blair wants to create a task:        │
                                                            │                                      │
                                                            │   Title: Fix login bug               │
                                                            │   Project: Project Alpha             │
                                                            │   Priority: High                     │
                                                            │                                      │
                                                            │   [Approve ✓]  [Reject ✗]           │
                                                            └──────────────────────────────────────┘

  User clicks [Approve ✓]
      │
  Frontend sends Command(resume={"approved": true}) ──────▶ LangGraph resumes from checkpoint
      │
  create_task() continues:
    4. Creates task via service layer
    5. Returns confirmation message
      │
  TOOL_CALL_END ──────────────────────────────────────────▶ Frontend: tool result card (task created)
      │
  agent_node: LLM generates response
      │
  TEXT_MESSAGE: "Done! I've created task PROJ-42: Fix login bug..." ▶ Frontend streams response
      │
  RUN_FINISHED ───────────────────────────────────────────▶ Frontend: idle
```

### Clarification Flow (HITL Clarification)

When Blair is uncertain about what the user means or can't find enough information, it uses the `request_clarification` tool to ask a follow-up question. This creates a seamless loop: Blair asks → user answers → Blair continues with the clarified intent.

```
User: "Show me the status of the project"
      │
      ▼
  agent_node: LLM searches for projects, finds 3 matching projects
      │
  TOOL_CALL_START {tool: "get_projects"} ──────────▶ Frontend: "Checking projects..."
      │
  TOOL_CALL_END ───────────────────────────────────▶ Found: Project Alpha, Project Beta, Project Gamma
      │
  agent_node: LLM sees ambiguity — 3 projects, user said "the project"
      │         Decides to call request_clarification
      │
  TOOL_CALL_START {tool: "request_clarification"} ─▶ Frontend: "Blair needs clarification..."
      │
  request_clarification() runs:
    1. Builds clarification payload
    2. Calls interrupt({...}) ◀── graph PAUSES here
      │
  AG-UI INTERRUPT event ───────────────────────────▶ Frontend renders INLINE clarification card:
                                                      ┌──────────────────────────────────────────────┐
                                                      │ Blair needs more info:                       │
                                                      │                                              │
                                                      │   "Which project did you mean?"              │
                                                      │                                              │
                                                      │   I found 3 projects matching your request   │
                                                      │                                              │
                                                      │   [Project Alpha]  [Project Beta]            │
                                                      │   [Project Gamma]  [All projects]            │
                                                      │                                              │
                                                      │   Or type your answer:                       │
                                                      │   [___________________________] [Send]       │
                                                      └──────────────────────────────────────────────┘

  User clicks [Project Alpha]  (or types "Alpha")
      │
  Frontend sends Command(resume={"answer": "Project Alpha"}) ──▶ LangGraph resumes
      │
  request_clarification() returns "Project Alpha"
      │
  TOOL_CALL_END ───────────────────────────────────▶ Frontend: clarification card updates to show answer
      │
  agent_node: LLM now knows which project — calls get_project_status("alpha-id")
      │
  (continues with normal tool execution flow...)
      │
  TEXT_MESSAGE: "Here's the status of Project Alpha: ..." ──▶ Frontend streams response
```

**Clarification scenarios that trigger `request_clarification`:**

| Scenario | Example User Input | Blair's Clarification |
|----------|-------------------|----------------------|
| Ambiguous reference | "Update the task" | "Which task? I found: [PROJ-12], [PROJ-15], [PROJ-18]" |
| Multiple scopes | "Search for API docs" | "Search in which scope? [All applications], [Project Alpha], [Personal docs]" |
| Insufficient context | "Create a document about that" | "What should the document cover? Give me a topic or a brief outline" |
| Vague search results | "Tell me about the auth flow" | "I found limited info. Can you clarify: [Login flow], [OAuth2 setup], [API key auth]?" |
| Missing details for write | "Make a task" | "I need a few details: What's the task title and which project?" |

**Key differences from confirmation cards:**

| Aspect | Confirmation (write actions) | Clarification (questions) |
|--------|------------------------------|--------------------------|
| Trigger | Blair attempts a write action | Blair encounters ambiguity |
| User response | Approve / Reject (binary) | Click option / Type answer (open) |
| Card buttons | "Approve" + "Reject" | Suggested options + free-text input |
| After response | Action executes or cancels | Blair continues reasoning |
| Visual style | Action summary with details | Question with options |

### Key HITL Design Decisions

1. **Inline confirmation, NOT modal dialog**: Confirmation cards render directly in the chat message stream (not as a modal that blocks the UI). This keeps the conversation flow natural and doesn't jar the user.

2. **Confirmation card in the chat stream**: The card appears as a special message type between Blair's reasoning and the final response. It looks like part of the conversation, not a system dialog.

3. **RBAC check BEFORE interrupt**: Blair validates permissions before presenting the confirmation. If the user doesn't have permission, Blair says so in the chat — no confirmation card is shown.

4. **Checkpoint persistence**: LangGraph's checkpointer stores the full agent state at the interrupt point. This means:
   - User can take time to review (no timeout)
   - Page navigation doesn't lose the pending action (within session)
   - If the user closes the sidebar and reopens, the pending confirmation is still there

5. **Progressive disclosure**: During tool execution, the frontend shows:
   - Tool name + animated spinner while executing
   - Collapsible result card after completion (summary visible, details expandable)
   - Multiple sequential tool calls each get their own card

6. **CopilotKit integration points**:
   ```typescript
   // useCopilotAction — register client-side actions Blair can reference
   useCopilotAction({
     name: "navigate_to_document",
     description: "Navigate the user to a specific document",
     parameters: [{ name: "documentId", type: "string" }],
     handler: async ({ documentId }) => {
       onNavigate({ type: "document", documentId })
     }
   })
   ```

### LangGraph Checkpointer Configuration

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Use the existing PostgreSQL database for checkpoints
# (no new infrastructure needed)
checkpointer = AsyncPostgresSaver.from_conn_string(settings.database_url)

# Initialize checkpoint tables (one-time setup in migration)
# Creates: checkpoints, checkpoint_writes tables

agent_graph = build_agent_graph(
    tools=all_tools,
    checkpointer=checkpointer
)
```

### Time Travel / Conversation Rollback

LangGraph's checkpointer stores the full agent state at every node transition — not just at interrupt points. This means every step (each tool call, each LLM response) creates a checkpoint that can be replayed. Blair supports **time travel**: users can rewind the conversation to any previous point and branch from there.

**How it works:**

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Every node execution creates a checkpoint:
#   agent_node → checkpoint_1
#   tools_node → checkpoint_2
#   agent_node → checkpoint_3  (response generated)
#   ... (user sends new message)
#   agent_node → checkpoint_4
#   tools_node → checkpoint_5
#   agent_node → checkpoint_6  (response generated)
#
# Each checkpoint stores:
#   - Full message history up to that point
#   - Agent state (user_id, accessible_app_ids, etc.)
#   - The node that was just executed
#   - Timestamp

# List all checkpoints for a conversation thread:
async def list_checkpoints(thread_id: str) -> list[CheckpointSummary]:
    """
    Returns all checkpoints for a conversation, ordered by timestamp.
    Each checkpoint includes:
    - checkpoint_id: unique ID for this state
    - thread_id: the conversation thread
    - timestamp: when this checkpoint was created
    - node: which graph node produced this checkpoint
    - message_count: number of messages at this point
    """
    checkpoints = []
    async for checkpoint_tuple in checkpointer.alist(
        config={"configurable": {"thread_id": thread_id}}
    ):
        checkpoints.append(CheckpointSummary(
            checkpoint_id=checkpoint_tuple.checkpoint["id"],
            thread_id=thread_id,
            timestamp=checkpoint_tuple.checkpoint["ts"],
            node=checkpoint_tuple.metadata.get("source", "unknown"),
            message_count=len(checkpoint_tuple.checkpoint["channel_values"].get("messages", [])),
        ))
    return checkpoints


# Replay from a specific checkpoint (fork the conversation):
async def replay_from_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    new_message: str | None = None
) -> AsyncIterator:
    """
    Resume the agent from a previous checkpoint.

    If new_message is provided:
      - The conversation branches from that point
      - All messages AFTER the checkpoint are discarded
      - The new message is processed as if the user sent it at that point

    If new_message is None:
      - Simply returns the state at that checkpoint (for preview)
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id  # ← This is the key: replay from here
        }
    }

    if new_message:
        # Add the new message and run the agent from this point
        input_state = {"messages": [HumanMessage(content=new_message)]}
        async for event in agent_graph.astream(input_state, config=config):
            yield event
    else:
        # Just return the state at this checkpoint
        state = await agent_graph.aget_state(config)
        yield state
```

**Time travel API endpoints:**

Add to `fastapi-backend/app/routers/ai_chat.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ai/chat/history/{thread_id}` | GET | List checkpoints (conversation timeline) |
| `/api/ai/chat/replay` | POST | Replay from a checkpoint (fork conversation) |
| `/api/ai/chat/state/{thread_id}` | GET | Get current conversation state |

```python
class ReplayRequest(BaseModel):
    thread_id: str
    checkpoint_id: str           # Which point to rewind to
    message: str | None = None   # Optional new message to send from that point

@router.get("/chat/history/{thread_id}")
async def get_conversation_history(
    thread_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Returns the conversation timeline with all checkpoints.
    Used by the frontend to show the rollback UI.
    Only returns checkpoints for 'agent' node (user-visible turns),
    not internal tool execution checkpoints.
    """
    checkpoints = await list_checkpoints(thread_id)
    # Filter to user-visible turns (agent responses, not internal tool calls)
    visible_checkpoints = [
        cp for cp in checkpoints
        if cp.node == "agent" and cp.message_count > 0
    ]
    return {"checkpoints": visible_checkpoints}

@router.post("/chat/replay")
async def replay_conversation(
    request: ReplayRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Rewind to a previous checkpoint and optionally send a new message.
    Creates a conversation branch — the original history is preserved
    but the active thread now continues from the replayed checkpoint.
    """
    # Stream the replayed conversation
    return EventSourceResponse(
        replay_from_checkpoint(
            request.thread_id,
            request.checkpoint_id,
            request.message
        )
    )
```

**Frontend UX for time travel:**

The conversation timeline is accessible via a subtle "rewind" affordance in the chat sidebar. Users can:

1. **Hover over any Blair message** → a small rewind icon appears in the message header
2. **Click the rewind icon** → the conversation view visually "collapses" all messages after that point (dimmed/crossed out, not deleted)
3. **The chat input re-activates** at that point in the conversation, with a banner: "Rewound to: [message preview]. Type a new message to branch from here, or click Cancel to restore."
4. **User types a new message** → Blair processes it from the rewound state (fork)
5. **Or user clicks Cancel** → conversation restores to the latest state

```
┌────────────────────────────────────────────┐
│ Blair                        [New] [X]     │
├────────────────────────────────────────────┤
│                                            │
│ You: What tasks are overdue?               │
│                                            │
│ Blair: Found 3 overdue tasks:    [⟲]      │  ← Rewind icon on hover
│   1. PROJ-12: Fix login...                 │
│   2. PROJ-15: Update API...               │
│                                            │
│ You: Create a task for each one            │  ← Messages after rewind point
│                                            │     are dimmed/collapsed
│ Blair: Created 3 tasks...        [⟲]      │
│                                            │
│ ┌────────────────────────────────────────┐ │
│ │ ⟲ Rewound to: "Found 3 overdue..."    │ │  ← Rewind banner
│ │     Type a new message to branch.      │ │
│ │                          [Cancel]      │ │
│ └────────────────────────────────────────┘ │
│                                            │
│ [Ask Blair anything...           ] [Send]  │  ← Input active at rewind point
└────────────────────────────────────────────┘
```

**Important design decisions:**

1. **Non-destructive**: Time travel doesn't delete history — it creates a branch. The original conversation can be restored via Cancel.
2. **Session-scoped threads**: Thread IDs are generated per session. Since chat history is session-only (clears on app close), checkpoints are cleaned up when the session ends.
3. **Checkpoint cleanup**: Run a periodic cleanup (hourly) to delete checkpoints older than 24 hours from the database, since chat is session-only.
4. **Only visible turns**: The timeline UI only shows checkpoints at agent response boundaries (not internal tool execution steps), keeping the UX clean.
5. **Branch, don't overwrite**: When replaying, LangGraph creates a new branch from the checkpoint. This means the checkpointer naturally handles the fork — no manual state manipulation needed.

### Acceptance Criteria
- [ ] AG-UI events stream in correct order (RUN_STARTED → TOOL_CALL_* → TEXT_MESSAGE_* → RUN_FINISHED)
- [ ] Write tool `interrupt()` pauses graph and sends INTERRUPT event
- [ ] Frontend renders inline confirmation card (not modal)
- [ ] User approval resumes graph via `Command(resume=...)`
- [ ] User rejection returns cancellation message and graph completes
- [ ] Clarification `interrupt()` pauses graph and sends INTERRUPT event with type "clarification"
- [ ] Frontend renders inline clarification card with suggested options + free-text input
- [ ] User clicking an option or typing an answer resumes graph via `Command(resume={"answer": "..."})`
- [ ] Blair continues reasoning with the clarified answer (not just echoing it back)
- [ ] Checkpointer persists state across interrupt (survives sidebar close/reopen)
- [ ] RBAC validated before interrupt (no confirmation for unauthorized actions)
- [ ] Progressive disclosure: tool execution shown in real-time with collapsible cards
- [ ] Multiple sequential tool calls each displayed independently
- [ ] CopilotKit `useCopilotAction` enables client-side navigation actions
- [ ] Checkpoints created at every agent node transition
- [ ] `/chat/history/{thread_id}` returns list of user-visible checkpoints
- [ ] `/chat/replay` replays from a specific checkpoint with optional new message
- [ ] Time travel creates a branch (non-destructive, original history preserved)
- [ ] Checkpoint cleanup removes stale data (>24h) automatically

---

## Task 4.5c: Structured Source References

Blair must include structured, clickable source references in every response that cites knowledge base content. These references enable the frontend to navigate users directly to the cited content and highlight the relevant text.

### Source Reference Format

Every tool that retrieves content (query_knowledge, query_entities) returns structured source references alongside the text response:

```python
@dataclass
class SourceReference:
    """A single citation from a knowledge retrieval result."""
    document_id: str         # UUID of the source document
    document_title: str      # Human-readable title
    document_type: str       # "document" or "canvas"
    heading_context: str | None   # Section heading (for scroll-to)
    chunk_text: str          # The exact cited text snippet (for highlighting)
    chunk_index: int         # Position in document (for ordering)
    score: float             # Retrieval relevance score
    source_type: str         # "semantic", "keyword", "fuzzy", "graph"
    entity_name: str | None  # If from entity search, the matched entity

class ToolResultWithSources:
    """Wrapper for tool results that include source citations."""
    text: str                          # Formatted text response for the LLM
    sources: list[SourceReference]     # Structured references for frontend
```

### How Sources Flow Through the System

```
1. User asks: "How does the payment system work?"
      │
2. Blair calls query_knowledge("payment system")
      │
3. HybridRetrievalService returns:
   - Chunk from "API Architecture" doc, heading "Payment Flow", text "The payment..."
   - Chunk from "Sprint 12 Notes" doc, heading "Backend Updates", text "Refactored payment..."
   - Entity match: "Payment Service" from knowledge graph
      │
4. query_knowledge tool formats text for LLM AND returns SourceReference list
      │
5. LLM generates response citing the sources
      │
6. Agent includes sources in STATE_SNAPSHOT AG-UI event:
   STATE_SNAPSHOT {
     sources: [
       {document_id: "abc", document_title: "API Architecture",
        heading_context: "Payment Flow", chunk_text: "The payment service...",
        source_type: "semantic"},
       {document_id: "def", document_title: "Sprint 12 Notes",
        heading_context: "Backend Updates", chunk_text: "Refactored payment...",
        source_type: "keyword"},
       {document_id: "ghi", document_title: "API Architecture",
        heading_context: "System Entities", entity_name: "Payment Service",
        source_type: "graph"}
     ]
   }
      │
7. Frontend renders clickable source links at bottom of Blair's message
```

### Source Reference Display in Chat

At the bottom of every Blair message that cites content:

```
┌──────────────────────────────────────────────────────┐
│ Blair: The payment system uses a two-phase commit     │
│ pattern. The Payment Service authenticates through    │
│ the Auth Service before processing transactions...    │
│                                                       │
│ ┌───────────────────────────────────────────────────┐ │
│ │ Sources:                                          │ │
│ │  📄 API Architecture → Payment Flow       [0.92] │ │  ← clickable
│ │  📄 Sprint 12 Notes → Backend Updates     [0.85] │ │  ← clickable
│ │  🔗 Entity: Payment Service (3 relations) [0.78] │ │  ← clickable
│ └───────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Acceptance Criteria
- [ ] `query_knowledge` returns `ToolResultWithSources` (not just text)
- [ ] `query_entities` returns `ToolResultWithSources` with entity-linked sources
- [ ] `SourceReference` includes document_id, title, heading, chunk_text, score, source_type
- [ ] Sources passed via `STATE_SNAPSHOT` AG-UI event to frontend
- [ ] Source type labels distinguish retrieval method (semantic, keyword, fuzzy, graph)
- [ ] Relevance scores included for transparency
- [ ] Canvas documents include element ID in source reference for element-level navigation

---

## Task 4.6: Chat Router

### New File: `fastapi-backend/app/routers/ai_chat.py`

**Prefix**: `/api/ai`

### Endpoints

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/chat` | POST | Non-streaming chat (for testing/simple clients) | Any authenticated user |
| `/chat/stream` | POST | SSE streaming with AG-UI events | Any authenticated user |

Additionally, the CopilotKit endpoint:

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/copilotkit` | POST | CopilotKit runtime endpoint (mounts CoAgents SDK) | Any authenticated user |

### Request Schema

```python
class ChatImageAttachment(BaseModel):
    """Image attached to a chat message by the user (paste or upload)."""
    data: str              # Base64-encoded image data
    media_type: str        # "image/png", "image/jpeg", "image/gif", "image/webp"
    filename: str | None = None  # Original filename if uploaded

class ChatRequest(BaseModel):
    message: str
    images: list[ChatImageAttachment] = []  # Images pasted/uploaded by user
    conversation_history: list[dict] = []   # Previous messages for context
    application_id: str | None = None       # Optional scope hint
```

### Multimodal Message Handling

When the user sends images with their message, the chat endpoint must:

1. **Build multimodal content blocks** for the LLM message:
   ```python
   # Convert ChatRequest into LangChain HumanMessage with mixed content
   content_blocks = [{"type": "text", "text": request.message}]
   for img in request.images:
       content_blocks.append({
           "type": "image_url",
           "image_url": {
               "url": f"data:{img.media_type};base64,{img.data}"
           }
       })
   # For Anthropic format, use "image" content block type instead
   ```

2. **Require vision-capable model**: If images are present, the agent node must use a vision-capable model (GPT-4o, Claude, or llava for Ollama). The `ProviderRegistry.get_vision_provider(user_id)` handles resolution.

3. **Provider-specific formatting**: Each provider expects images in slightly different format:
   - **OpenAI**: `image_url` content block with data URI
   - **Anthropic**: `image` content block with `source.type="base64"`
   - **Ollama**: `images` array in the message payload

   The provider adapter (Task 1.4) handles this translation internally — the agent graph always passes a normalized multimodal message, and the provider's `chat_completion()` method converts to the provider-specific format.

4. **Size limits**: Max 5 images per message, max 10MB per image. Validated in the chat router before passing to the agent.

### Non-Streaming (`POST /chat`)

```python
@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    1. Validate image attachments (count, size)
    2. Build RBAC context for user
    3. Build multimodal HumanMessage if images present
    4. Initialize agent state with user's messages + context
    5. Run agent graph to completion
    6. Return final response text
    """
    return {"response": agent_response, "tool_calls": tool_calls_made}
```

### Streaming (`POST /chat/stream`)

```python
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    1. Build RBAC context
    2. Initialize agent state
    3. Stream agent execution as SSE events:
       - TEXT_DELTA: Partial response text
       - TOOL_CALL_START: Agent invoked a tool
       - TOOL_CALL_END: Tool returned result
       - INTERRUPT: Write tool requesting confirmation
       - END: Agent finished
    4. Return EventSourceResponse
    """
    return EventSourceResponse(stream_agent(state))
```

### CopilotKit Endpoint

```python
# Mount CopilotKit router
copilotkit_sdk = create_copilotkit_sdk(agent_graph)
copilotkit_router = get_copilotkit_router(copilotkit_sdk)

# In main.py:
app.include_router(copilotkit_router, prefix="/api/copilotkit")
```

### Modify: `fastapi-backend/app/main.py`

Mount both routers:
```python
from app.routers import ai_chat
app.include_router(ai_chat.router)
# CopilotKit router mounted separately (see copilotkit_runtime.py)
```

### Acceptance Criteria
- [ ] Non-streaming endpoint returns complete response
- [ ] Streaming endpoint sends proper SSE events
- [ ] RBAC context injected into agent state
- [ ] CopilotKit endpoint handles AG-UI protocol
- [ ] Authentication required on all endpoints
- [ ] Conversation history properly formatted as LangChain messages
- [ ] Multimodal messages (text + images) handled correctly
- [ ] Image validation: max 5 per message, max 10MB each, allowed MIME types only
- [ ] Vision-capable model auto-selected when images are present
- [ ] Provider-specific image formatting handled by adapters
- [ ] Error responses don't leak internal details

---

## Task 4.7: Dependencies

### Modify: `fastapi-backend/requirements.txt`

Add:
```
langgraph>=1.0.0
langchain-core>=0.3.0
langchain-openai>=0.3.0
langchain-anthropic>=0.3.0
copilotkit>=0.8.0
```

### Acceptance Criteria
- [ ] `pip install -r requirements.txt` succeeds
- [ ] No version conflicts with all previous phase dependencies

---

## Task 4.8: Tests

### New File: `fastapi-backend/tests/test_agent_tools_read.py`

```
test_query_knowledge_returns_results
test_query_knowledge_respects_scope_filter
test_query_knowledge_rbac_denied
test_query_entities_returns_entities
test_query_entities_entity_context
test_query_entities_filters_by_type
test_query_entities_traverses_relationships
test_get_projects_returns_list_with_completion
test_get_projects_filters_by_status
test_get_projects_rbac_denied
test_get_tasks_returns_filtered_list
test_get_tasks_overdue_only
test_get_task_detail_includes_checklists
test_get_task_detail_includes_comments
test_get_project_status_returns_metrics
test_get_overdue_tasks_across_projects
test_get_overdue_tasks_scoped_to_app
test_get_team_members_returns_assignments
test_understand_image_returns_description
test_request_clarification_with_options
test_request_clarification_free_text_response
test_request_clarification_resumes_agent_reasoning
test_clarification_after_insufficient_search_results
test_clarification_for_ambiguous_entity_reference
```

### New File: `fastapi-backend/tests/test_agent_tools_write.py`

```
test_create_task_with_confirmation
test_create_task_rejection_cancels
test_create_task_rbac_denied
test_update_task_status_with_confirmation
test_update_task_status_rejection_cancels
test_assign_task_with_confirmation
test_assign_task_rbac_denied
test_create_document_with_confirmation
test_create_document_rejection_cancels
test_write_tool_interrupt_format
```

### New File: `fastapi-backend/tests/test_agent_rbac.py`

```
test_build_context_resolves_apps
test_build_context_resolves_projects
test_build_context_caches_in_redis
test_build_context_cache_expires
test_validate_app_access_allowed
test_validate_app_access_denied
test_validate_project_access_allowed
test_validate_project_access_denied
test_tool_with_unauthorized_app_returns_denied
test_tool_with_unauthorized_project_returns_denied
test_cross_app_isolation
```

### New File: `fastapi-backend/tests/test_agent_chat.py`

Integration test — send a message, get a response:

```
test_chat_endpoint_returns_response
test_chat_endpoint_requires_auth
test_chat_stream_sends_sse_events
test_chat_stream_includes_tool_calls
test_chat_handles_write_tool_interrupt
test_chat_conversation_history_maintained
test_chat_with_image_attachment
test_chat_with_multiple_images
test_chat_image_validation_max_count
test_chat_image_validation_max_size
test_chat_image_validation_mime_type
test_chat_image_selects_vision_model
test_copilotkit_endpoint_handles_agui
test_chat_history_returns_checkpoints
test_chat_history_filters_visible_turns_only
test_chat_replay_from_checkpoint
test_chat_replay_with_new_message_branches
test_chat_replay_preserves_original_history
test_chat_replay_requires_auth
test_checkpoint_cleanup_removes_stale_data
```

### Acceptance Criteria
- [ ] All tests pass
- [ ] LLM calls mocked (no real API calls in tests)
- [ ] Tool tests verify correct input parsing and output format
- [ ] RBAC tests verify isolation between users
- [ ] Integration tests verify full request → agent → response flow
- [ ] Write tool tests verify interrupt mechanism

---

## Verification Checklist

```bash
cd fastapi-backend

# 1. Install dependencies
pip install -r requirements.txt

# 2. Test Blair via API (no frontend needed)
# Non-streaming:
curl -X POST http://localhost:8001/api/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What tasks are overdue in my projects?"}'
# Should respond as "Blair" with structured source references

# 3. Test streaming:
curl -N -X POST http://localhost:8001/api/ai/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Summarize project Alpha"}'
# Should see AG-UI SSE events: RUN_STARTED → TOOL_CALL_* → TEXT_MESSAGE_* → STATE_SNAPSHOT → RUN_FINISHED

# 4. Test write tool (creates HITL interrupt):
curl -X POST http://localhost:8001/api/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a task called Review AI implementation in my project"}'
# Should see INTERRUPT event with inline confirmation data

# 5. Test with image attachment:
# Send base64 image in the images array
curl -X POST http://localhost:8001/api/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What does this diagram show?", "images": [{"data": "...", "media_type": "image/png"}]}'
# Blair should describe the image content

# 6. Test CopilotKit endpoint:
curl -X POST http://localhost:8001/api/copilotkit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
# Blair should respond with greeting

# 7. Test clarification (ambiguous request):
curl -X POST http://localhost:8001/api/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me the project status"}'
# If multiple projects exist, should see INTERRUPT event with type "clarification"
# and suggested project options

# 8. Test time travel — list conversation checkpoints:
curl http://localhost:8001/api/ai/chat/history/$THREAD_ID \
  -H "Authorization: Bearer $TOKEN"
# Should return list of checkpoints with timestamps and message counts

# 9. Test time travel — replay from a checkpoint:
curl -X POST http://localhost:8001/api/ai/chat/replay \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "$THREAD_ID", "checkpoint_id": "$CP_ID", "message": "Try a different question"}'
# Should stream a response from the rewound state

# 10. Run all agent tests
pytest tests/test_agent_tools_read.py tests/test_agent_tools_write.py \
       tests/test_agent_rbac.py tests/test_agent_chat.py -v
```
