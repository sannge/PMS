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

router = APIRouter(
    prefix="/document-folders",
    tags=["document-folders"],
)


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

    await db.delete(folder)
    await db.flush()
