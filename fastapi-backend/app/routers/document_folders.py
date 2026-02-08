"""Document folder CRUD and tree API endpoints.

Provides endpoints for managing document folders within the knowledge base.
Folders use a materialized path pattern for efficient tree queries and
support nesting up to 5 levels deep. All endpoints require authentication.
"""

from collections import defaultdict
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document import Document
from ..models.document_folder import DocumentFolder
from ..models.project import Project
from ..models.user import User
from ..schemas.document_folder import (
    FolderCreate,
    FolderResponse,
    FolderTreeNode,
    FolderUpdate,
)
from ..services.auth_service import get_current_user
from ..services.document_service import (
    compute_materialized_path,
    get_scope_filter,
    set_scope_fks,
    update_descendant_paths,
    validate_folder_depth,
    validate_scope,
)
from ..websocket.manager import manager, MessageType

router = APIRouter(
    prefix="/document-folders",
    tags=["document-folders"],
)


def _get_folder_scope(folder: DocumentFolder) -> tuple[str, str]:
    """Extract scope type and ID from a folder."""
    if folder.application_id:
        return "application", str(folder.application_id)
    elif folder.project_id:
        return "project", str(folder.project_id)
    elif folder.user_id:
        return "personal", str(folder.user_id)
    return "unknown", ""


async def _broadcast_folder_event(
    message_type: MessageType,
    folder: DocumentFolder,
    actor_id: UUID | None = None,
    extra_data: dict | None = None,
    project_application_id: UUID | None = None,
) -> None:
    """Broadcast a folder event to the appropriate room(s).

    Args:
        message_type: The WebSocket message type
        folder: The folder being affected
        actor_id: The user who performed the action (for client-side filtering)
        extra_data: Additional data to include in the broadcast
        project_application_id: For project-scoped folders, the parent application ID
            (so we can also broadcast to the application room)
    """
    scope, scope_id = _get_folder_scope(folder)

    data = {
        "folder_id": str(folder.id),
        "scope": scope,
        "scope_id": scope_id,
        "parent_id": str(folder.parent_id) if folder.parent_id else None,
        "actor_id": str(actor_id) if actor_id else None,
        "timestamp": datetime.utcnow().isoformat(),
        # Include application_id for project-scoped items so frontend can invalidate app queries
        "application_id": str(project_application_id) if project_application_id else None,
    }
    if extra_data:
        data.update(extra_data)

    message = {"type": message_type.value, "data": data}

    # Determine the room(s) to broadcast to
    if folder.application_id:
        await manager.broadcast_to_room(f"application:{folder.application_id}", message)
    elif folder.project_id:
        # Broadcast to project room
        await manager.broadcast_to_room(f"project:{folder.project_id}", message)
        # Also broadcast to application room so users viewing the app tree get updates
        if project_application_id:
            await manager.broadcast_to_room(f"application:{project_application_id}", message)
    else:
        # Personal folders - broadcast to user room
        await manager.broadcast_to_room(f"user:{folder.user_id}", message)


