"""Document CRUD API endpoints.

Provides endpoints for managing Documents within the knowledge base.
Documents support three scopes: application, project, and personal.
All endpoints require authentication. Includes trash/restore lifecycle
and tag assignment with scope compatibility validation.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document import Document
from ..models.document_tag import DocumentTag, DocumentTagAssignment
from ..models.user import User
from ..schemas.document import (
    DocumentContentUpdate,
    DocumentCreate,
    DocumentListItem,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from ..schemas.document_tag import TagAssignment, TagAssignmentResponse
from ..services.auth_service import get_current_user
from ..services.document_service import (
    decode_cursor,
    encode_cursor,
    get_scope_filter,
    save_document_content,
    set_scope_fks,
    validate_scope,
    validate_tag_scope,
)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


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

    Documents are ordered by created_at DESC, id DESC. Only non-deleted
    documents are returned. When folder_id is omitted and include_unfiled
    is True, returns documents with no folder assignment.
    """
    # Build base query
    query = (
        select(Document)
        .where(get_scope_filter(Document, scope, scope_id))
        .where(Document.deleted_at.is_(None))
    )

    # Folder filter
    if folder_id is not None:
        query = query.where(Document.folder_id == folder_id)
    elif include_unfiled:
        query = query.where(Document.folder_id.is_(None))

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

    # Order and limit (fetch one extra to determine if there's a next page)
    query = query.order_by(Document.created_at.desc(), Document.id.desc())
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
        next_cursor = encode_cursor(last.created_at, last.id)

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
    await validate_scope(body.scope, body.scope_id, db)

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

    return DocumentResponse.model_validate(document)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Update a document with optimistic concurrency control.

    The client must send the current row_version. If it does not match
    the database value, a 409 Conflict is returned. On success, row_version
    is incremented.
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

    # Optimistic concurrency check
    if document.row_version != body.row_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document has been modified by another user (expected version {body.row_version}, current {document.row_version})",
        )

    # Apply updates
    update_data = body.model_dump(exclude_unset=True, exclude={"row_version"})
    for field, value in update_data.items():
        setattr(document, field, value)

    # Increment version
    document.row_version += 1
    document.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(document)

    return DocumentResponse.model_validate(document)


@router.put("/{document_id}/content", response_model=DocumentResponse)
async def save_content(
    document_id: UUID,
    body: DocumentContentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Auto-save document content with optimistic concurrency control.

    The client must send the current row_version. If it does not match
    the database value, a 409 Conflict is returned indicating the document
    was modified by another user/session. On success, content is updated
    and row_version is incremented.
    """
    document = await save_document_content(
        document_id=document_id,
        content_json=body.content_json,
        row_version=body.row_version,
        user_id=current_user.id,
        db=db,
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

    document.deleted_at = datetime.utcnow()
    await db.flush()


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

    document.deleted_at = None
    await db.flush()
    await db.refresh(document)

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanent_delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Permanently delete a document (hard delete).

    This action is irreversible. The document and all its tag assignments
    are removed from the database.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    await db.delete(document)
    await db.flush()


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
