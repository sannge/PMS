"""Document CRUD API endpoints.

Provides endpoints for managing Documents within the knowledge base.
Documents support three scopes: application, project, and personal.
All endpoints require authentication. Includes trash/restore lifecycle
and tag assignment with scope compatibility validation.
"""

import asyncio
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, noload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.attachment import Attachment
from ..models.document import Document
from ..models.document_folder import DocumentFolder
from ..models.document_tag import DocumentTag, DocumentTagAssignment
from ..models.project import Project
from ..models.user import User
from ..models.project_member import ProjectMember
from ..schemas.document import (
    DocumentContentUpdate,
    DocumentCreate,
    DocumentListItem,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
    KnowledgePermissionsResponse,
    ProjectPermissionItem,
    ProjectsWithContentResponse,
    ScopesSummaryResponse,
)
from ..schemas.document_tag import TagAssignment, TagAssignmentResponse
from ..services.auth_service import get_current_user
from ..services.permission_service import PermissionService
from ..services.document_service import (
    check_name_uniqueness,
    cleanup_orphaned_attachments,
    decode_cursor,
    decode_title_cursor,
    encode_cursor,
    encode_title_cursor,
    get_scope_filter,
    save_document_content,
    set_scope_fks,
    validate_scope,
    validate_tag_scope,
)
from ..services.minio_service import MinIOService, MinIOServiceError, get_minio_service
from ..websocket.manager import manager, MessageType

import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


def _get_document_scope(doc: Document) -> tuple[str, str]:
    """Extract scope type and ID from a document."""
    if doc.application_id:
        return "application", str(doc.application_id)
    elif doc.project_id:
        return "project", str(doc.project_id)
    elif doc.user_id:
        return "personal", str(doc.user_id)
    return "unknown", ""


async def _broadcast_document_event(
    message_type: MessageType,
    doc: Document,
    actor_id: UUID | None = None,
    extra_data: dict | None = None,
    project_application_id: UUID | None = None,
) -> None:
    """Broadcast a document event to the appropriate room(s).

    Args:
        message_type: The WebSocket message type
        doc: The document being affected
        actor_id: The user who performed the action (for client-side filtering)
        extra_data: Additional data to include in the broadcast
        project_application_id: For project-scoped docs, the parent application ID
            (so we can also broadcast to the application room)
    """
    scope, scope_id = _get_document_scope(doc)

    data = {
        "document_id": str(doc.id),
        "scope": scope,
        "scope_id": scope_id,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "actor_id": str(actor_id) if actor_id else None,
        "timestamp": doc.updated_at.isoformat() if doc.updated_at else datetime.utcnow().isoformat(),
        # Include application_id for project-scoped items so frontend can invalidate app queries
        "application_id": str(project_application_id) if project_application_id else None,
    }
    if extra_data:
        data.update(extra_data)

    message = {"type": message_type.value, "data": data}

    # Determine the room(s) to broadcast to
    if doc.application_id:
        await manager.broadcast_to_room(f"application:{doc.application_id}", message)
    elif doc.project_id:
        # Broadcast to project room
        await manager.broadcast_to_room(f"project:{doc.project_id}", message)
        # Also broadcast to application room so users viewing the app tree get updates
        if project_application_id:
            await manager.broadcast_to_room(f"application:{project_application_id}", message)
    else:
        # Personal docs - broadcast to user room
        await manager.broadcast_to_room(f"user:{doc.user_id}", message)


# ============================================================================
# Trash endpoint (MUST be before /{document_id} to avoid path matching)
# ============================================================================


