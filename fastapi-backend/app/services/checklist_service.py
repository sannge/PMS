"""Checklist service for task checklists with drag-and-drop reordering.

Provides business logic for:
- Creating, updating, deleting checklists
- Managing checklist items with toggle functionality
- Reordering items via drag-and-drop
- Maintaining denormalized counts on tasks
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.checklist import Checklist
from ..models.checklist_item import ChecklistItem
from ..models.task import Task
from ..schemas.checklist import (
    ChecklistCreate,
    ChecklistItemCreate,
    ChecklistItemUpdate,
    ChecklistUpdate,
    ReorderRequest,
)


def _generate_lexorank(before_rank: Optional[str] = None, after_rank: Optional[str] = None) -> str:
    """Generate a lexorank between two existing ranks."""
    if before_rank is None and after_rank is None:
        return "a"
    if before_rank is None:
        # Insert at beginning
        return chr(ord(after_rank[0]) - 1) if after_rank else "a"
    if after_rank is None:
        # Insert at end
        return before_rank + "a"
    # Insert between
    if before_rank < after_rank:
        # Find midpoint
        for i in range(max(len(before_rank), len(after_rank))):
            b_char = before_rank[i] if i < len(before_rank) else 'a'
            a_char = after_rank[i] if i < len(after_rank) else 'z'
            if ord(a_char) - ord(b_char) > 1:
                return before_rank[:i] + chr((ord(b_char) + ord(a_char)) // 2)
        return before_rank + "m"
    return before_rank + "m"


# ============================================================================
# Checklist CRUD Operations
# ============================================================================


async def create_checklist(
    db: AsyncSession,
    task_id: UUID,
    checklist_data: ChecklistCreate,
) -> Checklist:
    """
    Create a new checklist for a task.

    Args:
        db: Database session
        task_id: Task ID to add checklist to
        checklist_data: Checklist creation data

    Returns:
        Created checklist
    """
    # Get current max rank for this task's checklists
    result = await db.execute(
        select(Checklist)
        .where(Checklist.task_id == task_id)
        .order_by(Checklist.rank.desc())
        .limit(1)
    )
    last_checklist = result.scalar_one_or_none()

    new_rank = _generate_lexorank(last_checklist.rank if last_checklist else None, None)

    checklist = Checklist(
        task_id=task_id,
        title=checklist_data.title,
        rank=new_rank,
        total_items=0,
        completed_items=0,
        created_at=datetime.utcnow(),
    )
    db.add(checklist)
    await db.commit()
    await db.refresh(checklist)

    return checklist


async def update_checklist(
    db: AsyncSession,
    checklist_id: UUID,
    checklist_data: ChecklistUpdate,
) -> Optional[Checklist]:
    """
    Update a checklist.

    Args:
        db: Database session
        checklist_id: Checklist ID to update
        checklist_data: Update data

    Returns:
        Updated checklist or None if not found
    """
    result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return None

    if checklist_data.title is not None:
        checklist.title = checklist_data.title

    checklist.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(checklist)

    return checklist


async def delete_checklist(
    db: AsyncSession,
    checklist_id: UUID,
) -> bool:
    """
    Delete a checklist and all its items.

    Args:
        db: Database session
        checklist_id: Checklist ID to delete

    Returns:
        True if deleted, False if not found
    """
    result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return False

    task_id = checklist.task_id

    # Delete all items
    await db.execute(
        delete(ChecklistItem).where(ChecklistItem.checklist_id == checklist_id)
    )

    # Delete checklist
    await db.delete(checklist)
    await db.commit()

    # Update task counts
    await _update_task_checklist_counts(db, task_id)

    return True


async def get_checklist(
    db: AsyncSession,
    checklist_id: UUID,
) -> Optional[Checklist]:
    """
    Get a checklist by ID with items loaded.

    Uses selectinload for items to avoid cartesian product,
    and nested selectinload for completer to prevent N+1 queries.

    Args:
        db: Database session
        checklist_id: Checklist ID

    Returns:
        Checklist or None if not found
    """
    result = await db.execute(
        select(Checklist)
        .options(selectinload(Checklist.items).selectinload(ChecklistItem.completer))
        .where(Checklist.id == checklist_id)
    )
    return result.scalar_one_or_none()


async def get_checklists_for_task(
    db: AsyncSession,
    task_id: UUID,
) -> List[Checklist]:
    """
    Get all checklists for a task with items.

    Uses selectinload for items to avoid cartesian product,
    and nested selectinload for completer to prevent N+1 queries.

    Args:
        db: Database session
        task_id: Task ID

    Returns:
        List of checklists ordered by rank
    """
    result = await db.execute(
        select(Checklist)
        .options(selectinload(Checklist.items).selectinload(ChecklistItem.completer))
        .where(Checklist.task_id == task_id)
        .order_by(Checklist.rank)
    )
    return list(result.scalars().all())


# ============================================================================
# Checklist Item CRUD Operations
# ============================================================================


async def create_checklist_item(
    db: AsyncSession,
    checklist_id: UUID,
    item_data: ChecklistItemCreate,
    user_id: Optional[UUID] = None,
) -> Optional[ChecklistItem]:
    """
    Create a new item in a checklist.

    Args:
        db: Database session
        checklist_id: Checklist ID to add item to
        item_data: Item creation data
        user_id: ID of user creating the item

    Returns:
        Created item or None if checklist not found
    """
    result = await db.execute(
        select(Checklist).where(Checklist.id == checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return None

    # Get last item rank
    result = await db.execute(
        select(ChecklistItem)
        .where(ChecklistItem.checklist_id == checklist_id)
        .order_by(ChecklistItem.rank.desc())
        .limit(1)
    )
    last_item = result.scalar_one_or_none()

    new_rank = _generate_lexorank(last_item.rank if last_item else None, None)

    item = ChecklistItem(
        checklist_id=checklist_id,
        content=item_data.content,
        is_done=False,
        rank=new_rank,
        created_at=datetime.utcnow(),
    )
    db.add(item)

    # Update checklist counts
    checklist.total_items += 1
    # No need to update completed_items since new items are not done

    await db.commit()
    await db.refresh(item)

    # Update task counts
    await _update_task_checklist_counts(db, checklist.task_id)

    return item


async def update_checklist_item(
    db: AsyncSession,
    item_id: UUID,
    item_data: ChecklistItemUpdate,
    user_id: Optional[UUID] = None,
) -> Optional[ChecklistItem]:
    """
    Update a checklist item.

    Args:
        db: Database session
        item_id: Item ID to update
        item_data: Update data
        user_id: ID of user updating the item

    Returns:
        Updated item or None if not found
    """
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return None

    result = await db.execute(
        select(Checklist).where(Checklist.id == item.checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return None

    # Track if done status changed
    was_done = item.is_done

    if item_data.content is not None:
        item.content = item_data.content

    if item_data.is_done is not None:
        item.is_done = item_data.is_done
        if item.is_done and not was_done:
            item.completed_by = user_id
            item.completed_at = datetime.utcnow()
        elif not item.is_done and was_done:
            item.completed_by = None
            item.completed_at = None

    item.updated_at = datetime.utcnow()

    # Update checklist completed count if status changed
    if item_data.is_done is not None and was_done != item.is_done:
        if item.is_done:
            checklist.completed_items += 1
        else:
            checklist.completed_items = max(0, checklist.completed_items - 1)

    await db.commit()
    await db.refresh(item)

    # Update task counts
    await _update_task_checklist_counts(db, checklist.task_id)

    return item


async def toggle_checklist_item(
    db: AsyncSession,
    item_id: UUID,
    user_id: Optional[UUID] = None,
) -> Optional[Tuple[ChecklistItem, UUID, UUID]]:
    """
    Toggle a checklist item's done status.

    Args:
        db: Database session
        item_id: Item ID to toggle
        user_id: ID of user toggling the item

    Returns:
        Tuple of (updated item, checklist_id, task_id) or None if not found
    """
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return None

    result = await db.execute(
        select(Checklist).where(Checklist.id == item.checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return None

    # Toggle
    item.is_done = not item.is_done
    item.updated_at = datetime.utcnow()

    if item.is_done:
        item.completed_by = user_id
        item.completed_at = datetime.utcnow()
    else:
        item.completed_by = None
        item.completed_at = None

    # Update checklist count
    if item.is_done:
        checklist.completed_items += 1
    else:
        checklist.completed_items = max(0, checklist.completed_items - 1)

    await db.commit()
    await db.refresh(item)

    # Update task counts
    await _update_task_checklist_counts(db, checklist.task_id)

    return item, checklist.id, checklist.task_id


async def delete_checklist_item(
    db: AsyncSession,
    item_id: UUID,
) -> Optional[Tuple[UUID, UUID]]:
    """
    Delete a checklist item.

    Args:
        db: Database session
        item_id: Item ID to delete

    Returns:
        Tuple of (checklist_id, task_id) or None if not found
    """
    result = await db.execute(
        select(ChecklistItem).where(ChecklistItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return None

    result = await db.execute(
        select(Checklist).where(Checklist.id == item.checklist_id)
    )
    checklist = result.scalar_one_or_none()
    if not checklist:
        return None

    checklist_id = checklist.id
    task_id = checklist.task_id

    # Update counts
    checklist.total_items = max(0, checklist.total_items - 1)
    if item.is_done:
        checklist.completed_items = max(0, checklist.completed_items - 1)

    await db.delete(item)
    await db.commit()

    # Update task counts
    await _update_task_checklist_counts(db, task_id)

    return checklist_id, task_id


# ============================================================================
# Reordering
# ============================================================================


async def reorder_checklist_items(
    db: AsyncSession,
    checklist_id: UUID,
    item_ids: List[UUID],
) -> bool:
    """
    Reorder items in a checklist.

    Args:
        db: Database session
        checklist_id: Checklist ID
        item_ids: Ordered list of item IDs

    Returns:
        True if successful, False if validation fails
    """
    # Verify all items belong to the checklist
    result = await db.execute(
        select(ChecklistItem).where(
            ChecklistItem.checklist_id == checklist_id,
            ChecklistItem.id.in_(item_ids),
        )
    )
    items = result.scalars().all()

    if len(items) != len(item_ids):
        return False

    # Generate new ranks based on order
    current_rank = "a"
    for item_id in item_ids:
        await db.execute(
            update(ChecklistItem)
            .where(ChecklistItem.id == item_id)
            .values(rank=current_rank)
        )
        current_rank = _generate_lexorank(current_rank, None)

    await db.commit()
    return True


async def reorder_checklists(
    db: AsyncSession,
    task_id: UUID,
    checklist_ids: List[UUID],
) -> bool:
    """
    Reorder checklists for a task.

    Args:
        db: Database session
        task_id: Task ID
        checklist_ids: Ordered list of checklist IDs

    Returns:
        True if successful, False if validation fails
    """
    # Verify all checklists belong to the task
    result = await db.execute(
        select(Checklist).where(
            Checklist.task_id == task_id,
            Checklist.id.in_(checklist_ids),
        )
    )
    checklists = result.scalars().all()

    if len(checklists) != len(checklist_ids):
        return False

    # Generate new ranks based on order
    current_rank = "a"
    for checklist_id in checklist_ids:
        await db.execute(
            update(Checklist)
            .where(Checklist.id == checklist_id)
            .values(rank=current_rank)
        )
        current_rank = _generate_lexorank(current_rank, None)

    await db.commit()
    return True


# ============================================================================
# Helper Functions
# ============================================================================


async def _update_task_checklist_counts(db: AsyncSession, task_id: UUID) -> None:
    """
    Update denormalized checklist counts on task.

    Args:
        db: Database session
        task_id: Task ID to update
    """
    # Calculate totals across all checklists
    result = await db.execute(
        select(
            func.sum(Checklist.total_items).label("total"),
            func.sum(Checklist.completed_items).label("done"),
        )
        .where(Checklist.task_id == task_id)
    )
    row = result.first()

    total = row.total or 0 if row else 0
    done = row.done or 0 if row else 0

    # Update task
    await db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(checklist_total=total, checklist_done=done)
    )
    await db.commit()


# ============================================================================
# Response Building
# ============================================================================


def build_checklist_response(checklist: Checklist) -> Dict[str, Any]:
    """
    Build a checklist response dictionary.

    Args:
        checklist: Checklist model instance

    Returns:
        Dictionary matching ChecklistResponse schema
    """
    items = []
    for item in sorted(checklist.items, key=lambda x: x.rank):
        items.append(build_checklist_item_response(item))

    progress_percent = 0
    if checklist.total_items > 0:
        progress_percent = int((checklist.completed_items / checklist.total_items) * 100)

    return {
        "id": str(checklist.id),
        "task_id": str(checklist.task_id),
        "title": checklist.title,
        "rank": checklist.rank,
        "total_items": checklist.total_items,
        "completed_items": checklist.completed_items,
        "progress_percent": progress_percent,
        "created_at": checklist.created_at.isoformat(),
        "items": items,
    }


def build_checklist_item_response(item: ChecklistItem) -> Dict[str, Any]:
    """
    Build a checklist item response dictionary.

    Args:
        item: ChecklistItem model instance

    Returns:
        Dictionary matching ChecklistItemResponse schema
    """
    completer_name = None
    if item.completer:
        completer_name = item.completer.display_name or item.completer.email

    return {
        "id": str(item.id),
        "checklist_id": str(item.checklist_id),
        "content": item.content,
        "is_done": item.is_done,
        "completed_by": str(item.completed_by) if item.completed_by else None,
        "completed_by_name": completer_name,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "rank": item.rank,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
