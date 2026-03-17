"""Utility tools for Blair AI agent.

Cross-cutting tools that do not belong to a single domain: image
analysis, SQL queries, and user clarification requests.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import select

from ....models.attachment import Attachment
from ....models.comment import Comment
from ....models.task import Task
from .context import _check_project_access, _get_ctx, _get_user_id
from .helpers import _get_tool_session, _truncate, _wrap_user_content

logger = logging.getLogger(__name__)


@tool
async def sql_query(question: str) -> str:
    """Query the project database to answer structural questions.

    LAST RESORT -- use only when no specific tool covers the query.
    Prefer list_tasks, list_projects, get_task_detail, etc. for standard
    look-ups.  Use this for ad-hoc analytical questions like cross-project
    comparisons, custom aggregations, or unusual joins.

    Args:
        question: Natural language question (will be converted to SQL).
    """
    if not question or not question.strip():
        return "Error: question cannot be empty."
    if len(question) > 2000:
        return "Error: question too long (max 2000 characters)."

    from ...agent_tools import sql_query_tool

    user_id = _get_user_id()
    ctx = _get_ctx()
    provider_registry = ctx.get("provider_registry")
    db_session_factory = ctx.get("db_session_factory")

    try:
        async with _get_tool_session() as db:
            result = await sql_query_tool(
                question=question,
                user_id=user_id,
                db=db,
                provider_registry=provider_registry,
                db_factory=db_session_factory,
            )

        if not result.success:
            return f"SQL query failed: {result.error}"

        return _truncate(result.data or "Query returned no data.")

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp
        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning("sql_query failed: %s: %s", type(exc).__name__, exc)
        return "Error executing query. Please try again."


@tool
async def understand_image(
    attachment_id: str,
    question: str | None = None,
) -> str:
    """Analyze an image attachment using vision AI.

    Use this when the user asks about a diagram, screenshot, chart,
    or any image stored as an attachment in their documents or tasks.

    Args:
        attachment_id: The attachment UUID.
        question: Optional specific question about the image.
    """
    if not attachment_id or len(attachment_id) > 64:
        return "Invalid attachment_id."

    from ....services.minio_service import MinIOService

    ctx = _get_ctx()
    provider_registry = ctx.get("provider_registry")

    try:
        async with _get_tool_session() as db:
            # Load attachment record
            att_result = await db.execute(
                select(Attachment).where(
                    Attachment.id == UUID(attachment_id)
                )
            )
            attachment = att_result.scalar_one_or_none()

            if attachment is None:
                return f"Attachment not found: {attachment_id}"

            # RBAC -- check that user can access the entity
            if attachment.task_id:
                task_result = await db.execute(
                    select(Task.project_id).where(
                        Task.id == attachment.task_id
                    )
                )
                project_id = task_result.scalar_one_or_none()
                if not project_id or not _check_project_access(str(project_id)):
                    return "Access denied: you do not have access to this attachment's project."
            elif attachment.comment_id is not None:
                comment_result = await db.execute(
                    select(Comment.task_id).where(
                        Comment.id == attachment.comment_id
                    )
                )
                comment_task_id = comment_result.scalar_one_or_none()
                if not comment_task_id:
                    return "Access denied: unable to verify access permissions for this attachment."
                task_result = await db.execute(
                    select(Task.project_id).where(
                        Task.id == comment_task_id
                    )
                )
                project_id = task_result.scalar_one_or_none()
                if not project_id or not _check_project_access(str(project_id)):
                    return "Access denied: you do not have access to this attachment's project."
            else:
                return "Access denied: unable to verify access permissions for this attachment."

            # Validate it is an image
            file_type = attachment.file_type or ""
            if not file_type.startswith("image/"):
                return (
                    f"Attachment '{attachment.file_name}' is not an image "
                    f"(type: {file_type}). Vision analysis requires an image file."
                )

            bucket = attachment.minio_bucket
            key = attachment.minio_key

            if not bucket or not key:
                return (
                    "Attachment has no storage reference. "
                    "The file may not have been uploaded successfully."
                )

            # Get vision provider while we have the DB session open
            vision_provider, model_id = await provider_registry.get_vision_provider(
                db, _get_user_id()
            )

        # Download outside the db session (only after confirming provider is available)
        minio_svc = MinIOService()
        image_bytes = minio_svc.download_file(bucket, key)

        # Build prompt
        prompt = question or (
            "Describe this image in detail. If it contains a diagram, "
            "flowchart, or chart, describe its structure and data."
        )

        # Call vision provider
        description = await vision_provider.describe_image(
            image_bytes=image_bytes,
            prompt=prompt,
            model=model_id,
        )

        return _truncate(description)

    except Exception as exc:
        from langgraph.errors import GraphBubbleUp
        if isinstance(exc, GraphBubbleUp):
            raise
        logger.warning(
            "understand_image failed: %s: %s", type(exc).__name__, exc
        )
        return "Error analyzing image. Please try again."


@tool
async def list_capabilities() -> str:
    """List all Blair capabilities. Call this when the user asks 'What can you do?',
    'Help', or wants to know available features.

    Returns a structured overview of all available capabilities.
    """
    return (
        "## Blair AI Copilot -- Capabilities\n"
        "\n"
        "### Workspaces\n"
        "- **Create** new workspaces with name and description\n"
        "- **Update** workspace name or description\n"
        "- **Delete** workspaces (with all projects, tasks, and documents)\n"
        "- **Manage members**: add, update roles, or remove workspace members\n"
        "\n"
        "### Projects\n"
        "- **Create** projects with name, key, description, and due date\n"
        "- **Update** project details (name, description, due date)\n"
        "- **Delete** projects (with all tasks, checklists, and documents)\n"
        "- **Manage members**: add, update roles, or remove project members\n"
        "- **View timelines** and overdue tasks\n"
        "\n"
        "### Tasks\n"
        "- **Create** tasks with title, description, priority, type, and assignments\n"
        "- **Update** task details (title, description, priority, due date, type)\n"
        "- **Move** tasks between statuses (Todo -> In Progress -> Done)\n"
        "- **Assign/reassign** tasks to team members\n"
        "- **Delete** tasks\n"
        "- **Add comments** with @mentions (triggers notifications)\n"
        "- **Manage checklists**: add checklists, items, and toggle completion\n"
        "\n"
        "### Knowledge Base\n"
        "- **Create** documents (training, research, documentation, notes, or general)\n"
        "- **Update** document title and content\n"
        "- **Delete** documents\n"
        "- **Search** across all knowledge base documents\n"
        "- **Browse** folder structure\n"
        "- **Export** documents as PDF\n"
        "\n"
        "### Web Research\n"
        "- **Search** the web for current information, articles, and documentation\n"
        "- **Scrape** web pages to extract and summarize content\n"
        "- Chain search + scrape for deep research on any topic\n"
        "\n"
        "### Data & Analytics\n"
        "- **SQL queries** on project data (tasks, members, timelines)\n"
        "- **Export** tasks, projects, or members to Excel\n"
        "- **Workload analysis** across team members\n"
        "- **Image analysis** for uploaded screenshots or diagrams\n"
        "\n"
        "### Search & Discovery\n"
        "- **Hybrid search** across documents (semantic + keyword + fuzzy)\n"
        "- **Browse** workspace and project structures\n"
        "- **View** task details, comments, and history\n"
        "\n"
        "---\n"
        "\n"
        "*All write operations require your confirmation before executing.*\n"
        "*Ask me anything about your projects, tasks, or documents!*"
    )


@tool
async def request_clarification(
    question: str,
    options: list[str] | None = None,
    context: str | None = None,
) -> str:
    """Ask the user ANY question. This is the ONLY way to ask questions.

    IMPORTANT: Never type questions in your response text — always use this
    tool instead. It provides interactive UI with clickable option buttons
    and a text input field. Plain text questions have no interactivity.

    Use this when:
    - The request is ambiguous (e.g., "the project" but multiple exist)
    - You need the user to choose between options
    - You need specific details before performing an action
    - A tool returned an error and you need the user to clarify their intent
    - Any time you would otherwise type a question mark in your response

    Try to search with tools first before asking. Only ask when tools
    genuinely cannot resolve the ambiguity.

    Args:
        question: The question to ask the user.
        options: Optional list of suggested answers (shown as clickable
                 buttons). Keep to 2-5 options. Always provide options
                 when there are known valid choices.
        context: Optional context explaining why you are asking
                 (shown as subtitle text below the question).
    """
    clarification = {
        "type": "clarification",
        "question": question,
        "options": options,
        "context": context,
    }
    response = interrupt(clarification)

    if isinstance(response, dict):
        raw = response.get("answer", "")
    else:
        raw = str(response)
    if not raw:
        return "User provided no answer — please proceed with best available information."
    return _wrap_user_content(raw)
