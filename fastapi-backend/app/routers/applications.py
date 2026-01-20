"""Applications CRUD API endpoints.

Provides endpoints for managing Applications, the top-level containers in the
Application > Project > Task hierarchy. All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, lazyload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.user import User
from ..schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithProjects,
    OwnershipType,
)
from ..schemas.invitation import ApplicationRole
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/api/applications", tags=["Applications"])


# ============================================================================
# Helper Functions
# ============================================================================


def get_user_application_role(
    db: Session,
    user_id: UUID,
    application_id: UUID,
    application: Optional[Application] = None,
) -> Optional[str]:
    """
    Get the user's role in an application.

    Args:
        db: Database session
        user_id: The user's ID
        application_id: The application's ID
        application: Optional pre-fetched application to avoid extra query

    Returns:
        The role string ('owner', 'editor', 'viewer') or None if not a member.
    """
    # If application is provided, use it; otherwise fetch
    if application is None:
        application = db.query(Application).filter(Application.id == application_id).first()

    if not application:
        return None

    # Check if user is the original owner
    if application.owner_id == user_id:
        return "owner"

    # Check ApplicationMembers table
    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

    return member.role if member else None


def is_application_owner(
    db: Session,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is the owner of the application."""
    return get_user_application_role(db, user_id, application_id) == "owner"


