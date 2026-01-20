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
from sqlalchemy.orm import Session, joinedload

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
    # Get current max position for this task's checklists
    max_position = db.query(func.max(Checklist.position)).filter(
        Checklist.task_id == task_id
    ).scalar() or 0

    checklist = Checklist(
        task_id=task_id,
        title=checklist_data.title,
        position=max_position + 1,
        total_items=0,
        done_items=0,
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

    Args:
        db: Database session
        checklist_id: Checklist ID

    Returns:
        Checklist or None if not found
    """
    return db.query(Checklist).options(
        joinedload(Checklist.items)
    ).filter(
        Checklist.id == checklist_id
    ).first()


def get_checklists_for_task(
    db: Session,
    task_id: UUID,
) -> List[Checklist]:
    """
    Get all checklists for a task with items.

    Args:
        db: Database session
        task_id: Task ID

    Returns:
        List of checklists ordered by position
    """
    return db.query(Checklist).options(
        joinedload(Checklist.items)
    ).filter(
        Checklist.task_id == task_id
    ).order_by(
        Checklist.position
    ).all()


# ============================================================================
# Checklist Item CRUD Operations
# ============================================================================


def create_checklist_item(
    db: Session,
    checklist_id: UUID,
    item_data: ChecklistItemCreate,
) -> Optional[ChecklistItem]:
    """
    Create a new item in a checklist.

    Args:
        db: Database session
        checklist_id: Checklist ID to add item to
        item_data: Item creation data

    Returns:
        Created item or None if checklist not found
    """
    checklist = db.query(Checklist).filter(Checklist.id == checklist_id).first()
    if not checklist:
        return None

    # Get max position
    max_position = db.query(func.max(ChecklistItem.position)).filter(
        ChecklistItem.checklist_id == checklist_id
    ).scalar() or 0

    item = ChecklistItem(
        checklist_id=checklist_id,
        text=item_data.text,
        is_done=item_data.is_done if item_data.is_done is not None else False,
        position=max_position + 1,
        created_at=datetime.utcnow(),
    )
    db.add(item)

    # Update checklist counts
    checklist.total_items += 1
    if item.is_done:
        checklist.done_items += 1
    checklist.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    # Update task counts
    _update_task_checklist_counts(db, checklist.task_id)

    return item


def update_checklist_item(
    db: Session,
    item_id: UUID,
    item_data: ChecklistItemUpdate,
) -> Optional[ChecklistItem]:
    """
    Update a checklist item.

    Args:
        db: Database session
        item_id: Item ID to update
        item_data: Update data

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

    if item_data.text is not None:
        item.text = item_data.text

    if item_data.is_done is not None:
        item.is_done = item_data.is_done

    item.updated_at = datetime.utcnow()

    # Update checklist done count if status changed
    if item_data.is_done is not None and was_done != item.is_done:
        if item.is_done:
            checklist.done_items += 1
        else:
            checklist.done_items = max(0, checklist.done_items - 1)
        checklist.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    # Update task counts
    _update_task_checklist_counts(db, checklist.task_id)

    return item


def toggle_checklist_item(
    db: Session,
    item_id: UUID,
) -> Optional[Tuple[ChecklistItem, UUID, UUID]]:
    """
    Toggle a checklist item's done status.

    Args:
        db: Database session
        item_id: Item ID to toggle

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

    # Update checklist count
    if item.is_done:
        checklist.done_items += 1
    else:
        checklist.done_items = max(0, checklist.done_items - 1)
    checklist.updated_at = datetime.utcnow()

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
        checklist.done_items = max(0, checklist.done_items - 1)
    checklist.updated_at = datetime.utcnow()

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

    # Update positions
    for position, item_id in enumerate(item_ids, start=1):
        db.query(ChecklistItem).filter(
            ChecklistItem.id == item_id
        ).update({"position": position})

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

    # Update positions
    for position, checklist_id in enumerate(checklist_ids, start=1):
        db.query(Checklist).filter(
            Checklist.id == checklist_id
        ).update({"position": position})

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
        func.sum(Checklist.done_items).label("done"),
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
    for item in sorted(checklist.items, key=lambda x: x.position):
        items.append({
            "id": str(item.id),
            "checklist_id": str(item.checklist_id),
            "text": item.text,
            "is_done": item.is_done,
            "position": item.position,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        })

    return {
        "id": str(checklist.id),
        "task_id": str(checklist.task_id),
        "title": checklist.title,
        "position": checklist.position,
        "total_items": checklist.total_items,
        "done_items": checklist.done_items,
        "created_at": checklist.created_at.isoformat(),
        "updated_at": checklist.updated_at.isoformat() if checklist.updated_at else None,
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
    return {
        "id": str(item.id),
        "checklist_id": str(item.checklist_id),
        "text": item.text,
        "is_done": item.is_done,
        "position": item.position,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