@router.get("/trash", response_model=DocumentListResponse)
async def list_trash(
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(30, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """
    List soft-deleted documents for the current user (trash).

    Returns documents where deleted_at IS NOT NULL and created_by matches
    the current user. Ordered by deleted_at DESC for most-recently-trashed first.
    """
    query = (
        select(Document)
        .where(Document.deleted_at.isnot(None))
        .where(Document.created_by == current_user.id)
        .options(noload("*"))
    )

    # Cursor pagination (keyset: created_at DESC, id DESC)
    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Document.created_at < cursor_created_at,
                and_(
                    Document.created_at == cursor_created_at,
                    Document.id < cursor_id,
                ),
            )
        )

    query = query.order_by(Document.created_at.desc(), Document.id.desc())
    query = query.limit(limit + 1)

    result = await db.execute(query)
    documents = result.scalars().all()

    has_next = len(documents) > limit
    if has_next:
        documents = documents[:limit]

    items = [DocumentListItem.model_validate(doc) for doc in documents]

    next_cursor = None
    if has_next and documents:
        last = documents[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return DocumentListResponse(items=items, next_cursor=next_cursor)


# ============================================================================
# Scopes summary endpoint (MUST be before /{document_id})
# ============================================================================


@router.get("/scopes-summary", response_model=ScopesSummaryResponse)
async def get_scopes_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return scopes available for knowledge base tabs.

    Returns all applications the user is a member of (not just those with documents)
    so users can create documents in empty applications.
    """
    # Personal docs exist?
    personal_count = await db.scalar(
        select(func.count(Document.id))
        .where(Document.user_id == current_user.id)
        .where(Document.deleted_at.is_(None))
    )

    # Applications where user is an ApplicationMember
    member_apps = await db.execute(
        select(Application.id, Application.name, Application.description, ApplicationMember.role)
        .join(ApplicationMember, ApplicationMember.application_id == Application.id)
        .where(ApplicationMember.user_id == current_user.id)
        .order_by(Application.created_at.asc())
    )
    member_rows = member_apps.all()

    # Applications where user is owner_id but NOT in ApplicationMember table
    member_app_ids = [r.id for r in member_rows]
    owner_filter = [Application.owner_id == current_user.id]
    if member_app_ids:
        owner_filter.append(Application.id.notin_(member_app_ids))
    owner_apps = await db.execute(
        select(Application.id, Application.name, Application.description)
        .where(*owner_filter)
        .order_by(Application.created_at.asc())
    )
    owner_rows = owner_apps.all()

    applications = [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "user_role": r.role,
        }
        for r in member_rows
    ] + [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "user_role": "owner",
        }
        for r in owner_rows
    ]

    return {
        "has_personal_docs": (personal_count or 0) > 0,
        "applications": applications,
    }


@router.get("/projects-with-content", response_model=ProjectsWithContentResponse)
async def get_projects_with_content(
    application_id: UUID = Query(..., description="Application ID to check projects for"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectsWithContentResponse:
    """
    Return project IDs that have knowledge content (documents or folders).

    Used by the application tree to filter out empty projects before rendering.
    Uses UNION of two EXISTS-optimized queries for efficiency.
    """
    # Verify user is an application member before exposing project content info
    perm_service = PermissionService(db)
    if not await perm_service.is_application_member(current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this application's projects",
        )

    # Projects with documents
    projects_with_docs = select(Document.project_id).where(
        Document.project_id.isnot(None),
        Document.deleted_at.is_(None),
        Document.project_id.in_(
            select(Project.id).where(Project.application_id == application_id)
        ),
    ).distinct()

    # Projects with folders
    projects_with_folders = select(DocumentFolder.project_id).where(
        DocumentFolder.project_id.isnot(None),
        DocumentFolder.project_id.in_(
            select(Project.id).where(Project.application_id == application_id)
        ),
    ).distinct()

    # Combine with UNION
    combined = projects_with_docs.union(projects_with_folders)
    result = await db.execute(combined)
    project_ids = [str(row[0]) for row in result.all()]

    # Determine per-project edit permissions
    app_role = await perm_service.get_user_application_role(
        current_user.id, application_id
    )

    project_permissions: list[ProjectPermissionItem] = []
    if app_role == "owner":
        # App owners can edit all projects
        project_permissions = [
            ProjectPermissionItem(project_id=pid, can_edit=True)
            for pid in project_ids
        ]
    elif app_role in ("editor", "viewer"):
        # Check ProjectMember for each project in batch
        project_uuids = [UUID(pid) for pid in project_ids]
        if project_uuids:
            pm_result = await db.execute(
                select(ProjectMember.project_id)
                .where(
                    ProjectMember.project_id.in_(project_uuids),
                    ProjectMember.user_id == current_user.id,
                )
            )
            member_project_ids = {str(row[0]) for row in pm_result.all()}
        else:
            member_project_ids = set()

        project_permissions = [
            ProjectPermissionItem(
                project_id=pid,
                can_edit=(app_role == "editor" and pid in member_project_ids),
            )
            for pid in project_ids
        ]
    else:
        # Not a member — no edit on any project
        project_permissions = [
            ProjectPermissionItem(project_id=pid, can_edit=False)
            for pid in project_ids
        ]

    return ProjectsWithContentResponse(
        project_ids=project_ids,
        project_permissions=project_permissions,
    )


# ============================================================================
# Knowledge permissions endpoint (MUST be before /{document_id})
# ============================================================================


@router.get("/knowledge-permissions", response_model=KnowledgePermissionsResponse)
async def get_knowledge_permissions(
    scope: Literal["application", "project", "personal"] = Query(
        ..., description="Scope type"
    ),
    scope_id: UUID = Query(..., description="Scope entity ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgePermissionsResponse:
    """Check view/edit permissions for a knowledge scope."""
    perm_service = PermissionService(db)
    can_view = await perm_service.check_can_view_knowledge(
        current_user.id, scope, scope_id
    )
    can_edit = await perm_service.check_can_edit_knowledge(
        current_user.id, scope, scope_id
    )

    # Determine owner status (for force-take lock capability)
    is_owner = False
    if scope == "personal":
        is_owner = scope_id == current_user.id
    elif scope == "application":
        role = await perm_service.get_user_application_role(current_user.id, scope_id)
        is_owner = role == "owner"
    elif scope == "project":
        project = await perm_service.get_project_with_application(scope_id)
        if project:
            role = await perm_service.get_user_application_role(
                current_user.id, project.application_id
            )
            is_owner = role == "owner"

    return KnowledgePermissionsResponse(
        can_view=can_view, can_edit=can_edit, is_owner=is_owner
    )


# ============================================================================
# Standard CRUD endpoints
# ============================================================================


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    scope: Literal["application", "project", "personal"] = Query(
        ..., description="Scope type"
    ),
    scope_id: UUID = Query(..., description="Scope entity ID"),
    folder_id: Optional[UUID] = Query(
        None, description="Filter by folder ID (omit for unfiled)"
    ),
    include_unfiled: bool = Query(
        False, description="If true and folder_id is omitted, return unfiled documents"
    ),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(30, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """
    List documents for a scope with cursor-based pagination.

    Documents are ordered alphabetically by title ASC, id ASC. Only non-deleted
    documents are returned. When folder_id is omitted and include_unfiled
    is True, returns documents with no folder assignment.
    """
    perm_service = PermissionService(db)
    if not await perm_service.check_can_view_knowledge(current_user.id, scope, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view documents in this scope",
        )

    # Build base query
    query = (
        select(Document)
        .where(get_scope_filter(Document, scope, scope_id))
        .where(Document.deleted_at.is_(None))
        .options(noload("*"))
    )

    # Folder filter
    if folder_id is not None:
        query = query.where(Document.folder_id == folder_id)
    elif include_unfiled:
        query = query.where(Document.folder_id.is_(None))

    # Cursor pagination (keyset: title ASC, id ASC)
    # Gracefully ignore stale cursors (e.g. old created_at-based format from cache)
    if cursor:
        try:
            cursor_title, cursor_id = decode_title_cursor(cursor)
            query = query.where(
                or_(
                    Document.title > cursor_title,
                    and_(
                        Document.title == cursor_title,
                        Document.id > cursor_id,
                    ),
                )
            )
        except HTTPException:
            pass  # Stale cursor — start from the beginning

    # Order alphabetically by title (frontend applies case-insensitive sort via select)
    query = query.order_by(Document.title.asc(), Document.id.asc())
    query = query.limit(limit + 1)

    result = await db.execute(query)
    documents = result.scalars().all()

    # Determine next cursor
    has_next = len(documents) > limit
    if has_next:
        documents = documents[:limit]

    items = [DocumentListItem.model_validate(doc) for doc in documents]

    next_cursor = None
    if has_next and documents:
        last = documents[-1]
        next_cursor = encode_title_cursor(last.title, last.id)

    return DocumentListResponse(items=items, next_cursor=next_cursor)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Create a new document in the specified scope.

    Validates that the scope entity exists and sets the appropriate FK.
    """
    perm_service = PermissionService(db)
    if not await perm_service.check_can_edit_knowledge(current_user.id, body.scope, body.scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create documents in this scope",
        )

    await validate_scope(body.scope, body.scope_id, db)
    await check_name_uniqueness(db, body.title, body.scope, body.scope_id, body.folder_id)

    # For project-scoped documents, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if body.scope == "project":
        project = await db.get(Project, body.scope_id)
        if project:
            project_application_id = project.application_id

    document = Document(
        title=body.title,
        content_json=body.content_json,
        created_by=current_user.id,
    )
    set_scope_fks(document, body.scope, body.scope_id)

    if body.folder_id is not None:
        document.folder_id = body.folder_id

    db.add(document)
    await db.flush()
    await db.refresh(document)

    # Extract search data BEFORE commit while ORM attributes are still loaded
    from ..services.search_service import build_search_doc_data, index_document_from_data
    search_doc_data = build_search_doc_data(document, project_application_id=project_application_id)

    # Commit before broadcast so clients re-fetch committed data
    await db.commit()

    # Fire-and-forget: index new document for search (non-blocking)
    asyncio.create_task(index_document_from_data(search_doc_data))

    # Broadcast document created event
    await _broadcast_document_event(
        MessageType.DOCUMENT_CREATED,
        document,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return DocumentResponse.model_validate(document)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Get a single document by ID, including all content fields.

    Returns 404 if the document does not exist or is soft-deleted.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_view_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this document",
        )

    return DocumentResponse.model_validate(document)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> DocumentResponse:
    """
    Update a document with optimistic concurrency control.

    The client must send the current row_version. If it does not match
    the database value, a 409 Conflict is returned. On success, row_version
    is incremented.
    """
    # SELECT with FOR UPDATE to lock the row and prevent concurrent modification.
    # lazyload('*') suppresses lazy="joined" relationships (folder, creator) which
    # generate LEFT OUTER JOINs incompatible with FOR UPDATE on nullable FK sides.
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
        .options(lazyload('*'))
        .with_for_update()
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this document",
        )

    # Optimistic concurrency check (safe under FOR UPDATE lock)
    if document.row_version != body.row_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document has been modified by another user (expected version {body.row_version}, current {document.row_version})",
        )

    # Check name uniqueness when title or folder changes
    update_data = body.model_dump(exclude_unset=True, exclude={"row_version"})
    if "title" in update_data or "folder_id" in update_data:
        new_title = update_data.get("title", document.title)
        new_folder_id = update_data.get("folder_id", document.folder_id)
        scope_type, scope_id_str = _get_document_scope(document)
        await check_name_uniqueness(
            db, new_title, scope_type, UUID(scope_id_str),
            new_folder_id, exclude_document_id=document.id,
        )

    # Apply updates (only allowed fields)
    UPDATABLE_FIELDS = {"title", "folder_id", "content_json"}
    for field, value in update_data.items():
        if field in UPDATABLE_FIELDS:
            setattr(document, field, value)

    # Increment version
    document.row_version += 1
    document.updated_at = datetime.utcnow()

    await db.flush()

    # Clean up orphaned attachments if content was updated
    if "content_json" in update_data and document.content_json:
        try:
            await cleanup_orphaned_attachments(document_id, document.content_json, db, minio)
        except Exception:
            logger.exception(
                "Failed to clean up orphaned attachments for document %s",
                document_id,
            )

    await db.refresh(document)

    # For project-scoped documents, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if document.project_id:
        project = await db.get(Project, document.project_id)
        if project:
            project_application_id = project.application_id

    # Extract search data BEFORE commit while ORM attributes are still loaded
    from ..services.search_service import build_search_doc_data, index_document_from_data
    search_doc_data = build_search_doc_data(document, project_application_id=project_application_id)

    # Commit before broadcast so clients re-fetch committed data
    await db.commit()

    # Fire-and-forget: update search index (non-blocking)
    asyncio.create_task(index_document_from_data(search_doc_data))

    # Broadcast document updated event
    await _broadcast_document_event(
        MessageType.DOCUMENT_UPDATED,
        document,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return DocumentResponse.model_validate(document)


@router.put("/{document_id}/content", response_model=DocumentResponse)
async def save_content(
    document_id: UUID,
    body: DocumentContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> DocumentResponse:
    """
    Auto-save document content with optimistic concurrency control.

    The client must send the current row_version. If it does not match
    the database value, a 409 Conflict is returned indicating the document
    was modified by another user/session. On success, content is updated
    and row_version is incremented.
    """
    # Permission check before saving
    doc_result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    doc_for_perm = doc_result.scalar_one_or_none()
    if doc_for_perm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(doc_for_perm)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit this document",
        )

    document, search_doc_data = await save_document_content(
        document_id=document_id,
        content_json=body.content_json,
        row_version=body.row_version,
        user_id=current_user.id,
        db=db,
        minio=minio,
    )

    # Broadcast document updated event so other users see fresh content
    project_application_id: UUID | None = None
    if document.project_id:
        project = await db.get(Project, document.project_id)
        if project:
            project_application_id = project.application_id

    # Commit before broadcast so clients re-fetch committed data
    await db.commit()

    # Fire-and-forget: update search index AFTER commit (non-blocking)
    if search_doc_data:
        from ..services.search_service import index_document_from_data
        asyncio.create_task(index_document_from_data(search_doc_data))

    await _broadcast_document_event(
        MessageType.DOCUMENT_UPDATED,
        document,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Soft delete a document (move to trash).

    Sets deleted_at to the current timestamp. The document can be restored
    via POST /documents/{id}/restore or permanently deleted via
    DELETE /documents/{id}/permanent.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this document",
        )

    # For project-scoped documents, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if document.project_id:
        project = await db.get(Project, document.project_id)
        if project:
            project_application_id = project.application_id

    document.deleted_at = datetime.utcnow()
    await db.flush()

    # Extract document ID before commit for safe background task usage
    doc_id_for_search = document.id

    # Commit before broadcast so clients re-fetch committed data
    await db.commit()

    # Fire-and-forget: mark document as deleted in search index (non-blocking)
    from ..services.search_service import index_document_soft_delete
    asyncio.create_task(index_document_soft_delete(doc_id_for_search))

    # Broadcast document deleted event
    await _broadcast_document_event(
        MessageType.DOCUMENT_DELETED,
        document,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )


# ============================================================================
# Restore and permanent delete endpoints
# ============================================================================


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Restore a soft-deleted document from trash.

    Sets deleted_at back to None. Returns 404 if the document does not
    exist or is not in the trash.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.isnot(None))
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found in trash",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to restore this document",
        )

    # Check name uniqueness before restoring
    scope_type, scope_id_str = _get_document_scope(document)
    await check_name_uniqueness(
        db, document.title, scope_type, UUID(scope_id_str),
        document.folder_id, exclude_document_id=document.id,
    )

    document.deleted_at = None
    await db.flush()
    await db.refresh(document)

    # For project-scoped documents, get the parent application_id for broadcasting
    project_application_id: UUID | None = None
    if document.project_id:
        project = await db.get(Project, document.project_id)
        if project:
            project_application_id = project.application_id

    # Extract document ID before commit for safe background task usage
    doc_id_for_search = document.id

    # Commit before broadcast so clients re-fetch committed data
    await db.commit()

    # Fire-and-forget: restore document in search index (non-blocking)
    from ..services.search_service import index_document_restore
    asyncio.create_task(index_document_restore(doc_id_for_search))

    # Broadcast document restored event (appears as created to other clients)
    await _broadcast_document_event(
        MessageType.DOCUMENT_CREATED,
        document,
        actor_id=current_user.id,
        project_application_id=project_application_id,
    )

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanent_delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    minio: MinIOService = Depends(get_minio_service),
) -> None:
    """
    Permanently delete a document (hard delete).

    This action is irreversible. The document and all its tag assignments
    are removed from the database.
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.isnot(None))
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found in trash",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to permanently delete this document",
        )

    # Delete all attachments for this document (MinIO files + DB records)
    attach_result = await db.execute(
        select(Attachment).where(
            Attachment.entity_type == "document",
            Attachment.entity_id == document_id,
        )
    )
    doc_attachments = attach_result.scalars().all()

    for attachment in doc_attachments:
        if attachment.minio_bucket and attachment.minio_key:
            try:
                minio.delete_file(
                    bucket=attachment.minio_bucket,
                    object_name=attachment.minio_key,
                )
            except MinIOServiceError:
                logger.warning(
                    "Failed to delete MinIO file for attachment %s during "
                    "document permanent deletion",
                    attachment.id,
                )
        await db.delete(attachment)

    await db.delete(document)
    await db.flush()
    await db.commit()

    # Synchronous: remove document from search index (ghost results are worse than slow delete)
    try:
        from ..services.search_service import remove_document_from_index
        await remove_document_from_index(document_id)
    except Exception:
        logger.warning("Failed to remove document %s from search index", document_id)


# ============================================================================
# Tag assignment endpoints
# ============================================================================


@router.post(
    "/{document_id}/tags",
    response_model=TagAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_tag_to_document(
    document_id: UUID,
    body: TagAssignment,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagAssignmentResponse:
    """
    Assign a tag to a document.

    Validates that the tag's scope is compatible with the document's scope:
    - Application-scoped documents can use application-scoped tags from the same application
    - Project-scoped documents can use tags from their parent application
    - Personal documents can only use personal tags from the same user

    Returns 409 if the tag is already assigned.
    """
    # Fetch document
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify tags on this document",
        )

    # Fetch tag
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.id == body.tag_id)
    )
    tag = result.scalar_one_or_none()

    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag {body.tag_id} not found",
        )

    # Validate scope compatibility
    is_compatible = await validate_tag_scope(db, document, tag)
    if not is_compatible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag scope is not compatible with document scope",
        )

    # Check for duplicate assignment
    result = await db.execute(
        select(DocumentTagAssignment).where(
            DocumentTagAssignment.document_id == document_id,
            DocumentTagAssignment.tag_id == body.tag_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tag is already assigned to this document",
        )

    assignment = DocumentTagAssignment(
        document_id=document_id,
        tag_id=body.tag_id,
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)

    return TagAssignmentResponse.model_validate(assignment)


@router.delete(
    "/{document_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_tag_from_document(
    document_id: UUID,
    tag_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a tag assignment from a document.
    """
    # Fetch document for permission check
    doc_result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.deleted_at.is_(None))
    )
    document = doc_result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    perm_service = PermissionService(db)
    scope_type, scope_id = PermissionService.resolve_entity_scope(document)
    if not await perm_service.check_can_edit_knowledge(current_user.id, scope_type, scope_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify tags on this document",
        )

    result = await db.execute(
        select(DocumentTagAssignment).where(
            DocumentTagAssignment.document_id == document_id,
            DocumentTagAssignment.tag_id == tag_id,
        )
    )
    assignment = result.scalar_one_or_none()

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag assignment not found",
        )

    await db.delete(assignment)
    await db.flush()
