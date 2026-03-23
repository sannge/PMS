"""Checklist write tools for Blair AI agent -- all require HITL confirmation via interrupt().

Tools that modify checklist data in the PM Desktop system:
1. add_checklist -- Add a new checklist to a task
2. add_checklist_item -- Add an item to an existing checklist
3. toggle_checklist_item -- Toggle a checklist item's completion status

All tools:
- Check RBAC BEFORE calling interrupt() (never confirm then deny)
- Use LangGraph interrupt() to pause and request user confirmation
- Use existing SQLAlchemy models for mutations
- Return human-readable confirmation text on success
- Return clear cancellation messages on rejection
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy import func, select, update

from ....models.checklist import Checklist
from ....models.checklist_item import ChecklistItem
from ....models.project_member import ProjectMember
from ....models.task import Task
from ....models.task_status import TaskStatus
from ....utils.timezone import utc_now
from ....services.checklist_service import _generate_lexorank
from .context import _check_project_access, _get_user_id
from .helpers import (
    _escape_ilike,
    _get_tool_session,
    _resolve_task,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool 1: add_checklist
# ---------------------------------------------------------------------------


@tool
async def add_checklist(
    task: str,
    title: str,
) -> str:
    """Add a new checklist to a task. Requires user confirmation before executing.

    Use this when the user wants to create a new checklist group on a task,
    such as a QA checklist, acceptance criteria, or subtask list.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        title: Checklist title (1-100 characters)
    """
    # Validate inputs
    if not title or len(title.strip()) == 0:
        return "Error: Checklist title is required."
    if len(title) > 100:
        return "Error: Checklist title must be 100 characters or fewer."

    # Resolve task and check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(select(Task).where(Task.id == task_uuid))
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        task_title = task_obj.title
        project_id = task_obj.project_id

        # Check task is not in Done status
        status_result = await db.execute(select(TaskStatus).where(TaskStatus.id == task_obj.task_status_id))
        current_status = status_result.scalar_one_or_none()
        if current_status and current_status.name == "Done":
            return (
                f"Error: Cannot add checklist to task {task_key} because it is "
                f"in 'Done' status. Move it to another status first."
            )

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "add_checklist",
        "summary": f"Add checklist '{title}' to {task_key} '{task_title}'",
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "title": title,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Checklist creation cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id)
                .where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                )
                .limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load task to get fresh state
            result = await db.execute(select(Task).where(Task.id == task_uuid))
            task_obj = result.scalar_one_or_none()
            if not task_obj:
                return f"Error: Task '{task}' no longer exists."

            # Get last checklist rank for ordering
            rank_result = await db.execute(
                select(Checklist).where(Checklist.task_id == task_uuid).order_by(Checklist.rank.desc()).limit(1)
            )
            last_checklist = rank_result.scalar_one_or_none()
            new_rank = _generate_lexorank(last_checklist.rank if last_checklist else None, None)

            checklist = Checklist(
                task_id=task_uuid,
                title=title.strip(),
                rank=new_rank,
                total_items=0,
                completed_items=0,
                created_at=utc_now(),
            )
            db.add(checklist)
            await db.flush()

            return f"Added checklist '{title}' to {task_key}."

        except Exception as e:
            logger.exception("add_checklist failed: %s", e)
            raise


# ---------------------------------------------------------------------------
# Tool 2: add_checklist_item
# ---------------------------------------------------------------------------


@tool
async def add_checklist_item(
    task: str,
    checklist_title: str,
    item_title: str,
) -> str:
    """Add an item to an existing checklist on a task. Requires user confirmation.

    Use this when the user wants to add a new item, step, or criterion
    to an existing checklist on a task.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        checklist_title: Title of the checklist to add the item to (case-insensitive)
        item_title: Item text content (1-200 characters)
    """
    # Validate inputs
    if not item_title or len(item_title.strip()) == 0:
        return "Error: Item title is required."
    if len(item_title) > 200:
        return "Error: Item title must be 200 characters or fewer."
    if not checklist_title or len(checklist_title.strip()) == 0:
        return "Error: Checklist title is required."

    # Resolve task, find checklist, check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(select(Task).where(Task.id == task_uuid))
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        project_id = task_obj.project_id

        # Find checklist by title (case-insensitive)
        escaped_title = _escape_ilike(checklist_title)
        cl_result = await db.execute(
            select(Checklist).where(
                Checklist.task_id == task_uuid,
                Checklist.title.ilike(f"%{escaped_title}%", escape="\\"),
            )
        )
        checklist_obj = cl_result.scalar_one_or_none()
        if not checklist_obj:
            # List available checklists to help the user
            all_cl_result = await db.execute(select(Checklist.title).where(Checklist.task_id == task_uuid))
            available = [r[0] for r in all_cl_result.all()]
            if available:
                return (
                    f"Error: No checklist matching '{checklist_title}' found on "
                    f"task {task_key}. Available checklists: "
                    f"{', '.join(available)}."
                )
            return f"Error: No checklists found on task {task_key}. Create a checklist first using add_checklist."

        checklist_id = checklist_obj.id
        checklist_name = checklist_obj.title

    # Build confirmation
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "add_checklist_item",
        "summary": (f"Add item '{item_title}' to checklist '{checklist_name}' on {task_key}"),
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "checklist_id": str(checklist_id),
            "checklist_title": checklist_name,
            "item_title": item_title,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Checklist item creation cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id)
                .where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                )
                .limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load checklist to get fresh state
            cl_result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
            checklist_obj = cl_result.scalar_one_or_none()
            if not checklist_obj:
                return f"Error: Checklist '{checklist_title}' no longer exists."

            # Get last item rank for ordering
            rank_result = await db.execute(
                select(ChecklistItem)
                .where(ChecklistItem.checklist_id == checklist_id)
                .order_by(ChecklistItem.rank.desc())
                .limit(1)
            )
            last_item = rank_result.scalar_one_or_none()
            new_rank = _generate_lexorank(last_item.rank if last_item else None, None)

            item = ChecklistItem(
                checklist_id=checklist_id,
                content=item_title.strip(),
                is_done=False,
                rank=new_rank,
                created_at=utc_now(),
            )
            db.add(item)

            # Update Checklist.total_items
            checklist_obj.total_items += 1

            # Update Task.checklist_total (denormalized counter)
            await db.execute(update(Task).where(Task.id == task_uuid).values(checklist_total=Task.checklist_total + 1))

            await db.flush()

            return f"Added item '{item_title}' to checklist '{checklist_name}'."

        except Exception as e:
            logger.exception("add_checklist_item failed: %s", e)
            raise


# ---------------------------------------------------------------------------
# Tool 3: toggle_checklist_item
# ---------------------------------------------------------------------------


@tool
async def toggle_checklist_item(
    task: str,
    checklist_title: str,
    item_title: str,
) -> str:
    """Toggle a checklist item's completion status. Requires user confirmation.

    Use this when the user wants to mark a checklist item as complete or
    incomplete. The item will be toggled from its current state.

    Args:
        task: Task UUID, task key (e.g., "PROJ-123"), or title (partial match)
        checklist_title: Title of the checklist containing the item (case-insensitive)
        item_title: Title/content of the item to toggle (case-insensitive)
    """
    if not checklist_title or len(checklist_title.strip()) == 0:
        return "Error: Checklist title is required."
    if not item_title or len(item_title.strip()) == 0:
        return "Error: Item title is required."

    # Resolve task -> checklist -> item, check RBAC BEFORE interrupt
    async with _get_tool_session() as db:
        resolved_id, error = await _resolve_task(task, db)
        if error:
            return error
        task_uuid = UUID(resolved_id)  # type: ignore[arg-type]

        result = await db.execute(select(Task).where(Task.id == task_uuid))
        task_obj = result.scalar_one_or_none()
        if not task_obj:
            return f"Error: Task '{task}' not found."

        # RBAC: check access to the task's project
        if not _check_project_access(str(task_obj.project_id)):
            return "Access denied: you do not have access to this task's project."

        task_key = task_obj.task_key
        project_id = task_obj.project_id

        # Find checklist by title (case-insensitive)
        escaped_cl_title = _escape_ilike(checklist_title)
        cl_result = await db.execute(
            select(Checklist).where(
                Checklist.task_id == task_uuid,
                Checklist.title.ilike(f"%{escaped_cl_title}%", escape="\\"),
            )
        )
        checklist_obj = cl_result.scalar_one_or_none()
        if not checklist_obj:
            return f"Error: No checklist matching '{checklist_title}' found on task {task_key}."

        checklist_id = checklist_obj.id
        checklist_name = checklist_obj.title

        # Find item by title (case-insensitive)
        escaped_item_title = _escape_ilike(item_title)
        item_result = await db.execute(
            select(ChecklistItem).where(
                ChecklistItem.checklist_id == checklist_id,
                ChecklistItem.content.ilike(f"%{escaped_item_title}%", escape="\\"),
            )
        )
        item_obj = item_result.scalar_one_or_none()
        if not item_obj:
            # List available items to help the user
            all_items_result = await db.execute(
                select(ChecklistItem.content).where(ChecklistItem.checklist_id == checklist_id)
            )
            available = [r[0] for r in all_items_result.all()]
            if available:
                return (
                    f"Error: No item matching '{item_title}' found in "
                    f"checklist '{checklist_name}' on task {task_key}. "
                    f"Available items: {', '.join(available[:10])}."
                )
            return f"Error: No items found in checklist '{checklist_name}' on task {task_key}."

        item_id = item_obj.id
        currently_done = item_obj.is_done

    # Build confirmation
    action_verb = "incomplete" if currently_done else "complete"
    confirmation: dict[str, Any] = {
        "type": "confirmation",
        "action": "toggle_checklist_item",
        "summary": (f"Mark '{item_title}' as {action_verb} in checklist '{checklist_name}' on {task_key}"),
        "details": {
            "task_id": str(task_uuid),
            "task_key": task_key,
            "checklist_title": checklist_name,
            "item_title": item_title,
            "currently_done": currently_done,
            "new_state": not currently_done,
        },
    }

    # Pause graph -- wait for user approval
    response = interrupt(confirmation)

    if not isinstance(response, dict) or response.get("approved") is not True:
        return "Checklist item toggle cancelled by user."

    # Re-check RBAC + execute write in single session (TOCTOU mitigation)
    async with _get_tool_session() as db:
        try:
            user_uuid_check = _get_user_id()
            membership = await db.execute(
                select(ProjectMember.id)
                .where(
                    ProjectMember.project_id == UUID(str(project_id)),
                    ProjectMember.user_id == user_uuid_check,
                )
                .limit(1)
            )
            if membership.scalar_one_or_none() is None:
                return "Access denied: you no longer have access to this task's project."

            # Re-load item to get fresh state
            item_result = await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))
            item_obj = item_result.scalar_one_or_none()
            if not item_obj:
                return f"Error: Checklist item '{item_title}' no longer exists."

            # Re-load checklist for counter updates
            cl_result = await db.execute(select(Checklist).where(Checklist.id == checklist_id))
            checklist_obj = cl_result.scalar_one_or_none()
            if not checklist_obj:
                return f"Error: Checklist '{checklist_title}' no longer exists."

            # Use the model's toggle method
            user_id = _get_user_id()
            item_obj.toggle(user_id=str(user_id))

            # Update Checklist.completed_items
            if item_obj.is_done:
                checklist_obj.completed_items += 1
            else:
                checklist_obj.completed_items = max(0, checklist_obj.completed_items - 1)

            # Update Task.checklist_done (denormalized counter)
            if item_obj.is_done:
                await db.execute(
                    update(Task).where(Task.id == task_uuid).values(checklist_done=Task.checklist_done + 1)
                )
            else:
                await db.execute(
                    update(Task)
                    .where(Task.id == task_uuid)
                    .values(checklist_done=func.greatest(Task.checklist_done - 1, 0))
                )

            await db.flush()

            new_state = "complete" if item_obj.is_done else "incomplete"
            return f"Marked '{item_title}' as {new_state}."

        except Exception as e:
            logger.exception("toggle_checklist_item failed: %s", e)
            raise


# ---------------------------------------------------------------------------
# Tool registry -- all checklist write tools exported for graph binding
# ---------------------------------------------------------------------------

CHECKLIST_WRITE_TOOLS = [
    add_checklist,
    add_checklist_item,
    toggle_checklist_item,
]
