"""Projects CRUD API endpoints.

Provides endpoints for managing Projects within Applications.
Projects are nested under Applications in the Application > Project > Task hierarchy.
All endpoints require authentication.

Access Control:
- List/Get projects: Any member (owner, editor, viewer)
- Create/Update projects: Only owners and editors
- Delete projects: Application owners or project admins
"""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload

from ..database import get_db

# Module-level cache for auto-archive throttling (per-application)
# Key: application_id (str), Value: last_run timestamp
_auto_archive_last_run: Dict[str, datetime] = {}
_AUTO_ARCHIVE_THROTTLE_SECONDS = 60  # Only run auto-archive once per minute per app
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_member import ProjectMember
from ..models.task import Task
from ..models.user import User
from ..models.task_status import TaskStatus
from ..models.project_task_status_agg import ProjectTaskStatusAgg
from ..services.status_derivation_service import recalculate_aggregation_from_tasks
from ..schemas.project import (
    ProjectBase,
    ProjectCursorPage,
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


async def get_user_application_role(
    db: AsyncSession,
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
        result = await db.execute(select(Application).where(Application.id == application_id))
        application = result.scalar_one_or_none()

    if not application:
        return None

    # Check if user is the original owner
    if application.owner_id == user_id:
        return "owner"

    # Check ApplicationMembers table
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    return member.role if member else None


async def is_application_owner(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is the owner of the application."""
    return await get_user_application_role(db, user_id, application_id) == "owner"


async def is_application_member(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is a member of the application (any role)."""
    return await get_user_application_role(db, user_id, application_id) is not None


async def can_edit_application(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user can edit the application (owner or editor)."""
    role = await get_user_application_role(db, user_id, application_id)
    return role in ["owner", "editor"]


async def verify_application_access(
    application_id: UUID,
    current_user: User,
    db: AsyncSession,
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
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Get user's role in this application (pass application to avoid re-fetching)
    user_role = await get_user_application_role(db, current_user.id, application_id, application)

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


async def verify_project_access(
    project_id: UUID,
    current_user: User,
    db: AsyncSession,
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
    # Fetch project with application in single query using selectinload
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.application))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Verify access through the parent application membership (pass application to avoid re-fetching)
    user_role = await get_user_application_role(db, current_user.id, project.application_id, project.application)

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
    db: AsyncSession = Depends(get_db),
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
    await verify_application_access(application_id, current_user, db)

    # Build query for projects (SQL Server compatible - no GROUP BY with eager loading)
    # Exclude archived projects from the main list
    query = (
        select(Project)
        .options(lazyload(Project.application))
        .where(
            Project.application_id == application_id,
            Project.archived_at.is_(None),  # Exclude archived projects
        )
    )

    # Apply search filter if provided
    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))

    # Apply project type filter if provided
    if project_type:
        query = query.where(Project.project_type == project_type)

    # Order by most recently updated
    query = query.order_by(Project.updated_at.desc())

    # Apply pagination
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    projects_list = result.scalars().all()

    # Get task counts for each project
    project_ids = [p.id for p in projects_list]

    # Query task counts (include all tasks, both active and archived)
    if project_ids:
        counts_result = await db.execute(
            select(
                Task.project_id,
                func.count(Task.id).label("count"),
            )
            .where(
                Task.project_id.in_(project_ids),
            )
            .group_by(Task.project_id)
        )
        counts_query = counts_result.all()
        counts_map = {str(proj_id): count for proj_id, count in counts_query}
    else:
        counts_map = {}

    # Get status names for derived_status_id values
    derived_status_ids = [p.derived_status_id for p in projects_list if p.derived_status_id]
    status_names_map: dict[str, str] = {}
    if derived_status_ids:
        status_result = await db.execute(
            select(TaskStatus.id, TaskStatus.name).where(
                TaskStatus.id.in_(derived_status_ids)
            )
        )
        status_records = status_result.all()
        status_names_map = {str(s.id): s.name for s in status_records}

    # Convert to response format
    projects = []
    for project in projects_list:
        derived_status_name = None
        if project.derived_status_id:
            derived_status_name = status_names_map.get(str(project.derived_status_id))

        project_response = ProjectWithTasks(
            id=project.id,
            name=project.name,
            key=project.key,
            description=project.description,
            project_type=project.project_type,
            due_date=project.due_date,

            application_id=project.application_id,
            created_by=project.created_by,
            project_owner_user_id=project.project_owner_user_id,
            derived_status_id=project.derived_status_id,
            derived_status=derived_status_name,
            override_status_id=project.override_status_id,
            override_reason=project.override_reason,
            override_by_user_id=project.override_by_user_id,
            override_expires_at=project.override_expires_at,
            row_version=project.row_version,
            created_at=project.created_at,
            updated_at=project.updated_at,
            archived_at=project.archived_at,
            tasks_count=counts_map.get(str(project.id), 0),
        )
        projects.append(project_response)

    return projects


@router.post(
    "/api/applications/{application_id}/projects",
    response_model=ProjectWithTasks,
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
    db: AsyncSession = Depends(get_db),
) -> ProjectWithTasks:
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
    await verify_application_access(application_id, current_user, db, require_edit=True)

    # Check for duplicate key within the application
    result = await db.execute(
        select(Project).where(
            Project.application_id == application_id,
            Project.key == project_data.key,
        )
    )
    existing_project = result.scalar_one_or_none()

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
        due_date=project_data.due_date,
        application_id=application_id,
        created_by=current_user.id,
    )

    # Save project to database
    db.add(project)
    await db.flush()  # Get the project ID without committing

    # Create default TaskStatuses for the project
    default_statuses = TaskStatus.create_default_statuses(project.id)
    for task_status in default_statuses:
        db.add(task_status)
    await db.flush()

    # Set initial derived status to "Todo" (first status)
    todo_status = next((s for s in default_statuses if s.name == "Todo"), None)
    if todo_status:
        project.derived_status_id = todo_status.id

    # Auto-add creator as a project admin
    from ..models.project_member import ProjectMemberRole
    project_member = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectMemberRole.ADMIN.value,  # Creator is project admin
        added_by_user_id=current_user.id,  # Self-added as creator
    )
    db.add(project_member)

    # Commit project, statuses, and member
    await db.commit()
    await db.refresh(project)

    # Get the derived status name for the response (use in-memory todo_status)
    derived_status_name = todo_status.name if todo_status else None

    # Broadcast project creation to application room (fire-and-forget for performance)
    app_room_id = f"application:{application_id}"
    asyncio.create_task(
        manager.broadcast_to_room(
            app_room_id,
            {
                "type": MessageType.PROJECT_CREATED,
                "data": {
                    "project_id": str(project.id),
                    "application_id": str(application_id),
                    "name": project.name,
                    "key": project.key,
                    "description": project.description,
                    "project_type": project.project_type,
                    "created_by": str(current_user.id),
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )
    )

    return ProjectWithTasks(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        due_date=project.due_date,
        application_id=project.application_id,
        created_by=project.created_by,
        project_owner_user_id=project.project_owner_user_id,
        derived_status_id=project.derived_status_id,
        derived_status=derived_status_name,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
        row_version=project.row_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        tasks_count=0,  # New project has no tasks
    )


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
    db: AsyncSession = Depends(get_db),
) -> ProjectWithTasks:
    """
    Get a specific project by its ID.

    Returns the project with its task count.
    Any member (owner, editor, viewer) can access the project.

    Auto-recalculates the project's derived status if the aggregation
    is out of sync with actual task counts.
    """
    # Verify access (any member can view) and get project
    project = await verify_project_access(project_id, current_user, db)

    # Get total task count (all tasks including archived) for display
    result = await db.execute(
        select(func.count(Task.id))
        .where(
            Task.project_id == project_id,
        )
    )
    tasks_count = result.scalar() or 0

    # Get active task count (excluding archived) for aggregation sync check
    result = await db.execute(
        select(func.count(Task.id))
        .where(
            Task.project_id == project_id,
            Task.archived_at.is_(None),
        )
    )
    active_tasks_count = result.scalar() or 0

    # Check if aggregation exists and is in sync (compare against active tasks only)
    result = await db.execute(
        select(ProjectTaskStatusAgg).where(ProjectTaskStatusAgg.project_id == project_id)
    )
    agg = result.scalar_one_or_none()

    # Check if aggregation needs recalculation:
    # 1. No aggregation exists
    # 2. Total tasks doesn't match active task count
    # 3. Sum of individual counters doesn't equal total_tasks (distribution is stale)
    if agg is not None:
        counter_sum = (
            (agg.todo_tasks or 0) +
            (agg.active_tasks or 0) +
            (agg.review_tasks or 0) +
            (agg.issue_tasks or 0) +
            (agg.done_tasks or 0)
        )
    else:
        counter_sum = -1  # Force recalculation

    needs_recalculation = (
        agg is None or
        agg.total_tasks != active_tasks_count or
        counter_sum != (agg.total_tasks or 0)
    )

    derived_status_name: Optional[str] = None

    if needs_recalculation:
        # Recalculate the aggregation from actual tasks (include subtasks, exclude archived)
        # Use selectinload to ensure task_status relationship is loaded
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.task_status))
            .where(
                Task.project_id == project_id,
                Task.archived_at.is_(None),  # Exclude archived tasks
            )
        )
        tasks = result.scalars().all()

        if agg is None:
            agg = ProjectTaskStatusAgg(
                project_id=project_id,
                total_tasks=0,
                todo_tasks=0,
                active_tasks=0,
                review_tasks=0,
                issue_tasks=0,
                done_tasks=0,
            )
            db.add(agg)
            await db.flush()

        derived_status_name = recalculate_aggregation_from_tasks(agg, tasks)

        # Ensure TaskStatuses exist for this project (handles legacy projects)
        result = await db.execute(
            select(func.count(TaskStatus.id)).where(TaskStatus.project_id == project_id)
        )
        existing_statuses_count = result.scalar() or 0

        if existing_statuses_count == 0:
            # Create default TaskStatuses for legacy project
            default_statuses = TaskStatus.create_default_statuses(project_id)
            for task_status in default_statuses:
                db.add(task_status)
            await db.flush()

        # Update project's derived_status_id
        result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project_id,
                TaskStatus.name == derived_status_name,
            )
        )
        task_status = result.scalar_one_or_none()

        if task_status:
            project.derived_status_id = task_status.id
        else:
            project.derived_status_id = None

        await db.commit()
        await db.refresh(project)
    else:
        # Get status name from existing derived_status_id
        if project.derived_status_id:
            result = await db.execute(
                select(TaskStatus).where(TaskStatus.id == project.derived_status_id)
            )
            task_status = result.scalar_one_or_none()
            derived_status_name = task_status.name if task_status else None

    return ProjectWithTasks(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        due_date=project.due_date,
        application_id=project.application_id,
        created_by=project.created_by,
        project_owner_user_id=project.project_owner_user_id,
        derived_status_id=project.derived_status_id,
        derived_status=derived_status_name,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
        row_version=project.row_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        tasks_count=tasks_count,
    )


@router.get(
    "/api/projects/{project_id}/statuses",
    summary="List task statuses for a project",
    description="Get all task statuses defined for a project, ordered by rank.",
    responses={
        200: {"description": "Task statuses retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Project not found"},
    },
)
async def list_project_statuses(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """
    Get all task statuses for a project, ordered by rank.

    Any member (owner, editor, viewer) can access the project's statuses.
    """
    # Verify access (any member can view)
    await verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.rank)
    )
    statuses = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "project_id": str(s.project_id),
            "name": s.name,
            "category": s.category,
            "rank": s.rank,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in statuses
    ]


@router.put(
    "/api/projects/{project_id}",
    response_model=ProjectWithTasks,
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
    db: AsyncSession = Depends(get_db),
) -> ProjectWithTasks:
    """
    Update an existing project.

    - **name**: New project name (optional, 1-255 characters)
    - **description**: New description (optional)
    - **project_type**: New project type (optional)

    Note: Project key cannot be changed after creation.
    Only owners and editors can update projects.
    """
    # Verify edit access (owner or editor) and get project
    project = await verify_project_access(project_id, current_user, db, require_edit=True)

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
    await db.commit()
    await db.refresh(project)

    # Broadcast project update to both application and project rooms for real-time updates
    # Use same timestamp for deduplication (frontend filters duplicates by project_id + timestamp)
    broadcast_timestamp = datetime.utcnow().isoformat()
    project_update_data = {
        "type": MessageType.PROJECT_UPDATED,
        "data": {
            "project_id": str(project_id),
            "application_id": str(project.application_id),
            "name": project.name,
            "description": project.description,
            "project_type": project.project_type,
            "project_key": project.key,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "updated_by": str(current_user.id),
            "timestamp": broadcast_timestamp,
        },
    }

    # Broadcast to application room (for dashboard/project list viewers)
    app_room_id = f"application:{project.application_id}"
    await manager.broadcast_to_room(app_room_id, project_update_data)

    # Broadcast to project room (for project detail viewers)
    project_room_id = f"project:{project_id}"
    await manager.broadcast_to_room(project_room_id, project_update_data)

    # Get the derived status name for the response
    derived_status_name = None
    if project.derived_status_id:
        result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == project.derived_status_id)
        )
        task_status = result.scalar_one_or_none()
        derived_status_name = task_status.name if task_status else None

    # Get task count (all tasks including archived)
    result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
        )
    )
    tasks_count = result.scalar() or 0

    return ProjectWithTasks(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        due_date=project.due_date,
        application_id=project.application_id,
        created_by=project.created_by,
        project_owner_user_id=project.project_owner_user_id,
        derived_status_id=project.derived_status_id,
        derived_status=derived_status_name,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
        row_version=project.row_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        tasks_count=tasks_count,
    )


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
    db: AsyncSession = Depends(get_db),
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
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Get user's role in the application
    user_role = await get_user_application_role(db, current_user.id, project.application_id)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this project's application.",
        )

    # Check if user is a project admin
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    project_member = result.scalar_one_or_none()
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
    result = await db.execute(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    )
    project_member_ids = [row[0] for row in result.all()]

    # Get all application owners' user IDs (they should also be notified)
    result = await db.execute(
        select(ApplicationMember.user_id).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.role == "owner",
        )
    )
    application_owner_ids = [row[0] for row in result.all()]

    # Combine unique user IDs to notify (excluding the user who deleted)
    users_to_notify = (set(project_member_ids) | set(application_owner_ids)) - {current_user.id}

    # Break circular dependency: delete TaskStatuses first, then Project
    # (Project.derived_status_id references TaskStatus, TaskStatus.project_id cascades from Project)
    # ORM cascade can't resolve this, so we handle it manually:
    # 1. Null out Project's FK references to TaskStatus
    # 2. Delete TaskStatuses via raw SQL (bypasses ORM cascade confusion)
    # 3. Delete Project (remaining cascades like tasks, members still work)
    from sqlalchemy import delete as sql_delete
    from ..models.task_status import TaskStatus as TaskStatusModel

    project.derived_status_id = None
    project.override_status_id = None
    await db.flush()

    # Delete TaskStatuses via raw SQL to bypass ORM circular dependency
    await db.execute(
        sql_delete(TaskStatusModel).where(TaskStatusModel.project_id == project_id)
    )

    # Expire the project to clear cached task_statuses relationship
    # Otherwise ORM will try to cascade-delete already-deleted TaskStatuses
    db.expire(project, ["task_statuses", "derived_status", "override_status"])

    # Delete the project
    await db.delete(project)
    await db.commit()

    # Broadcast project deletion to application room for real-time updates
    # (for users viewing the dashboard/project list)
    # Use same timestamp for both room and user broadcasts for deduplication
    delete_timestamp = datetime.utcnow().isoformat()
    delete_broadcast_data = {
        "project_id": str(project_id),
        "application_id": str(application_id),
        "project_name": project_name,
        "project_key": project_key,
        "deleted_by": str(current_user.id),
        "timestamp": delete_timestamp,
    }
    app_room_id = f"application:{application_id}"
    await manager.broadcast_to_room(
        app_room_id,
        {
            "type": MessageType.PROJECT_DELETED,
            "data": delete_broadcast_data,
        },
    )

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

        # Broadcast WebSocket event (reuse same data for deduplication)
        await manager.broadcast_to_user(
            user_id,
            {
                "type": MessageType.PROJECT_DELETED,
                "data": delete_broadcast_data,
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
    db: AsyncSession = Depends(get_db),
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
    project = await verify_project_access(project_id, current_user, db, require_owner=True)

    # Validate that the override_status_id belongs to this project
    result = await db.execute(
        select(TaskStatus).where(
            TaskStatus.id == override_data.override_status_id,
            TaskStatus.project_id == project_id,
        )
    )
    task_status = result.scalar_one_or_none()

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
    await db.commit()
    await db.refresh(project)

    # Get the derived status name for the response
    derived_status_name = None
    if project.derived_status_id:
        result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == project.derived_status_id)
        )
        derived_task_status = result.scalar_one_or_none()
        derived_status_name = derived_task_status.name if derived_task_status else None

    return ProjectResponse(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        due_date=project.due_date,
        application_id=project.application_id,
        created_by=project.created_by,
        project_owner_user_id=project.project_owner_user_id,
        derived_status_id=project.derived_status_id,
        derived_status=derived_status_name,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
        row_version=project.row_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
    )


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
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """
    Clear the project status override.

    This removes the manual status override, causing the project to
    display its automatically derived status based on task distribution.

    Only Application Owners can clear status overrides.
    """
    # Verify owner access and get project
    project = await verify_project_access(project_id, current_user, db, require_owner=True)

    # Clear the override fields
    project.override_status_id = None
    project.override_reason = None
    project.override_by_user_id = None
    project.override_expires_at = None

    # Update timestamp and row version
    project.updated_at = datetime.utcnow()
    project.row_version += 1

    # Save changes
    await db.commit()
    await db.refresh(project)

    # Get the derived status name for the response
    derived_status_name = None
    if project.derived_status_id:
        result = await db.execute(
            select(TaskStatus).where(TaskStatus.id == project.derived_status_id)
        )
        task_status = result.scalar_one_or_none()
        derived_status_name = task_status.name if task_status else None

    return ProjectResponse(
        id=project.id,
        name=project.name,
        key=project.key,
        description=project.description,
        project_type=project.project_type,
        due_date=project.due_date,
        application_id=project.application_id,
        created_by=project.created_by,
        project_owner_user_id=project.project_owner_user_id,
        derived_status_id=project.derived_status_id,
        derived_status=derived_status_name,
        override_status_id=project.override_status_id,
        override_reason=project.override_reason,
        override_by_user_id=project.override_by_user_id,
        override_expires_at=project.override_expires_at,
        row_version=project.row_version,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
    )


# ============================================================================
# Archived Projects Endpoints
# ============================================================================


async def auto_archive_eligible_projects(
    db: AsyncSession,
    application_id: UUID,
) -> int:
    """
    Archive all eligible projects in an application.
    A project is archived if:
    1. It has at least one task
    2. ALL of its tasks are archived

    Uses throttling to avoid running on every request (once per minute per app).
    Returns the count of archived projects.
    """
    # Throttle: only run if not run recently for this application
    app_id_str = str(application_id)
    now = datetime.utcnow()
    last_run = _auto_archive_last_run.get(app_id_str)

    if last_run and (now - last_run).total_seconds() < _AUTO_ARCHIVE_THROTTLE_SECONDS:
        return 0  # Skip - ran too recently

    # Update last run timestamp
    _auto_archive_last_run[app_id_str] = now

    # Subquery: projects that have at least one task
    has_tasks = (
        select(Task.project_id)
        .where(Task.project_id == Project.id)
        .correlate(Project)
        .exists()
    )

    # Subquery: projects that have at least one non-archived task
    has_active_tasks = (
        select(Task.project_id)
        .where(
            Task.project_id == Project.id,
            Task.archived_at.is_(None),
        )
        .correlate(Project)
        .exists()
    )

    # Find projects where:
    # - Belongs to this application
    # - Not already archived
    # - Has at least one task
    # - Has NO non-archived tasks (all tasks are archived)
    query = (
        select(Project)
        .where(
            Project.application_id == application_id,
            Project.archived_at.is_(None),
            has_tasks,
            ~has_active_tasks,  # NOT has_active_tasks
        )
    )

    result = await db.execute(query)
    projects_to_archive = result.scalars().all()

    if not projects_to_archive:
        return 0

    for project in projects_to_archive:
        project.archived_at = now

    await db.flush()
    return len(projects_to_archive)


@router.get(
    "/api/applications/{application_id}/projects/archived",
    response_model=ProjectCursorPage,
    summary="List archived projects",
    description="Get archived projects with cursor-based pagination and search.",
    responses={
        200: {"description": "Archived projects retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_archived_projects(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cursor: Optional[str] = Query(None, description="Cursor for pagination"),
    limit: int = Query(30, ge=1, le=100, description="Number of items to return"),
    search: Optional[str] = Query(None, description="Search term for project name or key"),
) -> ProjectCursorPage:
    """
    List archived projects with cursor-based pagination.

    - **cursor**: Project ID for cursor-based pagination
    - **limit**: Number of items per page (1-100, default 30)
    - **search**: Optional search term (matches project name or key)

    Returns archived projects ordered by archived_at DESC, id DESC.
    """
    # Auto-archive eligible projects before listing
    await auto_archive_eligible_projects(db, application_id)
    await db.commit()

    # Verify user is a member of the application
    application = await verify_application_access(application_id, current_user, db)

    # Check if user can restore (owner or editor)
    user_role = await get_user_application_role(db, current_user.id, application_id, application)
    can_restore = user_role in ["owner", "editor"]

    # Build base query for archived projects
    base_conditions = [
        Project.application_id == application_id,
        Project.archived_at.isnot(None),  # Only archived projects
    ]

    # Add search filter if provided
    if search:
        search_pattern = f"%{search}%"
        base_conditions.append(
            or_(
                Project.name.ilike(search_pattern),
                Project.key.ilike(search_pattern),
            )
        )

    # Get total count
    count_query = select(func.count(Project.id)).where(*base_conditions)
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Build main query
    query = (
        select(Project)
        .options(lazyload(Project.application))
        .where(*base_conditions)
    )

    # Apply cursor pagination
    if cursor:
        try:
            from uuid import UUID as UUIDType
            cursor_uuid = UUIDType(cursor)

            # Get cursor project's archived_at
            cursor_result = await db.execute(
                select(Project.archived_at).where(Project.id == cursor_uuid)
            )
            cursor_archived_at = cursor_result.scalar_one_or_none()

            if cursor_archived_at:
                # Fetch projects archived before or at cursor time, excluding cursor
                query = query.where(
                    or_(
                        Project.archived_at < cursor_archived_at,
                        (Project.archived_at == cursor_archived_at) & (Project.id < cursor_uuid),
                    )
                )
        except (ValueError, TypeError):
            pass  # Invalid cursor, ignore

    # Order by archived_at DESC, id DESC (most recently archived first)
    query = query.order_by(Project.archived_at.desc(), Project.id.desc())

    # Fetch one extra to determine if more results exist
    query = query.limit(limit + 1)
    result = await db.execute(query)
    projects_list = result.scalars().all()

    # Determine next cursor
    has_more = len(projects_list) > limit
    if has_more:
        projects_list = projects_list[:limit]

    next_cursor = str(projects_list[-1].id) if has_more and projects_list else None

    # Get task counts for each project (include ALL tasks for archived projects)
    # Since archived projects have all tasks archived, we show total count
    project_ids = [p.id for p in projects_list]
    counts_map: dict[str, int] = {}

    if project_ids:
        counts_result = await db.execute(
            select(
                Task.project_id,
                func.count(Task.id).label("count"),
            )
            .where(Task.project_id.in_(project_ids))
            .group_by(Task.project_id)
        )
        counts_query = counts_result.all()
        counts_map = {str(proj_id): count for proj_id, count in counts_query}

    # Get status names for derived_status_id values
    derived_status_ids = [p.derived_status_id for p in projects_list if p.derived_status_id]
    status_names_map: dict[str, str] = {}
    if derived_status_ids:
        status_result = await db.execute(
            select(TaskStatus.id, TaskStatus.name).where(
                TaskStatus.id.in_(derived_status_ids)
            )
        )
        status_records = status_result.all()
        status_names_map = {str(s.id): s.name for s in status_records}

    # Build response items
    items = []
    for project in projects_list:
        derived_status_name = None
        if project.derived_status_id:
            derived_status_name = status_names_map.get(str(project.derived_status_id))

        items.append(
            ProjectWithTasks(
                id=project.id,
                name=project.name,
                key=project.key,
                description=project.description,
                project_type=project.project_type,
                due_date=project.due_date,
    
                application_id=project.application_id,
                created_by=project.created_by,
                project_owner_user_id=project.project_owner_user_id,
                derived_status_id=project.derived_status_id,
                derived_status=derived_status_name,
                override_status_id=project.override_status_id,
                override_reason=project.override_reason,
                override_by_user_id=project.override_by_user_id,
                override_expires_at=project.override_expires_at,
                row_version=project.row_version,
                created_at=project.created_at,
                updated_at=project.updated_at,
                archived_at=project.archived_at,
                tasks_count=counts_map.get(str(project.id), 0),
            )
        )

    return ProjectCursorPage(
        items=items,
        next_cursor=next_cursor,
        total=total,
        can_restore=can_restore,
    )


# ============================================================================
# Cross-Application Dashboard Endpoints
# ============================================================================


@router.get(
    "/api/me/projects",
    response_model=ProjectCursorPage,
    summary="List my projects across all applications",
    description="Get active projects across all applications the user belongs to.",
    responses={
        200: {"description": "Projects retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_my_projects_cross_app(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (project ID)"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term to filter by name or key"),
    sort_by: str = Query("due_date", description="Sort field: due_date, name, updated_at"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by derived status: Todo, In Progress, Issue, Done"),
) -> ProjectCursorPage:
    """
    List all active projects the current user has access to across all applications.

    The user has access to a project if they are:
    - The application owner (Application.created_by)
    - An application member (ApplicationMember)
    - A project member (ProjectMember)
    """
    # Find all application IDs the user has access to
    # 1. Applications owned by user
    owned_apps = select(Application.id.label("app_id")).where(
        Application.owner_id == current_user.id
    )
    # 2. Applications where user is a member
    member_apps = select(ApplicationMember.application_id.label("app_id")).where(
        ApplicationMember.user_id == current_user.id
    )
    # Combine: all app IDs (use label for reliable column reference after union)
    all_app_ids = owned_apps.union(member_apps).subquery()

    # Build query: active projects in any of user's applications
    query = (
        select(Project)
        .where(
            Project.application_id.in_(select(all_app_ids.c.app_id)),
            Project.archived_at.is_(None),
        )
    )

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Project.name.ilike(search_term),
                Project.key.ilike(search_term),
            )
        )

    # Apply derived status filter via Project.derived_status_id → TaskStatus
    if status_filter:
        query = query.join(
            TaskStatus,
            Project.derived_status_id == TaskStatus.id,
        ).where(
            TaskStatus.name == status_filter,
        )

    # Apply sorting
    if sort_by == "name":
        if sort_order == "desc":
            query = query.order_by(Project.name.desc(), Project.id.desc())
        else:
            query = query.order_by(Project.name.asc(), Project.id.asc())
    elif sort_by == "updated_at":
        if sort_order == "desc":
            query = query.order_by(Project.updated_at.desc(), Project.id.desc())
        else:
            query = query.order_by(Project.updated_at.asc(), Project.id.asc())
    else:
        # Default: sort by due_date
        if sort_order == "desc":
            query = query.order_by(Project.due_date.desc(), Project.id.desc())
        else:
            query = query.order_by(Project.due_date.asc(), Project.id.asc())

    # Apply cursor-based pagination
    if cursor:
        try:
            cursor_uuid = UUID(cursor)
            cursor_result = await db.execute(
                select(Project).where(Project.id == cursor_uuid)
            )
            cursor_project = cursor_result.scalar_one_or_none()
            if cursor_project:
                if sort_by == "due_date" or sort_by not in ("name", "updated_at"):
                    if sort_order == "desc":
                        query = query.where(
                            (Project.due_date < cursor_project.due_date) |
                            ((Project.due_date == cursor_project.due_date) & (Project.id < cursor_uuid))
                        )
                    else:
                        query = query.where(
                            (Project.due_date > cursor_project.due_date) |
                            ((Project.due_date == cursor_project.due_date) & (Project.id > cursor_uuid))
                        )
                elif sort_by == "updated_at":
                    if sort_order == "desc":
                        query = query.where(
                            (Project.updated_at < cursor_project.updated_at) |
                            ((Project.updated_at == cursor_project.updated_at) & (Project.id < cursor_uuid))
                        )
                    else:
                        query = query.where(
                            (Project.updated_at > cursor_project.updated_at) |
                            ((Project.updated_at == cursor_project.updated_at) & (Project.id > cursor_uuid))
                        )
                elif sort_by == "name":
                    if sort_order == "desc":
                        query = query.where(
                            (Project.name < cursor_project.name) |
                            ((Project.name == cursor_project.name) & (Project.id < cursor_uuid))
                        )
                    else:
                        query = query.where(
                            (Project.name > cursor_project.name) |
                            ((Project.name == cursor_project.name) & (Project.id > cursor_uuid))
                        )
        except ValueError:
            pass

    # Fetch one extra to determine if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    projects = list(result.scalars().all())

    # Check if there are more results
    has_more = len(projects) > limit
    if has_more:
        projects = projects[:limit]

    # Fetch task counts, derived status names, and application names for these projects
    if projects:
        project_ids = [p.id for p in projects]
        count_result = await db.execute(
            select(Task.project_id, func.count(Task.id))
            .where(
                Task.project_id.in_(project_ids),
            )
            .group_by(Task.project_id)
        )
        counts_map = {str(row[0]): row[1] for row in count_result.all()}

        # Resolve derived status names
        derived_ids = [p.derived_status_id for p in projects if p.derived_status_id]
        status_names_map: dict[str, str] = {}
        if derived_ids:
            status_result = await db.execute(
                select(TaskStatus.id, TaskStatus.name).where(TaskStatus.id.in_(derived_ids))
            )
            status_names_map = {str(row[0]): row[1] for row in status_result.all()}

        # Fetch application names
        app_ids = list({p.application_id for p in projects})
        app_result = await db.execute(
            select(Application.id, Application.name).where(Application.id.in_(app_ids))
        )
        app_names_map = {str(row[0]): row[1] for row in app_result.all()}
    else:
        counts_map = {}
        status_names_map = {}
        app_names_map = {}

    # Convert to response format
    project_responses = []
    for project in projects:
        derived_status_name = None
        if project.derived_status_id:
            derived_status_name = status_names_map.get(str(project.derived_status_id))

        project_responses.append(
            ProjectWithTasks(
                id=project.id,
                name=project.name,
                key=project.key,
                description=project.description,
                project_type=project.project_type,
                due_date=project.due_date,
                application_id=project.application_id,
                created_by=project.created_by,
                project_owner_user_id=project.project_owner_user_id,
                derived_status_id=project.derived_status_id,
                derived_status=derived_status_name,
                override_status_id=project.override_status_id,
                override_reason=project.override_reason,
                override_by_user_id=project.override_by_user_id,
                override_expires_at=project.override_expires_at,
                row_version=project.row_version,
                created_at=project.created_at,
                updated_at=project.updated_at,
                archived_at=project.archived_at,
                tasks_count=counts_map.get(str(project.id), 0),
                application_name=app_names_map.get(str(project.application_id)),
            )
        )

    next_cursor = str(projects[-1].id) if has_more and projects else None

    return ProjectCursorPage(
        items=project_responses,
        next_cursor=next_cursor,
    )

