"""Projects CRUD API endpoints.

Provides endpoints for managing Projects within Applications.
Projects are nested under Applications in the Application > Project > Task hierarchy.
All endpoints require authentication.

Access Control:
- List/Get projects: Any member (owner, editor, viewer)
- Create/Update projects: Only owners and editors
- Delete projects: Application owners or project admins
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, lazyload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_member import ProjectMember
from ..models.task import Task
from ..models.user import User
from ..models.task_status import TaskStatus
from ..schemas.project import (
    ProjectBase,
    ProjectResponse,
    ProjectStatusOverride,
    ProjectStatusOverrideClear,
    ProjectUpdate,
    ProjectWithTasks,
)
from ..services.auth_service import get_current_user
from ..services.notification_service import NotificationService
from ..websocket.manager import MessageType, manager

router = APIRouter(tags=["Projects"])


# ============================================================================
# Helper Functions for Role-Based Access Control
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
    # If application is provided, use it; otherwise fetch with member in single query
    if application is None:
        # Single query to get application
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


def verify_application_access(
    application_id: UUID,
    current_user: User,
    db: Session,
    require_edit: bool = False,
    require_owner: bool = False,
) -> Application:
    """
    Verify that the application exists and the user has appropriate access.

    Args:
        application_id: The UUID of the application
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require owner or editor role (not viewer)
        require_owner: If True, require owner role only

    Returns:
        Application: The verified application

    Raises:
        HTTPException: If application not found or user doesn't have appropriate access
    """
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Get user's role in this application (pass application to avoid re-fetching)
    user_role = get_user_application_role(db, current_user.id, application_id, application)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    if require_owner and user_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners can perform this action.",
        )

    if require_edit and user_role not in ["owner", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners and editors can perform this action.",
        )

    return application


def verify_project_access(
    project_id: UUID,
    current_user: User,
    db: Session,
    require_edit: bool = False,
    require_owner: bool = False,
) -> Project:
    """
    Verify that the project exists and the user has access to it via application membership.

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require owner or editor role (not viewer)
        require_owner: If True, require owner role only

    Returns:
        Project: The verified project

    Raises:
        HTTPException: If project not found or user doesn't have access
    """
    # Fetch project with application in single query using join
    from sqlalchemy.orm import joinedload
    project = db.query(Project).options(
        joinedload(Project.application)
    ).filter(
        Project.id == project_id,
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Verify access through the parent application membership (pass application to avoid re-fetching)
    user_role = get_user_application_role(db, current_user.id, project.application_id, project.application)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this project's application.",
        )

    if require_owner and user_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners can perform this action.",
        )

    if require_edit and user_role not in ["owner", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners and editors can perform this action.",
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
        403: {"description": "Access denied - not a member"},
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
    Any member (owner, editor, viewer) can list projects.
    """
    # Verify user is a member of the application (any role)
    verify_application_access(application_id, current_user, db)

    # Build query for projects (SQL Server compatible - no GROUP BY with eager loading)
    query = (
        db.query(Project)
        .options(lazyload(Project.application))
        .filter(Project.application_id == application_id)
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
    projects_list = query.offset(skip).limit(limit).all()

    # Get task counts for each project
    project_ids = [p.id for p in projects_list]

    # Query task counts separately
    counts_query = (
        db.query(
            Task.project_id,
            func.count(Task.id).label("count"),
        )
        .filter(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
        .all()
    )

    # Create a map of project_id -> count
    counts_map = {str(proj_id): count for proj_id, count in counts_query}

    # Convert to response format
    projects = []
    for project in projects_list:
        project_response = ProjectWithTasks(
            id=project.id,
            name=project.name,
            key=project.key,
            description=project.description,
            project_type=project.project_type,
            application_id=project.application_id,
            created_by=project.created_by,
            derived_status_id=project.derived_status_id,
            override_status_id=project.override_status_id,
            override_reason=project.override_reason,
            override_by_user_id=project.override_by_user_id,
            override_expires_at=project.override_expires_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
            tasks_count=counts_map.get(str(project.id), 0),
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
        403: {"description": "Access denied - not an owner or editor"},
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
    Only owners and editors can create projects.
    """
    # Verify user has edit access (owner or editor)
    verify_application_access(application_id, current_user, db, require_edit=True)

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
        created_by=current_user.id,
    )

    # Save project to database
    db.add(project)
    db.flush()  # Get the project ID without committing

    # Auto-add creator as a project admin
    from ..models.project_member import ProjectMemberRole
    project_member = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectMemberRole.ADMIN.value,  # Creator is project admin
        added_by_user_id=current_user.id,  # Self-added as creator
    )
    db.add(project_member)

    # Commit both project and member
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
        403: {"description": "Access denied - not a member"},
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
    Any member (owner, editor, viewer) can access the project.
    """
    # Verify access (any member can view) and get project
    project = verify_project_access(project_id, current_user, db)

    # Get task count separately
    tasks_count = (
        db.query(func.count(Task.id))
        .filter(Task.project_id == project_id)
        .scalar()
    ) or 0

    return ProjectWithTasks(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        application_id=project.application_id,
        created_by=project.created_by,
        derived_status_id=project.derived_status_id,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
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
        403: {"description": "Access denied - not an owner or editor"},
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
    Only owners and editors can update projects.
    """
    # Verify edit access (owner or editor) and get project
    project = verify_project_access(project_id, current_user, db, require_edit=True)

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

    # Broadcast project update to project room for real-time updates
    room_id = f"project:{project_id}"
    await manager.broadcast_to_room(
        room_id,
        {
            "type": MessageType.PROJECT_UPDATED,
            "data": {
                "project_id": str(project_id),
                "name": project.name,
                "description": project.description,
                "project_type": project.project_type,
                "project_key": project.key,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "updated_by": str(current_user.id),
            },
        },
    )

    return project


@router.delete(
    "/api/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    description="Delete a project and all its associated tasks. Application owners or project admins can delete.",
    responses={
        204: {"description": "Project deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - must be application owner or project admin"},
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

    Permissions:
    - Application owners can delete any project
    - Project admins can delete the project they administer

    This action is irreversible.
    """
    # Get the project
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Get user's role in the application
    user_role = get_user_application_role(db, current_user.id, project.application_id)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this project's application.",
        )

    # Check if user is a project admin
    project_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    ).first()
    is_project_admin = project_member and project_member.role == "admin"

    # Application owners or project admins can delete projects
    if user_role != "owner" and not is_project_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only application owners or project admins can delete projects.",
        )

    # Capture info for WebSocket broadcast before deletion
    application_id = project.application_id
    project_name = project.name
    project_key = project.key

    # Get all project members' user IDs
    project_member_ids = [
        pm.user_id for pm in db.query(ProjectMember.user_id).filter(
            ProjectMember.project_id == project_id
        ).all()
    ]

    # Get all application owners' user IDs (they should also be notified)
    application_owner_ids = [
        am.user_id for am in db.query(ApplicationMember.user_id).filter(
            ApplicationMember.application_id == application_id,
            ApplicationMember.role == "owner",
        ).all()
    ]

    # Combine unique user IDs to notify (excluding the user who deleted)
    users_to_notify = (set(project_member_ids) | set(application_owner_ids)) - {current_user.id}

    # Delete the project (cascade will handle related records)
    db.delete(project)
    db.commit()

    # Send notifications and broadcast to all affected users (excluding deleter)
    for user_id in users_to_notify:
        # Create stored notification
        await NotificationService.notify_system(
            db=db,
            user_id=user_id,
            title="Project Deleted",
            message=f"Project '{project_name}' ({project_key}) was deleted by {current_user.display_name or current_user.email}.",
            entity_type=None,  # Project no longer exists
            entity_id=None,
        )

        # Broadcast WebSocket event
        await manager.broadcast_to_user(
            user_id,
            {
                "type": MessageType.PROJECT_DELETED,
                "data": {
                    "project_id": str(project_id),
                    "application_id": str(application_id),
                    "project_name": project_name,
                    "project_key": project_key,
                    "deleted_by": str(current_user.id),
                },
            },
        )

    return None


# ============================================================================
# Project Status Override endpoints (Owner-only)
# ============================================================================


@router.put(
    "/api/projects/{project_id}/override-status",
    response_model=ProjectResponse,
    summary="Override project status",
    description="Manually override the derived project status. Owner-only.",
    responses={
        200: {"description": "Project status override set successfully"},
        400: {"description": "Invalid status ID or validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Project not found"},
    },
)
async def override_project_status(
    project_id: UUID,
    override_data: ProjectStatusOverride,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Override the derived project status.

    This allows Application Owners to manually set a project's status,
    overriding the automatically derived status based on task distribution.

    - **override_status_id**: The TaskStatus ID to set (must belong to this project)
    - **override_reason**: Required explanation for the override
    - **override_expires_at**: Optional expiration timestamp for the override

    When an override is active, the project displays the override status
    instead of the derived status. When the override expires (if set),
    the project reverts to the derived status.

    Only Application Owners can set status overrides.
    """
    # Verify owner access and get project
    project = verify_project_access(project_id, current_user, db, require_owner=True)

    # Validate that the override_status_id belongs to this project
    task_status = db.query(TaskStatus).filter(
        TaskStatus.id == override_data.override_status_id,
        TaskStatus.project_id == project_id,
    ).first()

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TaskStatus with ID {override_data.override_status_id} not found or does not belong to this project",
        )

    # Set the override fields
    project.override_status_id = override_data.override_status_id
    project.override_reason = override_data.override_reason
    project.override_by_user_id = current_user.id
    project.override_expires_at = override_data.override_expires_at

    # Update timestamp and row version
    project.updated_at = datetime.utcnow()
    project.row_version += 1

    # Save changes
    db.commit()
    db.refresh(project)

    return project


@router.delete(
    "/api/projects/{project_id}/override-status",
    response_model=ProjectResponse,
    summary="Clear project status override",
    description="Clear the manual status override, reverting to derived status. Owner-only.",
    responses={
        200: {"description": "Project status override cleared successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Project not found"},
    },
)
async def clear_project_status_override(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Clear the project status override.

    This removes the manual status override, causing the project to
    display its automatically derived status based on task distribution.

    Only Application Owners can clear status overrides.
    """
    # Verify owner access and get project
    project = verify_project_access(project_id, current_user, db, require_owner=True)

    # Clear the override fields
    project.override_status_id = None
    project.override_reason = None
    project.override_by_user_id = None
    project.override_expires_at = None

    # Update timestamp and row version
    project.updated_at = datetime.utcnow()
    project.row_version += 1

    # Save changes
    db.commit()
    db.refresh(project)

    return project
