"""Document business logic service.

Provides helpers for scope validation, cursor pagination, folder depth
management, materialized path computation, and content conversion stubs.
"""

import base64
import json
from datetime import datetime
from typing import Any, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.document_folder import DocumentFolder
from ..models.project import Project
from ..models.user import User


async def validate_scope(
    scope: str,
    scope_id: UUID,
    db: AsyncSession,
) -> None:
    """
    Verify that the referenced scope entity (application/project/user) exists.

    Args:
        scope: One of "application", "project", "personal"
        scope_id: UUID of the scope entity
        db: Database session

    Raises:
        HTTPException: 404 if the scope entity does not exist
    """
    if scope == "application":
        result = await db.execute(select(Application.id).where(Application.id == scope_id))
    elif scope == "project":
        result = await db.execute(select(Project.id).where(Project.id == scope_id))
    elif scope == "personal":
        result = await db.execute(select(User.id).where(User.id == scope_id))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope: {scope}",
        )

    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{scope.capitalize()} with id {scope_id} not found",
        )


def set_scope_fks(obj: Any, scope: str, scope_id: UUID) -> None:
    """
    Set the correct foreign key column on a model instance based on scope.

    Args:
        obj: SQLAlchemy model instance (Document or DocumentFolder)
        scope: One of "application", "project", "personal"
        scope_id: UUID to assign
    """
    if scope == "application":
        obj.application_id = scope_id
    elif scope == "project":
        obj.project_id = scope_id
    elif scope == "personal":
        obj.user_id = scope_id


def get_scope_filter(model: Any, scope: str, scope_id: UUID) -> Any:
    """
    Return a SQLAlchemy filter expression for the given scope.

    Args:
        model: SQLAlchemy model class (Document or DocumentFolder)
        scope: One of "application", "project", "personal"
        scope_id: UUID to filter on

    Returns:
        SQLAlchemy binary expression for WHERE clause
    """
    if scope == "application":
        return model.application_id == scope_id
    elif scope == "project":
        return model.project_id == scope_id
    elif scope == "personal":
        return model.user_id == scope_id
    else:
        raise ValueError(f"Invalid scope: {scope}")


def encode_cursor(created_at: datetime, id: UUID) -> str:
    """
    Encode a cursor from created_at timestamp and document ID.

    Uses base64-encoded JSON for cursor stability across API versions.

    Args:
        created_at: Document creation timestamp
        id: Document UUID

    Returns:
        Base64-encoded cursor string
    """
    payload = json.dumps({
        "created_at": created_at.isoformat(),
        "id": str(id),
    })
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> Tuple[datetime, UUID]:
    """
    Decode a cursor string back to created_at and ID.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Tuple of (created_at, id)

    Raises:
        HTTPException: 400 if cursor is invalid
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        created_at = datetime.fromisoformat(payload["created_at"])
        id = UUID(payload["id"])
        return created_at, id
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cursor: {e}",
        )


async def validate_folder_depth(
    db: AsyncSession,
    parent_id: Optional[UUID],
) -> Tuple[int, Optional[str]]:
    """
    Check that adding a child under parent_id would not exceed max depth of 5.

    Args:
        db: Database session
        parent_id: Parent folder UUID (None for root-level)

    Returns:
        Tuple of (new_depth, parent_materialized_path)

    Raises:
        HTTPException: 400 if nesting would exceed 5 levels
    """
    if parent_id is None:
        return 0, None

    result = await db.execute(
        select(DocumentFolder.depth, DocumentFolder.materialized_path)
        .where(DocumentFolder.id == parent_id)
    )
    parent = result.one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent folder {parent_id} not found",
        )

    parent_depth, parent_path = parent
    new_depth = parent_depth + 1
    if new_depth > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum folder nesting depth is 5 (parent is at depth {parent_depth})",
        )

    return new_depth, parent_path


def compute_materialized_path(
    parent_path: Optional[str],
    folder_id: UUID,
) -> str:
    """
    Build materialized path string from parent path and folder ID.

    Format: "/{ancestor-uuid}/.../{self-uuid}/"

    Args:
        parent_path: Parent's materialized path (None for root)
        folder_id: This folder's UUID

    Returns:
        Materialized path string
    """
    if parent_path is None or parent_path == "/":
        return f"/{folder_id}/"
    return f"{parent_path}{folder_id}/"


async def update_descendant_paths(
    db: AsyncSession,
    old_path: str,
    new_path: str,
    depth_delta: int,
) -> None:
    """
    Bulk update materialized_path and depth for all descendants of a moved folder.

    Uses SQL LIKE + string replacement for efficient bulk update.

    Args:
        db: Database session
        old_path: The folder's old materialized path
        new_path: The folder's new materialized path
        depth_delta: Change in depth (new_depth - old_depth)
    """
    from sqlalchemy import func

    # Update all folders whose path starts with old_path
    stmt = (
        update(DocumentFolder)
        .where(DocumentFolder.materialized_path.like(f"{old_path}%"))
        .values(
            materialized_path=func.replace(
                DocumentFolder.materialized_path, old_path, new_path
            ),
            depth=DocumentFolder.depth + depth_delta,
        )
    )
    await db.execute(stmt)


def convert_tiptap_to_markdown(content_json: Optional[str]) -> str:
    """Convert TipTap JSON to Markdown format.

    Stub for Phase 4 auto-save pipeline (SAVE-05). Will be implemented
    with a proper TipTap JSON walker or library.

    Args:
        content_json: TipTap JSON string or None

    Returns:
        Markdown string (currently empty stub)
    """
    # TODO(Phase-4): Implement TipTap JSON -> Markdown conversion
    return ""


def convert_tiptap_to_plain_text(content_json: Optional[str]) -> str:
    """Convert TipTap JSON to plain text for search indexing.

    Stub for Phase 4 auto-save pipeline (SAVE-05). Will be implemented
    to extract text nodes from TipTap JSON.

    Args:
        content_json: TipTap JSON string or None

    Returns:
        Plain text string (currently empty stub)
    """
    # TODO(Phase-4): Implement TipTap JSON -> plain text extraction
    return ""