@router.get("/tree", response_model=list[FolderTreeNode])
async def get_folder_tree(
    scope: Literal["application", "project", "personal"] = Query(
        ..., description="Scope type"
    ),
    scope_id: UUID = Query(..., description="Scope entity ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FolderTreeNode]:
    """
    Get the full folder tree for a scope in a single call.

    Returns root-level folder nodes with nested children. Each node
    includes a document_count of non-deleted documents in that folder.
    Folders are ordered by materialized_path ASC, sort_order ASC.
    """
    # Fetch all folders for scope
    scope_filter = get_scope_filter(DocumentFolder, scope, scope_id)
    result = await db.execute(
        select(DocumentFolder)
        .where(scope_filter)
        .order_by(DocumentFolder.materialized_path.asc(), DocumentFolder.sort_order.asc())
    )
    folders = result.scalars().all()

    if not folders:
        return []

    # Get document counts per folder
    folder_ids = [f.id for f in folders]
    doc_count_result = await db.execute(
        select(
            Document.folder_id,
            func.count(Document.id).label("doc_count"),
        )
        .where(Document.folder_id.in_(folder_ids))
        .where(Document.deleted_at.is_(None))
        .group_by(Document.folder_id)
    )
    doc_counts: dict[UUID, int] = {
        row.folder_id: row.doc_count for row in doc_count_result
    }

    # Build tree from flat list
    nodes: dict[UUID, FolderTreeNode] = {}
    root_nodes: list[FolderTreeNode] = []

    for folder in folders:
        node = FolderTreeNode(
            id=folder.id,
            name=folder.name,
            parent_id=folder.parent_id,
            materialized_path=folder.materialized_path,
            depth=folder.depth,
            sort_order=folder.sort_order,
            children=[],
            document_count=doc_counts.get(folder.id, 0),
        )
        nodes[folder.id] = node

    # Wire up parent-child relationships
    for folder in folders:
        node = nodes[folder.id]
        if folder.parent_id is not None and folder.parent_id in nodes:
            nodes[folder.parent_id].children.append(node)
        else:
            root_nodes.append(node)

    return root_nodes


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """
    Create a new folder in the specified scope.

    Validates that nesting depth does not exceed 5 levels. Computes
    the materialized_path from the parent folder's path.
    """
    await validate_scope(body.scope, body.scope_id, db)

    # For project-scoped folders, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if body.scope == "project":
        project = await db.get(Project, UUID(body.scope_id))
        if project:
            project_application_id = project.application_id

    # Validate depth and get parent path
    new_depth, parent_path = await validate_folder_depth(db, body.parent_id)

    folder = DocumentFolder(
        name=body.name,
        parent_id=body.parent_id,
        depth=new_depth,
        created_by=current_user.id,
    )
    set_scope_fks(folder, body.scope, body.scope_id)

    db.add(folder)
    await db.flush()

    # Compute materialized path (needs folder.id which is set after flush)
    folder.materialized_path = compute_materialized_path(parent_path, folder.id)

    await db.flush()
    await db.refresh(folder)

    # Broadcast folder created event
    await _broadcast_folder_event(
        MessageType.FOLDER_CREATED,
        folder,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return FolderResponse.model_validate(folder)


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    body: FolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FolderResponse:
    """
    Update a folder. If parent_id changes, recomputes materialized paths
    for this folder and all its descendants.
    """
    result = await db.execute(
        select(DocumentFolder).where(DocumentFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()

    if folder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Handle parent_id change (folder move)
    if "parent_id" in update_data and update_data["parent_id"] != folder.parent_id:
        new_parent_id = update_data["parent_id"]

        # Prevent moving folder under itself
        if new_parent_id is not None:
            target_result = await db.execute(
                select(DocumentFolder.materialized_path)
                .where(DocumentFolder.id == new_parent_id)
            )
            target_path = target_result.scalar_one_or_none()
            if target_path and f"/{folder_id}/" in target_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder under its own descendant",
                )

        # Validate new depth
        new_depth, parent_path = await validate_folder_depth(db, new_parent_id)
        old_path = folder.materialized_path
        old_depth = folder.depth

        # Update this folder
        folder.parent_id = new_parent_id
        folder.depth = new_depth
        new_path = compute_materialized_path(parent_path, folder.id)
        folder.materialized_path = new_path

        # Bulk update descendants
        depth_delta = new_depth - old_depth
        await update_descendant_paths(db, old_path, new_path, depth_delta)

    # Apply other updates
    for field in ("name", "sort_order"):
        if field in update_data:
            setattr(folder, field, update_data[field])

    folder.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(folder)

    # For project-scoped folders, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if folder.project_id:
        project = await db.get(Project, folder.project_id)
        if project:
            project_application_id = project.application_id

    # Broadcast folder updated event
    await _broadcast_folder_event(
        MessageType.FOLDER_UPDATED,
        folder,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a folder.

    Documents in this folder have folder_id set to NULL (unfiled) via
    the FK ondelete SET NULL constraint. Child folders are cascade-deleted
    via the FK ondelete CASCADE constraint.
    """
    result = await db.execute(
        select(DocumentFolder).where(DocumentFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()

    if folder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    # For project-scoped folders, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if folder.project_id:
        project = await db.get(Project, folder.project_id)
        if project:
            project_application_id = project.application_id

    # Broadcast folder deleted event before deletion (need folder data)
    await _broadcast_folder_event(
        MessageType.FOLDER_DELETED,
        folder,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    await db.delete(folder)
    await db.flush()