def is_application_member(
    db: Session,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is a member of the application (any role)."""
    return get_user_application_role(db, user_id, application_id) is not None


def can_edit_application(
    db: Session,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user can edit the application (owner or editor)."""
    role = get_user_application_role(db, user_id, application_id)
    return role in ["owner", "editor"]


# ============================================================================
# List endpoints
# ============================================================================


@router.get(
    "",
    response_model=List[ApplicationWithProjects],
    summary="List all applications",
    description="Get all applications accessible to the current user (owned and invited).",
    responses={
        200: {"description": "List of applications retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_applications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term for application name"),
    ownership_filter: Optional[OwnershipType] = Query(
        None,
        alias="ownership",
        description="Filter by ownership type (created/invited)",
    ),
) -> List[ApplicationWithProjects]:
    """
    List all applications for the current user.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **search**: Optional search term to filter by name
    - **ownership**: Optional filter by ownership type (created/invited)

    Returns applications with their project counts and ownership type.
    """
    # Get IDs of applications the user is a member of (through invitation)
    member_app_ids_query = (
        db.query(ApplicationMember.application_id)
        .filter(ApplicationMember.user_id == current_user.id)
    )
    member_app_ids = [row[0] for row in member_app_ids_query.all()]

    # Build query based on ownership filter
    query = (
        db.query(Application)
        .options(lazyload(Application.owner))
    )

    if ownership_filter == OwnershipType.CREATED:
        # Only apps created by the user
        query = query.filter(Application.owner_id == current_user.id)
    elif ownership_filter == OwnershipType.INVITED:
        # Only apps user was invited to
        query = query.filter(Application.id.in_(member_app_ids))
    else:
        # All accessible apps: owned OR member
        query = query.filter(
            or_(
                Application.owner_id == current_user.id,
                Application.id.in_(member_app_ids),
            )
        )

    # Apply search filter if provided
    if search:
        query = query.filter(Application.name.ilike(f"%{search}%"))

    # Order by most recently updated
    query = query.order_by(Application.updated_at.desc())

    # Apply pagination
    applications_list = query.offset(skip).limit(limit).all()

    # Get project counts for each application
    app_ids = [app.id for app in applications_list]

    # Query project counts separately
    counts_query = (
        db.query(
            Project.application_id,
            func.count(Project.id).label("count"),
        )
        .filter(Project.application_id.in_(app_ids))
        .group_by(Project.application_id)
        .all()
    )

    # Create a map of application_id -> count
    counts_map = {str(app_id): count for app_id, count in counts_query}

    # Create a map of application_id -> member role (for invited apps)
    member_roles_map = {}
    if member_app_ids:
        member_roles_query = (
            db.query(ApplicationMember.application_id, ApplicationMember.role)
            .filter(
                ApplicationMember.application_id.in_(app_ids),
                ApplicationMember.user_id == current_user.id,
            )
            .all()
        )
        member_roles_map = {str(app_id): role for app_id, role in member_roles_query}

    # Convert to response format
    applications = []
    for app in applications_list:
        # Determine ownership type and user role
        is_creator = app.owner_id == current_user.id
        ownership_type = OwnershipType.CREATED if is_creator else OwnershipType.INVITED

        # Get user role - creator is always owner, otherwise get from membership
        if is_creator:
            user_role = "owner"
        else:
            user_role = member_roles_map.get(str(app.id), "viewer")

        app_response = ApplicationWithProjects(
            id=app.id,
            name=app.name,
            description=app.description,
            owner_id=app.owner_id,
            created_at=app.created_at,
            updated_at=app.updated_at,
            projects_count=counts_map.get(str(app.id), 0),
            ownership_type=ownership_type,
            user_role=user_role,
        )
        applications.append(app_response)

    return applications


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new application",
    description="Create a new application container for organizing projects.",
    responses={
        201: {"description": "Application created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
    },
)
async def create_application(
    application_data: ApplicationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    """
    Create a new application.

    - **name**: Application name (required, 1-255 characters)
    - **description**: Optional description of the application

    The current user will be set as the owner.
    """
    # Create new application instance
    application = Application(
        name=application_data.name,
        description=application_data.description,
        owner_id=current_user.id,
    )

    # Save to database
    db.add(application)
    db.commit()
    db.refresh(application)

    # Create ApplicationMember record for the owner
    # This ensures consistency with WebSocket room authorization which checks ApplicationMember table
    owner_member = ApplicationMember(
        application_id=application.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(owner_member)
    db.commit()

    return application


@router.get(
    "/{application_id}",
    response_model=ApplicationWithProjects,
    summary="Get an application by ID",
    description="Get details of a specific application.",
    responses={
        200: {"description": "Application retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def get_application(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ApplicationWithProjects:
    """
    Get a specific application by its ID.

    Returns the application with its project count and ownership type.
    Any member (owner, editor, viewer) can access the application.
    """
    # Query application (SQL Server compatible - no GROUP BY with eager loading)
    application = (
        db.query(Application)
        .options(lazyload(Application.owner))
        .filter(Application.id == application_id)
        .first()
    )

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user is owner or member (pass application to avoid re-fetching)
    user_role = get_user_application_role(db, current_user.id, application_id, application)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Get project count separately
    projects_count = (
        db.query(func.count(Project.id))
        .filter(Project.application_id == application_id)
        .scalar()
    ) or 0

    # Determine ownership type
    is_creator = application.owner_id == current_user.id
    ownership_type = OwnershipType.CREATED if is_creator else OwnershipType.INVITED

    return ApplicationWithProjects(
        id=application.id,
        name=application.name,
        description=application.description,
        owner_id=application.owner_id,
        created_at=application.created_at,
        updated_at=application.updated_at,
        projects_count=projects_count,
        ownership_type=ownership_type,
        user_role=user_role,
    )


@router.put(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Update an application",
    description="Update an existing application's details.",
    responses={
        200: {"description": "Application updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner or editor"},
        404: {"description": "Application not found"},
    },
)
async def update_application(
    application_id: UUID,
    application_data: ApplicationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ApplicationResponse:
    """
    Update an existing application.

    - **name**: New application name (optional, 1-255 characters)
    - **description**: New description (optional)

    Owners and editors can update the application.
    Viewers have read-only access.
    """
    # Get the application
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user can edit (owner or editor)
    if not can_edit_application(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners and editors can update this application.",
        )

    # Update fields if provided
    update_data = application_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided",
        )

    for field, value in update_data.items():
        setattr(application, field, value)

    # Update timestamp
    application.updated_at = datetime.utcnow()

    # Save changes
    db.commit()
    db.refresh(application)

    return application


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an application",
    description="Delete an application and all its associated projects and tasks.",
    responses={
        204: {"description": "Application deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Application not found"},
    },
)
async def delete_application(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Delete an application.

    This will cascade delete all associated:
    - Projects
    - Tasks
    - Notes
    - Invitations
    - Members

    Only owners can delete the application.
    Editors and viewers cannot delete applications.
    This action is irreversible.
    """
    # Get the application
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user is an owner (original owner or member with owner role)
    if not is_application_owner(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners can delete this application.",
        )

    # Delete the application (cascade will handle related records)
    db.delete(application)
    db.commit()

    return None
