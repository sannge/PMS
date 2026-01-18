"""Room authorization for WebSocket connections.

Validates that users have access to rooms they attempt to join.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.task import Task
from ..models.note import Note

logger = logging.getLogger(__name__)


async def check_room_access(user_id: UUID, room_id: str) -> bool:
    """
    Check if a user has access to a specific room.

    Room ID formats:
    - application:{uuid} - Application room (requires membership)
    - project:{uuid} - Project room (requires membership in parent application)
    - task:{uuid} - Task room (requires access to parent project)
    - note:{uuid} - Note room (requires access to parent application)
    - user:{uuid} - User-specific room (only for own user)

    Args:
        user_id: The user's UUID
        room_id: The room identifier

    Returns:
        bool: True if user has access, False otherwise
    """
    if not room_id or ":" not in room_id:
        # Invalid room format - deny
        return False

    try:
        room_type, resource_id_str = room_id.split(":", 1)
        resource_id = UUID(resource_id_str)
    except (ValueError, AttributeError):
        logger.warning(f"Invalid room ID format: {room_id}")
        return False

    # User-specific rooms - only allow access to own room
    if room_type == "user":
        return resource_id == user_id

    # Database access required for other room types
    db: Optional[Session] = None
    try:
        db = SessionLocal()

        if room_type == "application":
            return _check_application_access(db, user_id, resource_id)
        elif room_type == "project":
            return _check_project_access(db, user_id, resource_id)
        elif room_type == "task":
            return _check_task_access(db, user_id, resource_id)
        elif room_type == "note":
            return _check_note_access(db, user_id, resource_id)
        else:
            # Unknown room type - deny
            logger.warning(f"Unknown room type: {room_type}")
            return False

    except Exception as e:
        logger.error(f"Error checking room access: {e}")
        return False
    finally:
        if db:
            db.close()


def _check_application_access(db: Session, user_id: UUID, application_id: UUID) -> bool:
    """Check if user is a member of the application."""
    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()
    return member is not None


def _check_project_access(db: Session, user_id: UUID, project_id: UUID) -> bool:
    """Check if user has access to the project via application membership."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False
    return _check_application_access(db, user_id, project.application_id)


def _check_task_access(db: Session, user_id: UUID, task_id: UUID) -> bool:
    """Check if user has access to the task via project/application membership."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return False
    return _check_project_access(db, user_id, task.project_id)


def _check_note_access(db: Session, user_id: UUID, note_id: UUID) -> bool:
    """Check if user has access to the note via application membership."""
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        return False
    return _check_application_access(db, user_id, note.application_id)
