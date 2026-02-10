"""Document Tag CRUD and assignment API endpoints.

Provides endpoints for managing tags within application and personal scopes,
and for assigning/unassigning tags on documents with scope compatibility
validation.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.document_tag import DocumentTag
from ..models.user import User
from ..schemas.document_tag import (
    TagCreate,
    TagResponse,
    TagUpdate,
)
from ..services.auth_service import get_current_user

router = APIRouter(
    prefix="/document-tags",
    tags=["document-tags"],
)


@router.get("", response_model=list[TagResponse])
async def list_tags(
    scope: Literal["application", "personal"] = Query(
        ..., description="Scope type"
    ),
    scope_id: UUID = Query(..., description="Application ID or User ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TagResponse]:
    """
    List tags for a given scope.

    Returns all tags within an application scope or a user's personal scope.
    """
    if scope == "application":
        query = select(DocumentTag).where(DocumentTag.application_id == scope_id)
    else:  # personal
        query = select(DocumentTag).where(DocumentTag.user_id == scope_id)

    query = query.order_by(DocumentTag.name)
    result = await db.execute(query)
    tags = result.scalars().all()

    return [TagResponse.model_validate(tag) for tag in tags]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """
    Create a new tag in the specified scope.

    Tags scoped to an application can be used by all documents in that
    application and its projects. Tags scoped to a user (personal) can
    only be used by that user's personal documents.
    """
    tag = DocumentTag(name=body.name, color=body.color)

    if body.scope == "application":
        tag.application_id = body.scope_id
    else:  # personal
        tag.user_id = body.scope_id

    db.add(tag)

    try:
        await db.flush()
    except Exception as e:
        # Check for unique constraint violation (duplicate tag name in scope)
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tag with name '{body.name}' already exists in this scope",
            )
        raise

    await db.refresh(tag)
    return TagResponse.model_validate(tag)


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    body: TagUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TagResponse:
    """
    Update a tag's name and/or color.
    """
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.id == tag_id)
    )
    tag = result.scalar_one_or_none()

    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag {tag_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    UPDATABLE_FIELDS = {"name", "color"}
    for field, value in update_data.items():
        if field in UPDATABLE_FIELDS:
            setattr(tag, field, value)

    try:
        await db.flush()
    except Exception as e:
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tag with name '{body.name}' already exists in this scope",
            )
        raise

    await db.refresh(tag)
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a tag. Cascades to remove all tag assignments.
    """
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.id == tag_id)
    )
    tag = result.scalar_one_or_none()

    if tag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag {tag_id} not found",
        )

    await db.delete(tag)
    await db.flush()
