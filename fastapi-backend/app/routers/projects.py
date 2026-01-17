"""Projects CRUD API endpoints.

Provides endpoints for managing Projects within Applications.
Projects are nested under Applications in the Application > Project > Task hierarchy.
All endpoints require authentication.
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
from ..models.task import Task
from ..models.user import User
from ..schemas.project import (
    ProjectBase,
    ProjectResponse,
    ProjectUpdate,
    ProjectWithTasks,
)
from ..services.auth_service import get_current_user

router = APIRouter(tags=["Projects"])


def verify_application_ownership(
    application_id: UUID,
    current_user: User,
    db: Session,
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
        HTTPException: If application not found or user is not the owner
    """
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

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


def verify_project_access(
    project_id: UUID,
    current_user: User,
    db: Session,
) -> Project:
    """
    Verify that the project exists and the user has access to it via application ownership.

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session

    Returns:
        Project: The verified project

    Raises:
        HTTPException: If project not found or user doesn't have access
    """
    project = db.query(Project).filter(
        Project.id == project_id,
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Verify ownership through the parent application
    application = db.query(Application).filter(
        Application.id == project.application_id,
    ).first()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this project's application.",
        )

    return project


# ============================================================================
# Application-nested endpoints (for listing and creating projects)
# ============================================================================


@router.get(
    "/api/applications/{application_id}/projects",
    response_model=List[ProjectWithTasks],
    summary="List all projects in an application",
    description="Get all projects within a specific application.",
    responses={
        200: {"description": "List of projects retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Application not found"},
    },
)
async def list_projects(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term for project name"),
    project_type: Optional[str] = Query(None, description="Filter by project type"),
) -> List[ProjectWithTasks]:
    """
    List all projects within an application.

    - **application_id**: ID of the parent application
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **search**: Optional search term to filter by name
    - **project_type**: Optional filter by project type (scrum, kanban, etc.)

    Returns projects with their task counts.
    """
    # Verify application ownership
    verify_application_ownership(application_id, current_user, db)

    # Build query for projects with task count
    query = db.query(
        Project,
        func.count(Task.id).label("tasks_count"),
    ).outerjoin(
        Task,
        Task.project_id == Project.id,
    ).filter(
        Project.application_id == application_id,
    ).group_by(
        Project.id,
    )

    # Apply search filter if provided
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%"))

    # Apply project type filter if provided
    if project_type:
        query = query.filter(Project.project_type == project_type)

    # Order by most recently updated
    query = query.order_by(Project.updated_at.desc())

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Convert to response format
    projects = []
    for project, tasks_count in results:
        project_response = ProjectWithTasks(
            id=project.id,
            name=project.name,
            key=project.key,
            description=project.description,
            project_type=project.project_type,
            application_id=project.application_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            tasks_count=tasks_count,
        )
        projects.append(project_response)

    return projects


@router.post(
    "/api/applications/{application_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description="Create a new project within an application.",
    responses={
        201: {"description": "Project created successfully"},
        400: {"description": "Validation error or duplicate key"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Application not found"},
    },
)
async def create_project(
    application_id: UUID,
    project_data: ProjectBase,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Create a new project within an application.

    - **name**: Project name (required, 1-255 characters)
    - **key**: Project key (required, uppercase, e.g., 'PROJ')
    - **description**: Optional project description
    - **project_type**: Project type (default: 'kanban')

    The project will be created under the specified application.
    """
    # Verify application ownership
    verify_application_ownership(application_id, current_user, db)

    # Check for duplicate key within the application
    existing_project = db.query(Project).filter(
        Project.application_id == application_id,
        Project.key == project_data.key,
    ).first()

    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project with key '{project_data.key}' already exists in this application",
        )

    # Create new project instance
    project = Project(
        name=project_data.name,
        key=project_data.key,
        description=project_data.description,
        project_type=project_data.project_type,
        application_id=application_id,
    )

    # Save to database
    db.add(project)
    db.commit()
    db.refresh(project)

    return project


# ============================================================================
# Direct project endpoints (for getting, updating, and deleting individual projects)
# ============================================================================


@router.get(
    "/api/projects/{project_id}",
    response_model=ProjectWithTasks,
    summary="Get a project by ID",
    description="Get details of a specific project.",
    responses={
        200: {"description": "Project retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Project not found"},
    },
)
async def get_project(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectWithTasks:
    """
    Get a specific project by its ID.

    Returns the project with its task count.
    Only the application owner can access their projects.
    """
    # Query project with task count
    result = db.query(
        Project,
        func.count(Task.id).label("tasks_count"),
    ).outerjoin(
        Task,
        Task.project_id == Project.id,
    ).filter(
        Project.id == project_id,
    ).group_by(
        Project.id,
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    project, tasks_count = result

    # Verify ownership through application
    application = db.query(Application).filter(
        Application.id == project.application_id,
    ).first()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this project's application.",
        )

    return ProjectWithTasks(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        application_id=project.application_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        tasks_count=tasks_count,
    )


@router.put(
    "/api/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
    description="Update an existing project's details.",
    responses={
        200: {"description": "Project updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Project not found"},
    },
)
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Update an existing project.

    - **name**: New project name (optional, 1-255 characters)
    - **description**: New description (optional)
    - **project_type**: New project type (optional)

    Note: Project key cannot be changed after creation.
    Only the application owner can update their projects.
    """
    # Verify access and get project
    project = verify_project_access(project_id, current_user, db)

    # Update fields if provided
    update_data = project_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided",
        )

    for field, value in update_data.items():
        setattr(project, field, value)

    # Update timestamp
    project.updated_at = datetime.utcnow()

    # Save changes
    db.commit()
    db.refresh(project)

    return project


@router.delete(
    "/api/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    description="Delete a project and all its associated tasks.",
    responses={
        204: {"description": "Project deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
        404: {"description": "Project not found"},
    },
)
async def delete_project(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a project.

    This will cascade delete all associated:
    - Tasks
    - Attachments linked to those tasks

    Only the application owner can delete their projects.
    This action is irreversible.
    """
    # Verify access and get project
    project = verify_project_access(project_id, current_user, db)

    # Delete the project (cascade will handle related records)
    db.delete(project)
    db.commit()

    return None
