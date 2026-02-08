"""Applications CRUD API endpoints.

Provides endpoints for managing Applications, the top-level containers in the
Application > Project > Task hierarchy. All endpoints require authentication.
"""

from datetime import datetime, timedelta
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.task import Task
from ..models.task_status import StatusCategory, TaskStatus as TaskStatusModel
from ..models.user import User
from ..schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithProjects,
    OwnershipType,
)
from ..schemas.invitation import ApplicationRole
from ..schemas.project import ProjectCursorPage, ProjectResponse, ProjectWithTasks
from ..schemas.task import TaskCursorPage, TaskResponse, TaskStatusInfo, TaskUserInfo
from ..services.auth_service import get_current_user
from ..services.task_helpers import get_task_status_info
from ..websocket.handlers import handle_application_update, UpdateAction

router = APIRouter(prefix="/api/applications", tags=["Applications"])


# ============================================================================
# Helper Functions
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
    # If application is provided, use it; otherwise fetch
    if application is None:
        result = await db.execute(
            select(Application).where(Application.id == application_id)
        )
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
    role = await get_user_application_role(db, user_id, application_id)
    return role == "owner"


async def is_application_member(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is a member of the application (any role)."""
    role = await get_user_application_role(db, user_id, application_id)
    return role is not None


async def can_edit_application(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user can edit the application (owner or editor)."""
    role = await get_user_application_role(db, user_id, application_id)
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
    db: AsyncSession = Depends(get_db),
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
    member_app_ids_result = await db.execute(
        select(ApplicationMember.application_id)
        .where(ApplicationMember.user_id == current_user.id)
    )
    member_app_ids = [row[0] for row in member_app_ids_result.all()]

    # Build query based on ownership filter
    stmt = select(Application).options(lazyload(Application.owner))

    if ownership_filter == OwnershipType.CREATED:
        # Only apps created by the user
        stmt = stmt.where(Application.owner_id == current_user.id)
    elif ownership_filter == OwnershipType.INVITED:
        # Only apps user was invited to
        stmt = stmt.where(Application.id.in_(member_app_ids))
    else:
        # All accessible apps: owned OR member
        stmt = stmt.where(
            or_(
                Application.owner_id == current_user.id,
                Application.id.in_(member_app_ids),
            )
        )

    # Apply search filter if provided
    if search:
        stmt = stmt.where(Application.name.ilike(f"%{search}%"))

    # Order by most recently updated
    stmt = stmt.order_by(Application.updated_at.desc())

    # Apply pagination
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    applications_list = result.scalars().all()

    # Get project counts for each application
    app_ids = [app.id for app in applications_list]

    # Query project counts separately (exclude archived projects)
    counts_result = await db.execute(
        select(
            Project.application_id,
            func.count(Project.id).label("count"),
        )
        .where(
            Project.application_id.in_(app_ids),
            Project.archived_at.is_(None),  # Exclude archived projects
        )
        .group_by(Project.application_id)
    )
    counts_query = counts_result.all()

    # Create a map of application_id -> count
    counts_map = {str(app_id): count for app_id, count in counts_query}

    # Create a map of application_id -> member role (for invited apps)
    member_roles_map = {}
    if member_app_ids:
        member_roles_result = await db.execute(
            select(ApplicationMember.application_id, ApplicationMember.role)
            .where(
                ApplicationMember.application_id.in_(app_ids),
                ApplicationMember.user_id == current_user.id,
            )
        )
        member_roles_query = member_roles_result.all()
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
    db: AsyncSession = Depends(get_db),
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
    await db.flush()

    # Create ApplicationMember record for the owner
    # This ensures consistency with WebSocket room authorization which checks ApplicationMember table
    owner_member = ApplicationMember(
        application_id=application.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(owner_member)
    await db.commit()
    await db.refresh(application)

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
    db: AsyncSession = Depends(get_db),
) -> ApplicationWithProjects:
    """
    Get a specific application by its ID.

    Returns the application with its project count and ownership type.
    Any member (owner, editor, viewer) can access the application.
    """
    # Query application
    result = await db.execute(
        select(Application)
        .options(lazyload(Application.owner))
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user is owner or member (pass application to avoid re-fetching)
    user_role = await get_user_application_role(db, current_user.id, application_id, application)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Get project count separately
    count_result = await db.execute(
        select(func.count(Project.id))
        .where(Project.application_id == application_id)
    )
    projects_count = count_result.scalar() or 0

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
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    """
    Update an existing application.

    - **name**: New application name (optional, 1-255 characters)
    - **description**: New description (optional)

    Owners and editors can update the application.
    Viewers have read-only access.
    """
    # Get the application
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user can edit (owner or editor)
    if not await can_edit_application(db, current_user.id, application_id):
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
    await db.commit()
    await db.refresh(application)

    # Broadcast update to application room + the user who made the change
    await handle_application_update(
        application_id=application_id,
        action=UpdateAction.UPDATED,
        application_data={
            "id": str(application.id),
            "name": application.name,
            "description": application.description,
            "updated_at": application.updated_at.isoformat() if application.updated_at else None,
        },
        user_id=current_user.id,
        member_user_ids=[current_user.id],  # Only notify the user who made the change
    )

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
    db: AsyncSession = Depends(get_db),
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
    result = await db.execute(
        select(Application).where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Check if user is an owner (original owner or member with owner role)
    if not await is_application_owner(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners can delete this application.",
        )

    # Delete the application (cascade will handle related records)
    await db.delete(application)
    await db.commit()

    return None


# ============================================================================
# My Tasks endpoints
# ============================================================================

# Archive threshold: tasks in done status for 7+ days are considered archived
MY_TASKS_ARCHIVE_THRESHOLD_DAYS = 7


def get_user_info(user) -> Optional[TaskUserInfo]:
    """Convert a User model to TaskUserInfo schema for API responses."""
    if user is None:
        return None
    return TaskUserInfo(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
    )


@router.get(
    "/{application_id}/tasks/my",
    response_model=TaskCursorPage,
    summary="List my pending tasks across all projects",
    description="Get tasks assigned to the current user that are not completed.",
    responses={
        200: {"description": "Tasks retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_my_pending_tasks(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (task ID)"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term to filter by title or task key"),
) -> TaskCursorPage:
    """
    List tasks assigned to the current user across all projects in an application.

    Returns pending tasks (not in Done status) with cursor-based pagination.
    """
    # Verify application membership
    user_role = await get_user_application_role(db, current_user.id, application_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Get all project IDs in this application
    project_ids_result = await db.execute(
        select(Project.id).where(Project.application_id == application_id)
    )
    project_ids = [row[0] for row in project_ids_result.all()]

    if not project_ids:
        return TaskCursorPage(items=[], next_cursor=None)

    # Query tasks assigned to the user that are not done and not archived
    query = (
        select(Task)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.reporter),
            selectinload(Task.project),
            selectinload(Task.task_status),
        )
        .join(TaskStatusModel, Task.task_status_id == TaskStatusModel.id)
        .where(
            Task.project_id.in_(project_ids),
            Task.assignee_id == current_user.id,
            TaskStatusModel.category != StatusCategory.DONE.value,
            Task.archived_at.is_(None),
        )
        .order_by(Task.updated_at.desc(), Task.id.desc())
    )

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Task.title.ilike(search_term)) | (Task.task_key.ilike(search_term))
        )

    # Apply cursor if provided
    if cursor:
        try:
            cursor_uuid = UUID(cursor)
            cursor_result = await db.execute(
                select(Task.updated_at).where(Task.id == cursor_uuid)
            )
            cursor_task_updated_at = cursor_result.scalar_one_or_none()
            if cursor_task_updated_at:
                query = query.where(
                    (Task.updated_at < cursor_task_updated_at) |
                    ((Task.updated_at == cursor_task_updated_at) & (Task.id < cursor_uuid))
                )
        except ValueError:
            pass

    # Fetch one extra to determine if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    tasks = list(result.scalars().all())

    # Check if there are more results
    has_more = len(tasks) > limit
    if has_more:
        tasks = tasks[:limit]

    # Convert to response format
    task_responses = []
    for task in tasks:
        task_response = TaskResponse(
            id=task.id,
            project_id=task.project_id,
            task_key=task.task_key,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            story_points=task.story_points,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee=get_user_info(task.assignee),
            reporter_id=task.reporter_id,
            reporter=get_user_info(task.reporter),
            parent_id=task.parent_id,
            sprint_id=task.sprint_id,
            task_status_id=task.task_status_id,
            task_status=get_task_status_info(task),
            task_rank=task.task_rank,
            row_version=task.row_version,
            checklist_total=task.checklist_total,
            checklist_done=task.checklist_done,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            archived_at=task.archived_at,
        )
        task_responses.append(task_response)

    next_cursor = str(tasks[-1].id) if has_more and tasks else None

    return TaskCursorPage(
        items=task_responses,
        next_cursor=next_cursor,
    )


@router.get(
    "/{application_id}/tasks/my/completed",
    response_model=TaskCursorPage,
    summary="List my recently completed tasks",
    description="Get tasks assigned to the current user that were completed within the last 7 days.",
    responses={
        200: {"description": "Tasks retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_my_completed_tasks(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (task ID)"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term to filter by title or task key"),
) -> TaskCursorPage:
    """
    List recently completed tasks assigned to the current user.

    Returns tasks in Done status completed within the last 7 days (not yet archived).
    """
    # Verify application membership
    user_role = await get_user_application_role(db, current_user.id, application_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Get all project IDs in this application
    project_ids_result = await db.execute(
        select(Project.id).where(Project.application_id == application_id)
    )
    project_ids = [row[0] for row in project_ids_result.all()]

    if not project_ids:
        return TaskCursorPage(items=[], next_cursor=None)

    # Calculate threshold date (7 days ago)
    threshold_date = datetime.utcnow() - timedelta(days=MY_TASKS_ARCHIVE_THRESHOLD_DAYS)

    # Query tasks assigned to the user that are done and completed within threshold
    query = (
        select(Task)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.reporter),
            selectinload(Task.project),
            selectinload(Task.task_status),
        )
        .join(TaskStatusModel, Task.task_status_id == TaskStatusModel.id)
        .where(
            Task.project_id.in_(project_ids),
            Task.assignee_id == current_user.id,
            TaskStatusModel.category == StatusCategory.DONE.value,
            Task.completed_at.isnot(None),
            Task.completed_at > threshold_date,
            Task.archived_at.is_(None),  # Not yet archived
        )
        .order_by(Task.completed_at.desc(), Task.id.desc())
    )

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Task.title.ilike(search_term)) | (Task.task_key.ilike(search_term))
        )

    # Apply cursor if provided
    if cursor:
        try:
            cursor_uuid = UUID(cursor)
            cursor_result = await db.execute(
                select(Task.completed_at).where(Task.id == cursor_uuid)
            )
            cursor_task_completed_at = cursor_result.scalar_one_or_none()
            if cursor_task_completed_at:
                query = query.where(
                    (Task.completed_at < cursor_task_completed_at) |
                    ((Task.completed_at == cursor_task_completed_at) & (Task.id < cursor_uuid))
                )
        except ValueError:
            pass

    # Fetch one extra to determine if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    tasks = list(result.scalars().all())

    # Check if there are more results
    has_more = len(tasks) > limit
    if has_more:
        tasks = tasks[:limit]

    # Convert to response format
    task_responses = []
    for task in tasks:
        task_response = TaskResponse(
            id=task.id,
            project_id=task.project_id,
            task_key=task.task_key,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            story_points=task.story_points,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee=get_user_info(task.assignee),
            reporter_id=task.reporter_id,
            reporter=get_user_info(task.reporter),
            parent_id=task.parent_id,
            sprint_id=task.sprint_id,
            task_status_id=task.task_status_id,
            task_status=get_task_status_info(task),
            task_rank=task.task_rank,
            row_version=task.row_version,
            checklist_total=task.checklist_total,
            checklist_done=task.checklist_done,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            archived_at=task.archived_at,
        )
        task_responses.append(task_response)

    next_cursor = str(tasks[-1].id) if has_more and tasks else None

    return TaskCursorPage(
        items=task_responses,
        next_cursor=next_cursor,
    )


@router.get(
    "/{application_id}/tasks/my/archived",
    response_model=TaskCursorPage,
    summary="List my archived tasks",
    description="Get tasks assigned to the current user that have been archived (completed 7+ days ago).",
    responses={
        200: {"description": "Tasks retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_my_archived_tasks(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (task ID)"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term to filter by title or task key"),
) -> TaskCursorPage:
    """
    List archived tasks assigned to the current user.

    Returns tasks that have been in Done status for 7+ days and are archived.
    """
    # Verify application membership
    user_role = await get_user_application_role(db, current_user.id, application_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Get all project IDs in this application
    project_ids_result = await db.execute(
        select(Project.id).where(Project.application_id == application_id)
    )
    project_ids = [row[0] for row in project_ids_result.all()]

    if not project_ids:
        return TaskCursorPage(items=[], next_cursor=None)

    # Query archived tasks assigned to the user
    query = (
        select(Task)
        .options(
            selectinload(Task.assignee),
            selectinload(Task.reporter),
            selectinload(Task.project),
            selectinload(Task.task_status),
        )
        .where(
            Task.project_id.in_(project_ids),
            Task.assignee_id == current_user.id,
            Task.archived_at.isnot(None),  # Only archived tasks
        )
        .order_by(Task.archived_at.desc(), Task.id.desc())
    )

    # Apply search filter if provided
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Task.title.ilike(search_term)) | (Task.task_key.ilike(search_term))
        )

    # Apply cursor if provided
    if cursor:
        try:
            cursor_uuid = UUID(cursor)
            cursor_result = await db.execute(
                select(Task.archived_at).where(Task.id == cursor_uuid)
            )
            cursor_task_archived_at = cursor_result.scalar_one_or_none()
            if cursor_task_archived_at:
                query = query.where(
                    (Task.archived_at < cursor_task_archived_at) |
                    ((Task.archived_at == cursor_task_archived_at) & (Task.id < cursor_uuid))
                )
        except ValueError:
            pass

    # Fetch one extra to determine if there are more results
    query = query.limit(limit + 1)

    result = await db.execute(query)
    tasks = list(result.scalars().all())

    # Check if there are more results
    has_more = len(tasks) > limit
    if has_more:
        tasks = tasks[:limit]

    # Convert to response format
    task_responses = []
    for task in tasks:
        task_response = TaskResponse(
            id=task.id,
            project_id=task.project_id,
            task_key=task.task_key,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            story_points=task.story_points,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee=get_user_info(task.assignee),
            reporter_id=task.reporter_id,
            reporter=get_user_info(task.reporter),
            parent_id=task.parent_id,
            sprint_id=task.sprint_id,
            task_status_id=task.task_status_id,
            task_status=get_task_status_info(task),
            task_rank=task.task_rank,
            row_version=task.row_version,
            checklist_total=task.checklist_total,
            checklist_done=task.checklist_done,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            archived_at=task.archived_at,
        )
        task_responses.append(task_response)

    next_cursor = str(tasks[-1].id) if has_more and tasks else None

    return TaskCursorPage(
        items=task_responses,
        next_cursor=next_cursor,
    )


# ============================================================================
# My Projects Endpoint (Dashboard)
# ============================================================================


@router.get(
    "/{application_id}/projects/my",
    response_model=ProjectCursorPage,
    summary="List my projects across an application",
    description="Get active projects in an application, ordered by due date.",
    responses={
        200: {"description": "Projects retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_my_projects(
    application_id: UUID,
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
    List projects the current user has access to within an application.

    Returns active (non-archived) projects with sorting by due_date, name, or updated_at.
    Supports filtering by derived status.
    """
    from ..models.project_task_status_agg import ProjectTaskStatusAgg

    # Verify application membership
    user_role = await get_user_application_role(db, current_user.id, application_id)
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    # Build query: projects in this application that are not archived
    query = (
        select(Project)
        .where(
            Project.application_id == application_id,
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

    # Apply derived status filter
    if status_filter:
        from ..models.task_status import TaskStatus

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
                if sort_by == "due_date":
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

    # Fetch task counts and derived status names for these projects
    if projects:
        project_ids = [p.id for p in projects]
        count_result = await db.execute(
            select(Task.project_id, func.count(Task.id))
            .where(
                Task.project_id.in_(project_ids),
                Task.archived_at.is_(None),
            )
            .group_by(Task.project_id)
        )
        counts_map = {str(row[0]): row[1] for row in count_result.all()}

        # Resolve derived status names
        from ..models.task_status import TaskStatus as TS
        derived_ids = [p.derived_status_id for p in projects if p.derived_status_id]
        status_names_map: dict[str, str] = {}
        if derived_ids:
            status_result = await db.execute(
                select(TS.id, TS.name).where(TS.id.in_(derived_ids))
            )
            status_names_map = {str(row[0]): row[1] for row in status_result.all()}
    else:
        counts_map = {}
        status_names_map = {}

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
            )
        )

    next_cursor = str(projects[-1].id) if has_more and projects else None

    return ProjectCursorPage(
        items=project_responses,
        next_cursor=next_cursor,
    )
