"""Notes CRUD API endpoints with hierarchy support.

Provides endpoints for managing Notes within Applications.
Notes support hierarchical organization through parent-child relationships
for creating sections/subsections similar to OneNote.
All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.application import Application
from ..models.note import Note
from ..models.user import User
from ..schemas.note import (
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    NoteWithChildren,
    NoteTree,
)
from ..services.auth_service import get_current_user

router = APIRouter(tags=["Notes"])


async def verify_application_ownership(
    application_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> Application:
    """
    Verify that the application exists and the user owns it.

    Args:
        application_id: The UUID of the application
        current_user: The authenticated user
        db: Database session

    Returns:
        Application: The verified application

    Raises:
        HTTPException: If application not found or user doesn't own it
    """
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    if application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this application.",
        )

    return application


async def verify_note_access(
    note_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> Note:
    """
    Verify that the note exists and the user has access via application ownership.

    Args:
        note_id: The UUID of the note
        current_user: The authenticated user
        db: Database session

    Returns:
        Note: The verified note

    Raises:
        HTTPException: If note not found or user doesn't have access
    """
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID {note_id} not found",
        )

    # Verify ownership through the parent application
    result = await db.execute(select(Application).where(Application.id == note.application_id))
    application = result.scalar_one_or_none()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this note's application.",
        )

    return note


def build_note_tree(
    notes: List[Note],
    parent_id: Optional[UUID] = None,
) -> List[NoteTree]:
    """
    Build a hierarchical tree structure from a flat list of notes.

    Args:
        notes: Flat list of all notes
        parent_id: ID of the parent note (None for root notes)

    Returns:
        List[NoteTree]: Hierarchical tree of notes
    """
    tree = []
    for note in notes:
        if note.parent_id == parent_id:
            children = build_note_tree(notes, note.id)
            note_tree = NoteTree(
                id=note.id,
                application_id=note.application_id,
                parent_id=note.parent_id,
                title=note.title,
                content=note.content,
                tab_order=note.tab_order,
                created_by=note.created_by,
                created_at=note.created_at,
                updated_at=note.updated_at,
                children=children,
            )
            tree.append(note_tree)
    # Sort by tab_order
    tree.sort(key=lambda x: x.tab_order)
    return tree


# ============================================================================
# Application-nested endpoints (for listing and creating notes)
# ============================================================================


@router.get(
    "/api/applications/{application_id}/notes",
    response_model=List[NoteWithChildren],
    summary="List all notes in an application",
    description="Get all notes within a specific application.",
    responses={
        200: {"description": "List of notes retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Application not found"},
    },
)
async def list_notes(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term for note title"),
    parent_id: Optional[UUID] = Query(None, description="Filter by parent note ID (use 'root' for root notes)"),
    root_only: bool = Query(False, description="Only return root-level notes (no parent)"),
) -> List[NoteWithChildren]:
    """
    List all notes within an application.

    - **application_id**: ID of the parent application
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **search**: Optional search term to filter by title
    - **parent_id**: Optional filter by parent note ID
    - **root_only**: Only return root-level notes (no parent)

    Returns notes with their children counts.
    """
    # Verify application ownership
    await verify_application_ownership(application_id, current_user, db)

    # Build subquery for counting children
    children_count_subquery = (
        select(
            Note.parent_id,
            func.count(Note.id).label("children_count"),
        )
        .where(Note.parent_id.isnot(None))
        .group_by(Note.parent_id)
        .subquery()
    )

    query = (
        select(
            Note,
            func.coalesce(children_count_subquery.c.children_count, 0).label("children_count"),
        )
        .outerjoin(children_count_subquery, Note.id == children_count_subquery.c.parent_id)
        .where(Note.application_id == application_id)
    )

    # Apply search filter if provided
    if search:
        query = query.where(Note.title.ilike(f"%{search}%"))

    # Apply parent filter if provided
    if root_only:
        query = query.where(Note.parent_id.is_(None))
    elif parent_id:
        query = query.where(Note.parent_id == parent_id)

    # Order by tab_order then by title
    query = query.order_by(Note.tab_order.asc(), Note.title.asc())

    # Apply pagination
    result = await db.execute(query.offset(skip).limit(limit))
    results = result.all()

    # Convert to response format
    notes = []
    for note, children_count in results:
        note_response = NoteWithChildren(
            id=note.id,
            application_id=note.application_id,
            parent_id=note.parent_id,
            title=note.title,
            content=note.content,
            tab_order=note.tab_order,
            created_by=note.created_by,
            created_at=note.created_at,
            updated_at=note.updated_at,
            children_count=children_count,
        )
        notes.append(note_response)

    return notes


@router.get(
    "/api/applications/{application_id}/notes/tree",
    response_model=List[NoteTree],
    summary="Get notes as a hierarchical tree",
    description="Get all notes within an application organized as a tree structure.",
    responses={
        200: {"description": "Note tree retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Application not found"},
    },
)
async def get_note_tree(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> List[NoteTree]:
    """
    Get all notes within an application as a hierarchical tree.

    Returns the complete note tree structure with all children nested.
    Useful for rendering the note sidebar/navigation.
    """
    # Verify application ownership
    await verify_application_ownership(application_id, current_user, db)

    # Get all notes for this application
    result = await db.execute(
        select(Note)
        .where(Note.application_id == application_id)
        .order_by(Note.tab_order.asc(), Note.title.asc())
    )
    notes = list(result.scalars().all())

    # Build and return the tree
    return build_note_tree(notes)


@router.post(
    "/api/applications/{application_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new note",
    description="Create a new note within an application.",
    responses={
        201: {"description": "Note created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Application or parent note not found"},
    },
)
async def create_note(
    application_id: UUID,
    note_data: NoteCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """
    Create a new note within an application.

    - **title**: Note title (required, 1-255 characters)
    - **content**: Rich text content - HTML or JSON (optional)
    - **tab_order**: Order of the note in tab bar (default: 0)
    - **parent_id**: ID of parent note for creating sections (optional)

    The note will be created under the specified application.
    Creator will be set to the current user.
    """
    # Verify application ownership
    await verify_application_ownership(application_id, current_user, db)

    # Validate that application_id in body matches URL
    if note_data.application_id != application_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application ID in request body does not match URL parameter",
        )

    # Validate parent note if provided
    if note_data.parent_id:
        result = await db.execute(
            select(Note).where(
                Note.id == note_data.parent_id,
                Note.application_id == application_id,
            )
        )
        parent_note = result.scalar_one_or_none()

        if not parent_note:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent note not found or does not belong to this application",
            )

    # Calculate tab_order if not provided (append to end)
    if note_data.tab_order == 0:
        result = await db.execute(
            select(func.max(Note.tab_order)).where(
                Note.application_id == application_id,
                Note.parent_id == note_data.parent_id,
            )
        )
        max_order = result.scalar() or 0
        tab_order = max_order + 1
    else:
        tab_order = note_data.tab_order

    # Create new note instance
    note = Note(
        application_id=application_id,
        parent_id=note_data.parent_id,
        title=note_data.title,
        content=note_data.content,
        tab_order=tab_order,
        created_by=current_user.id,
    )

    # Save to database
    db.add(note)
    await db.commit()
    await db.refresh(note)

    return note


# ============================================================================
# Direct note endpoints (for getting, updating, and deleting individual notes)
# ============================================================================


@router.get(
    "/api/notes/{note_id}",
    response_model=NoteWithChildren,
    summary="Get a note by ID",
    description="Get details of a specific note.",
    responses={
        200: {"description": "Note retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Note not found"},
    },
)
async def get_note(
    note_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> NoteWithChildren:
    """
    Get a specific note by its ID.

    Returns the note with its children count.
    Only the application owner can access their notes.
    """
    # Query note with children count
    children_count_subquery = (
        select(
            Note.parent_id,
            func.count(Note.id).label("children_count"),
        )
        .where(Note.parent_id.isnot(None))
        .group_by(Note.parent_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Note,
            func.coalesce(children_count_subquery.c.children_count, 0).label("children_count"),
        )
        .outerjoin(children_count_subquery, Note.id == children_count_subquery.c.parent_id)
        .where(Note.id == note_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID {note_id} not found",
        )

    note, children_count = row

    # Verify ownership through the parent application
    result = await db.execute(select(Application).where(Application.id == note.application_id))
    application = result.scalar_one_or_none()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this note's application.",
        )

    return NoteWithChildren(
        id=note.id,
        application_id=note.application_id,
        parent_id=note.parent_id,
        title=note.title,
        content=note.content,
        tab_order=note.tab_order,
        created_by=note.created_by,
        created_at=note.created_at,
        updated_at=note.updated_at,
        children_count=children_count,
    )


@router.get(
    "/api/notes/{note_id}/children",
    response_model=List[NoteWithChildren],
    summary="Get children of a note",
    description="Get all child notes of a specific note.",
    responses={
        200: {"description": "Child notes retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Note not found"},
    },
)
async def get_note_children(
    note_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
) -> List[NoteWithChildren]:
    """
    Get all child notes of a specific note.

    Returns children notes with their own children counts.
    Useful for lazy-loading nested sections.
    """
    # Verify the parent note exists and user has access
    await verify_note_access(note_id, current_user, db)

    # Query children with their children counts
    children_count_subquery = (
        select(
            Note.parent_id,
            func.count(Note.id).label("children_count"),
        )
        .where(Note.parent_id.isnot(None))
        .group_by(Note.parent_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Note,
            func.coalesce(children_count_subquery.c.children_count, 0).label("children_count"),
        )
        .outerjoin(children_count_subquery, Note.id == children_count_subquery.c.parent_id)
        .where(Note.parent_id == note_id)
        .order_by(Note.tab_order.asc(), Note.title.asc())
        .offset(skip)
        .limit(limit)
    )
    results = result.all()

    # Convert to response format
    notes = []
    for note, children_count in results:
        note_response = NoteWithChildren(
            id=note.id,
            application_id=note.application_id,
            parent_id=note.parent_id,
            title=note.title,
            content=note.content,
            tab_order=note.tab_order,
            created_by=note.created_by,
            created_at=note.created_at,
            updated_at=note.updated_at,
            children_count=children_count,
        )
        notes.append(note_response)

    return notes


@router.put(
    "/api/notes/{note_id}",
    response_model=NoteResponse,
    summary="Update a note",
    description="Update an existing note's details.",
    responses={
        200: {"description": "Note updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Note not found"},
    },
)
async def update_note(
    note_id: UUID,
    note_data: NoteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """
    Update an existing note.

    - **title**: New note title (optional, 1-255 characters)
    - **content**: New rich text content (optional)
    - **tab_order**: New tab order (optional)
    - **parent_id**: New parent note ID (optional) - use to move note in hierarchy

    Only the application owner can update their notes.
    """
    # Verify access and get note
    note = await verify_note_access(note_id, current_user, db)

    # Update fields if provided
    update_data = note_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided",
        )

    # Validate parent note if being updated
    if "parent_id" in update_data and update_data["parent_id"]:
        # Cannot set self as parent
        if update_data["parent_id"] == note_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Note cannot be its own parent",
            )

        # Cannot set a descendant as parent (would create cycle)
        async def is_descendant(potential_parent_id: UUID, check_note_id: UUID) -> bool:
            """Check if check_note_id is a descendant of potential_parent_id."""
            result = await db.execute(select(Note).where(Note.id == potential_parent_id))
            parent = result.scalar_one_or_none()
            while parent:
                if parent.id == check_note_id:
                    return True
                if parent.parent_id:
                    result = await db.execute(select(Note).where(Note.id == parent.parent_id))
                    parent = result.scalar_one_or_none()
                else:
                    break
            return False

        # Check if the new parent is actually a child of the current note
        result = await db.execute(select(Note).where(Note.parent_id == note_id))
        children = list(result.scalars().all())
        for child in children:
            if child.id == update_data["parent_id"] or await is_descendant(update_data["parent_id"], child.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot set a descendant as parent (would create cycle)",
                )

        # Validate that new parent exists and belongs to same application
        result = await db.execute(
            select(Note).where(
                Note.id == update_data["parent_id"],
                Note.application_id == note.application_id,
            )
        )
        parent_note = result.scalar_one_or_none()

        if not parent_note:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent note not found or does not belong to the same application",
            )

    # Apply updates
    for field, value in update_data.items():
        setattr(note, field, value)

    # Update timestamp
    note.updated_at = datetime.utcnow()

    # Save changes
    await db.commit()
    await db.refresh(note)

    return note


@router.put(
    "/api/notes/{note_id}/reorder",
    response_model=NoteResponse,
    summary="Reorder a note",
    description="Update a note's tab_order position.",
    responses={
        200: {"description": "Note reordered successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Note not found"},
    },
)
async def reorder_note(
    note_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    new_order: int = Query(..., ge=0, description="New tab order position"),
) -> NoteResponse:
    """
    Reorder a note by updating its tab_order.

    This endpoint handles shifting other notes' orders as needed.
    - **new_order**: The new position for the note (0-indexed)
    """
    # Verify access and get note
    note = await verify_note_access(note_id, current_user, db)

    old_order = note.tab_order

    if old_order == new_order:
        return note

    # Get sibling notes (same parent)
    result = await db.execute(
        select(Note)
        .where(
            Note.application_id == note.application_id,
            Note.parent_id == note.parent_id,
            Note.id != note_id,
        )
        .order_by(Note.tab_order.asc())
    )
    siblings = list(result.scalars().all())

    # Update orders
    if new_order < old_order:
        # Moving up - shift others down
        for sibling in siblings:
            if new_order <= sibling.tab_order < old_order:
                sibling.tab_order += 1
    else:
        # Moving down - shift others up
        for sibling in siblings:
            if old_order < sibling.tab_order <= new_order:
                sibling.tab_order -= 1

    # Set new order
    note.tab_order = new_order
    note.updated_at = datetime.utcnow()

    # Save changes
    await db.commit()
    await db.refresh(note)

    return note


@router.delete(
    "/api/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a note",
    description="Delete a note and optionally its children.",
    responses={
        204: {"description": "Note deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Note not found"},
    },
)
async def delete_note(
    note_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cascade: bool = Query(True, description="Delete all child notes recursively"),
) -> None:
    """
    Delete a note.

    - **cascade**: If true (default), delete all child notes recursively.
                   If false, orphan children (set their parent_id to null).

    This will also delete all attachments linked to the note.
    Only the application owner can delete their notes.
    This action is irreversible.
    """
    # Verify access and get note
    note = await verify_note_access(note_id, current_user, db)

    if cascade:
        # Recursively delete all children
        async def delete_children(parent_id: UUID):
            result = await db.execute(select(Note).where(Note.parent_id == parent_id))
            children = list(result.scalars().all())
            for child in children:
                await delete_children(child.id)
                await db.delete(child)

        await delete_children(note_id)
    else:
        # Orphan children (set parent_id to null)
        await db.execute(
            update(Note).where(Note.parent_id == note_id).values(parent_id=None)
        )

    # Delete the note (cascade will handle attachments)
    await db.delete(note)
    await db.commit()

    return None
