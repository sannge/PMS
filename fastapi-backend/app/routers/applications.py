"""Applications CRUD API endpoints.

Provides endpoints for managing Applications, the top-level containers in the
Application > Project > Task hierarchy. All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.application import Application
from ..models.project import Project
from ..models.user import User
from ..schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithProjects,
)
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/api/applications", tags=["Applications"])


@router.get(
    "",
    response_model=List[ApplicationWithProjects],
    summary="List all applications",
    description="Get all applications accessible to the current user.",
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
) -> List[ApplicationWithProjects]:
    """
    List all applications for the current user.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **search**: Optional search term to filter by name

    Returns applications with their project counts.
    """
    # Build query for applications owned by the current user
    query = db.query(
        Application,
        func.count(Project.id).label("projects_count"),
    ).outerjoin(
        Project,
        Project.application_id == Application.id,
    ).filter(
        Application.owner_id == current_user.id,
    ).group_by(
        Application.id,
    )

    # Apply search filter if provided
    if search:
        query = query.filter(Application.name.ilike(f"%{search}%"))

    # Order by most recently updated
    query = query.order_by(Application.updated_at.desc())

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Convert to response format
    applications = []
    for app, projects_count in results:
        app_response = ApplicationWithProjects(
            id=app.id,
            name=app.name,
            description=app.description,
            owner_id=app.owner_id,
            created_at=app.created_at,
            updated_at=app.updated_at,
            projects_count=projects_count,
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

    return application


@router.get(
    "/{application_id}",
    response_model=ApplicationWithProjects,
    summary="Get an application by ID",
    description="Get details of a specific application.",
    responses={
        200: {"description": "Application retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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

    Returns the application with its project count.
    Only the owner can access their applications.
    """
    # Query application with project count
    result = db.query(
        Application,
        func.count(Project.id).label("projects_count"),
    ).outerjoin(
        Project,
        Project.application_id == Application.id,
    ).filter(
        Application.id == application_id,
    ).group_by(
        Application.id,
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    application, projects_count = result

    # Check ownership
    if application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this application.",
        )

    return ApplicationWithProjects(
        id=application.id,
        name=application.name,
        description=application.description,
        owner_id=application.owner_id,
        created_at=application.created_at,
        updated_at=application.updated_at,
        projects_count=projects_count,
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
        403: {"description": "Access denied - not the owner"},
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

    Only the owner can update their applications.
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

    # Check ownership
    if application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this application.",
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
        403: {"description": "Access denied - not the owner"},
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

    Only the owner can delete their applications.
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

    # Check ownership
    if application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this application.",
        )

    # Delete the application (cascade will handle related records)
    db.delete(application)
    db.commit()

    return None
