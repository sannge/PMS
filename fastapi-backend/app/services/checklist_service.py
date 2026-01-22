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

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

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


def create_checklist(
    db: Session,
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
    last_checklist = db.query(Checklist).filter(
        Checklist.task_id == task_id
    ).order_by(Checklist.rank.desc()).first()

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
    db.commit()
    db.refresh(checklist)

    return checklist


def update_checklist(
    db: Session,
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
    checklist = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not checklist:
        return None

    if checklist_data.title is not None:
        checklist.title = checklist_data.title

    checklist.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(checklist)

    return checklist


def delete_checklist(
    db: Session,
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
    checklist = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not checklist:
        return False

    task_id = checklist.task_id

    # Delete all items
    db.query(ChecklistItem).filter(ChecklistItem.checklist_id == checklist_id).delete()

    # Delete checklist
    db.delete(checklist)
    db.commit()

    # Update task counts
    _update_task_checklist_counts(db, task_id)

    return True


def get_checklist(
    db: Session,
    checklist_id: UUID,
) -> Optional[Checklist]:
    """
    Get a checklist by ID with items loaded.

    Uses selectinload for items to avoid cartesian product,
    and nested joinedload for completer to prevent N+1 queries.

    Args:
        db: Database session
        checklist_id: Checklist ID

    Returns:
        Checklist or None if not found
    """
    return db.query(Checklist).options(
        selectinload(Checklist.items).joinedload(ChecklistItem.completer)
    ).filter(
        Checklist.id == checklist_id
    ).first()


def get_checklists_for_task(
    db: Session,
    task_id: UUID,
) -> List[Checklist]:
    """
    Get all checklists for a task with items.

    Uses selectinload for items to avoid cartesian product,
    and nested joinedload for completer to prevent N+1 queries.

    Args:
        db: Database session
        task_id: Task ID

    Returns:
        List of checklists ordered by rank
    """
    return db.query(Checklist).options(
        selectinload(Checklist.items).joinedload(ChecklistItem.completer)
    ).filter(
        Checklist.task_id == task_id
    ).order_by(
        Checklist.rank
    ).all()


# ============================================================================
# Checklist Item CRUD Operations
# ============================================================================


def create_checklist_item(
    db: Session,
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
    checklist = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not checklist:
        return None

    # Get last item rank
    last_item = db.query(ChecklistItem).filter(
        ChecklistItem.checklist_id == checklist_id
    ).order_by(ChecklistItem.rank.desc()).first()

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

    db.commit()
    db.refresh(item)

    # Update task counts
    _update_task_checklist_counts(db, checklist.task_id)

    return item


def update_checklist_item(
    db: Session,
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
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        return None

    checklist = db.query(Checklist).filter(Checklist.id == item.checklist_id).first()
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

    db.commit()
    db.refresh(item)

    # Update task counts
    _update_task_checklist_counts(db, checklist.task_id)

    return item


def toggle_checklist_item(
    db: Session,
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
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        return None

    checklist = db.query(Checklist).filter(Checklist.id == item.checklist_id).first()
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

    db.commit()
    db.refresh(item)

    # Update task counts
    _update_task_checklist_counts(db, checklist.task_id)

    return item, checklist.id, checklist.task_id


def delete_checklist_item(
    db: Session,
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
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        return None

    checklist = db.query(Checklist).filter(Checklist.id == item.checklist_id).first()
    if not checklist:
        return None

    checklist_id = checklist.id
    task_id = checklist.task_id

    # Update counts
    checklist.total_items = max(0, checklist.total_items - 1)
    if item.is_done:
        checklist.completed_items = max(0, checklist.completed_items - 1)

    db.delete(item)
    db.commit()

    # Update task counts
    _update_task_checklist_counts(db, task_id)

    return checklist_id, task_id


# ============================================================================
# Reordering
# ============================================================================


def reorder_checklist_items(
    db: Session,
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
    items = db.query(ChecklistItem).filter(
        ChecklistItem.checklist_id == checklist_id,
        ChecklistItem.id.in_(item_ids),
    ).all()

    if len(items) != len(item_ids):
        return False

    # Generate new ranks based on order
    current_rank = "a"
    for item_id in item_ids:
        db.query(ChecklistItem).filter(
            ChecklistItem.id == item_id
        ).update({"rank": current_rank})
        current_rank = _generate_lexorank(current_rank, None)

    db.commit()
    return True


def reorder_checklists(
    db: Session,
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
    checklists = db.query(Checklist).filter(
        Checklist.task_id == task_id,
        Checklist.id.in_(checklist_ids),
    ).all()

    if len(checklists) != len(checklist_ids):
        return False

    # Generate new ranks based on order
    current_rank = "a"
    for checklist_id in checklist_ids:
        db.query(Checklist).filter(
            Checklist.id == checklist_id
        ).update({"rank": current_rank})
        current_rank = _generate_lexorank(current_rank, None)

    db.commit()
    return True


# ============================================================================
# Helper Functions
# ============================================================================


def _update_task_checklist_counts(db: Session, task_id: UUID) -> None:
    """
    Update denormalized checklist counts on task.

    Args:
        db: Database session
        task_id: Task ID to update
    """
    # Calculate totals across all checklists
    result = db.query(
        func.sum(Checklist.total_items).label("total"),
        func.sum(Checklist.completed_items).label("done"),
    ).filter(
        Checklist.task_id == task_id
    ).first()

    total = result.total or 0 if result else 0
    done = result.done or 0 if result else 0

    # Update task
    db.query(Task).filter(Task.id == task_id).update({
        "checklist_total": total,
        "checklist_done": done,
    })
    db.commit()


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
