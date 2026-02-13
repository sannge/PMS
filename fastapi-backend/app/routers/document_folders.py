"""Document folder CRUD and tree API endpoints.

Provides endpoints for managing document folders within the knowledge base.
Folders use a materialized path pattern for efficient tree queries and
support nesting up to 5 levels deep. All endpoints require authentication.
"""

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

logger = logging.getLogger(__name__)

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
from ..services.permission_service import PermissionService
from ..services.document_service import (
    check_name_uniqueness,
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


def _build_folder_broadcast(
    folder: DocumentFolder,
    actor_id: UUID,
    project_application_id: UUID | None = None,
) -> tuple[dict, list[str]]:
    """Build broadcast payload and target rooms for a folder event.

    Must be called BEFORE commit so folder attributes are accessible.
    Returns (data_dict, room_list) for use with _broadcast_to_rooms.
    """
    scope, scope_id = _get_folder_scope(folder)
    data = {
        "folder_id": str(folder.id),
        "scope": scope,
        "scope_id": scope_id,
        "parent_id": str(folder.parent_id) if folder.parent_id else None,
        "actor_id": str(actor_id),
        "timestamp": datetime.utcnow().isoformat(),
        "application_id": str(project_application_id) if project_application_id else None,
    }
    rooms: list[str] = []
    if folder.application_id:
        rooms.append(f"application:{folder.application_id}")
    elif folder.project_id:
        rooms.append(f"project:{folder.project_id}")
        if project_application_id:
            rooms.append(f"application:{project_application_id}")
    elif folder.user_id:
        rooms.append(f"user:{folder.user_id}")
    return data, rooms


async def _broadcast_to_rooms(
    message_type: MessageType,
    data: dict,
    rooms: list[str],
) -> None:
    """Broadcast a pre-built event payload to specific rooms.

    Used when broadcast data and room targets must be captured before commit
    (e.g. delete) but the broadcast itself must happen after commit so clients
    re-fetch committed data.
    """
    message = {"type": message_type.value, "data": data}
    for room in rooms:
        await manager.broadcast_to_room(room, message)


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
    perm_service = PermissionService(db)
    if not await perm_service.check_can_view_knowledge(current_user.id, scope, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view folders in this scope",
        )

    # Fetch all folders for scope
    scope_filter = get_scope_filter(DocumentFolder, scope, scope_id)
    result = await db.execute(
        select(DocumentFolder)
        .where(scope_filter)
        .order_by(DocumentFolder.materialized_path.asc(), DocumentFolder.name.asc())
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
    perm_service = PermissionService(db)
    if not await perm_service.check_can_edit_knowledge(current_user.id, body.scope, body.scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create folders in this scope",
        )

    await validate_scope(body.scope, body.scope_id, db)
    await check_name_uniqueness(db, body.name, body.scope, body.scope_id, body.parent_id)

    # For project-scoped folders, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if body.scope == "project":
        project = await db.get(Project, body.scope_id)
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

    # Capture broadcast data before commit (folder attrs needed)
    broadcast_data, broadcast_rooms = _build_folder_broadcast(
        folder, current_user.id, project_application_id,
    )

    await db.commit()
    await _broadcast_to_rooms(MessageType.FOLDER_CREATED, broadcast_data, broadcast_rooms)

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
        select(DocumentFolder)
        .options(lazyload("*"))
        .where(DocumentFolder.id == folder_id)
        .with_for_update()
    )
    folder = result.scalar_one_or_none()

    if folder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder {folder_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(folder)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this folder",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Check name uniqueness when name or parent changes
    if "name" in update_data or "parent_id" in update_data:
        new_name = update_data.get("name", folder.name)
        new_parent_id = update_data.get("parent_id", folder.parent_id)
        scope_type, scope_id_str = _get_folder_scope(folder)
        await check_name_uniqueness(
            db, new_name, scope_type, UUID(scope_id_str),
            new_parent_id, exclude_folder_id=folder.id,
        )

    # Handle parent_id change (folder move)
    if "parent_id" in update_data and update_data["parent_id"] != folder.parent_id:
        new_parent_id = update_data["parent_id"]

        # Prevent moving folder under itself
        if new_parent_id is not None:
            target_result = await db.execute(
                select(DocumentFolder.materialized_path)
                .where(DocumentFolder.id == new_parent_id)
                .with_for_update()
            )
            target_path = target_result.scalar_one_or_none()
            if target_path and f"/{folder_id}/" in target_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a folder under its own descendant",
                )

        # Validate new depth
        new_depth, parent_path = await validate_folder_depth(db, new_parent_id)

        # Validate that the deepest descendant won't exceed max depth
        max_descendant_depth_result = await db.execute(
            select(func.max(DocumentFolder.depth))
            .where(DocumentFolder.materialized_path.like(f"{folder.materialized_path}%"))
            .where(DocumentFolder.id != folder.id)
        )
        max_descendant_depth = max_descendant_depth_result.scalar()
        if max_descendant_depth is not None:
            # relative depth of deepest descendant from this folder
            subtree_height = max_descendant_depth - folder.depth
            if new_depth + subtree_height > 5:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Moving this folder would cause descendants to exceed maximum depth of 5 (deepest descendant would be at depth {new_depth + subtree_height})",
                )

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
    for field in ("name",):
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

    # Capture broadcast data before commit (folder attrs needed)
    broadcast_data, broadcast_rooms = _build_folder_broadcast(
        folder, current_user.id, project_application_id,
    )

    await db.commit()
    await _broadcast_to_rooms(MessageType.FOLDER_UPDATED, broadcast_data, broadcast_rooms)

    return FolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a folder.

    All documents in this folder and descendant folders are soft-deleted
    (moved to trash). Child folders are cascade-deleted via the FK
    ondelete CASCADE constraint.
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

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(folder)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this folder",
        )

    # For project-scoped folders, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if folder.project_id:
        project = await db.get(Project, folder.project_id)
        if project:
            project_application_id = project.application_id

    # Soft-delete all documents in this folder and descendant folders.
    # Must run BEFORE db.delete(folder), because the FK ondelete="SET NULL"
    # will null out folder_id on cascade, making documents unfindable.
    descendant_result = await db.execute(
        select(DocumentFolder.id)
        .where(DocumentFolder.materialized_path.like(f"{folder.materialized_path}%"))
    )
    all_folder_ids = [row[0] for row in descendant_result.all()]

    if all_folder_ids:
        now = datetime.utcnow()
        soft_delete_result = await db.execute(
            update(Document)
            .where(Document.folder_id.in_(all_folder_ids))
            .where(Document.deleted_at.is_(None))
            .values(deleted_at=now)
        )
        logger.info(
            "Soft-deleted %d documents in folder %s (descendant folders: %d)",
            soft_delete_result.rowcount,
            folder_id,
            len(all_folder_ids),
        )

    # Capture broadcast data before deletion (folder attrs unavailable after delete+commit)
    broadcast_data, broadcast_rooms = _build_folder_broadcast(
        folder, current_user.id, project_application_id,
    )

    await db.delete(folder)
    await db.flush()

    # Commit explicitly so data is persisted before the 204 response reaches
    # the client. FastAPI >= 0.115 runs yield-dependency cleanup (where
    # get_db commits) AFTER the response is sent — without this explicit
    # commit the client's onSuccess re-fetch would race against the commit
    # and could see stale (pre-soft-delete) data.
    await db.commit()

    # Broadcast AFTER commit so other clients re-fetch committed data
    await _broadcast_to_rooms(MessageType.FOLDER_DELETED, broadcast_data, broadcast_rooms)
