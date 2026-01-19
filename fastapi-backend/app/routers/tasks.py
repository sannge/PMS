"""Tasks CRUD API endpoints.

Provides endpoints for managing Tasks within Projects.
Tasks are the lowest level of the hierarchy: Application > Project > Task.
All endpoints require authentication.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.task import Task
from ..models.user import User
from ..schemas.task import (
    TaskCreate,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskType,
    TaskUpdate,
    TaskWithSubtasks,
)
from ..services.auth_service import get_current_user
from ..services.permission_service import PermissionService, get_permission_service

router = APIRouter(tags=["Tasks"])


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


def verify_project_access(
    project_id: UUID,
    current_user: User,
    db: Session,
    require_edit: bool = False,
) -> Project:
    """
    Verify that the project exists and the user has access via application membership.

    For edit operations, enforces the ProjectMember gate for Editors:
    - Application Owners: Always have full access (no ProjectMember gate)
    - Application Editors: Must be ProjectMembers to edit tasks
    - Application Viewers: Read-only access only

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require owner or editor role with ProjectMember gate

    Returns:
        Project: The verified project

    Raises:
        HTTPException: If project not found or user doesn't have access
    """
    # Fetch project with application in single query using join
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

    if require_edit:
        # Use PermissionService to check edit permissions with ProjectMember gate
        permission_service = get_permission_service(db)
        can_manage = permission_service.check_can_manage_tasks(
            current_user, project_id, project.application_id
        )

        if not can_manage:
            # Provide appropriate error message based on role
            if user_role == "viewer":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Viewers cannot manage tasks.",
                )
            elif user_role == "editor":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Editors must be project members to manage tasks in this project.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. You do not have permission to manage tasks in this project.",
                )

    return project


def verify_task_access(
    task_id: UUID,
    current_user: User,
    db: Session,
    require_edit: bool = False,
) -> Task:
    """
    Verify that the task exists and the user has access via application membership.

    For edit operations, enforces the ProjectMember gate for Editors:
    - Application Owners: Always have full access (no ProjectMember gate)
    - Application Editors: Must be ProjectMembers to edit tasks
    - Application Viewers: Read-only access only

    Args:
        task_id: The UUID of the task
        current_user: The authenticated user
        db: Database session
        require_edit: If True, require owner or editor role with ProjectMember gate

    Returns:
        Task: The verified task

    Raises:
        HTTPException: If task not found or user doesn't have access
    """
    # Fetch task with project and application in single query using joins
    task = db.query(Task).options(
        joinedload(Task.project).joinedload(Project.application)
    ).filter(
        Task.id == task_id,
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )

    # Project is already loaded via joinedload
    project = task.project

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task's parent project not found",
        )

    # Application is already loaded via chained joinedload (pass it to avoid re-fetching)
    user_role = get_user_application_role(db, current_user.id, project.application_id, project.application)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this task's application.",
        )

    if require_edit:
        # Use PermissionService to check edit permissions with ProjectMember gate
        permission_service = get_permission_service(db)
        can_manage = permission_service.check_can_manage_tasks(
            current_user, project.id, project.application_id
        )

        if not can_manage:
            # Provide appropriate error message based on role
            if user_role == "viewer":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Viewers cannot manage tasks.",
                )
            elif user_role == "editor":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Editors must be project members to manage tasks in this project.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. You do not have permission to manage tasks in this project.",
                )

    return task


def generate_task_key(project: Project, db: Session) -> str:
    """
    Generate the next task key for a project.

    Task keys follow the format: PROJECT_KEY-NUMBER (e.g., "PROJ-123")

    Args:
        project: The parent project
        db: Database session

    Returns:
        str: The generated task key
    """
    # Count existing tasks in this project to determine next number
    task_count = db.query(func.count(Task.id)).filter(
        Task.project_id == project.id,
    ).scalar() or 0

    # Generate the next task key
    next_number = task_count + 1
    return f"{project.key}-{next_number}"


def validate_assignee_eligibility(
    assignee_id: UUID,
    project_id: UUID,
    application_id: UUID,
    db: Session,
) -> None:
    """
    Validate that a user can be assigned to a task in a project.

    Assignment eligibility rules:
    - Must be a ProjectMember of the project
    - Must have Owner or Editor role in the application
    - Viewers cannot be assigned to tasks

    Args:
        assignee_id: The UUID of the user to be assigned
        project_id: The UUID of the project
        application_id: The UUID of the parent application
        db: Database session

    Raises:
        HTTPException: If assignee does not exist or is not eligible
    """
    # Verify the assignee user exists
    from ..models.user import User as UserModel
    assignee_user = db.query(UserModel).filter(UserModel.id == assignee_id).first()
    if not assignee_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with ID {assignee_id} not found",
        )

    # Use PermissionService to check assignment eligibility
    permission_service = get_permission_service(db)
    can_be_assigned = permission_service.check_can_be_assigned(
        user_id=assignee_id,
        project_id=project_id,
        application_id=application_id,
    )

    if not can_be_assigned:
        # Get the user's application role for a more informative error message
        user_role = permission_service.get_user_application_role(
            user_id=assignee_id,
            application_id=application_id,
        )

        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign task to this user. User is not a member of the application.",
            )
        elif user_role == "viewer":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign task to this user. Viewers cannot be assigned to tasks.",
            )
        else:
            # User is owner/editor but not a ProjectMember
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign task to this user. User must be a project member to be assigned tasks.",
            )


# ============================================================================
# Project-nested endpoints (for listing and creating tasks)
# ============================================================================


@router.get(
    "/api/projects/{project_id}/tasks",
    response_model=List[TaskWithSubtasks],
    summary="List all tasks in a project",
    description="Get all tasks within a specific project. Any member can view tasks.",
    responses={
        200: {"description": "List of tasks retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Project not found"},
    },
)
async def list_tasks(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    search: Optional[str] = Query(None, description="Search term for task title"),
    task_type: Optional[TaskType] = Query(None, description="Filter by task type"),
    task_status: Optional[TaskStatus] = Query(None, alias="status", description="Filter by task status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    assignee_id: Optional[UUID] = Query(None, description="Filter by assignee"),
) -> List[TaskWithSubtasks]:
    """
    List all tasks within a project.

    - **project_id**: ID of the parent project
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-500)
    - **search**: Optional search term to filter by title
    - **task_type**: Optional filter by task type (story, bug, epic, subtask, task)
    - **status**: Optional filter by status (todo, in_progress, in_review, done, blocked)
    - **priority**: Optional filter by priority (lowest, low, medium, high, highest)
    - **assignee_id**: Optional filter by assigned user

    Returns tasks with their subtask counts.
    Any member (owner, editor, viewer) can list tasks.
    """
    # Verify project access (any member can view)
    verify_project_access(project_id, current_user, db)

    # Build query for tasks with subtask count
    # Use a subquery for counting subtasks
    subtask_count_subquery = db.query(
        Task.parent_id,
        func.count(Task.id).label("subtasks_count"),
    ).filter(
        Task.parent_id.isnot(None),
    ).group_by(
        Task.parent_id,
    ).subquery()

    query = db.query(
        Task,
        func.coalesce(subtask_count_subquery.c.subtasks_count, 0).label("subtasks_count"),
    ).outerjoin(
        subtask_count_subquery,
        Task.id == subtask_count_subquery.c.parent_id,
    ).filter(
        Task.project_id == project_id,
    )

    # Apply search filter if provided
    if search:
        query = query.filter(Task.title.ilike(f"%{search}%"))

    # Apply task type filter if provided
    if task_type:
        query = query.filter(Task.task_type == task_type.value)

    # Apply status filter if provided
    if task_status:
        query = query.filter(Task.status == task_status.value)

    # Apply priority filter if provided
    if priority:
        query = query.filter(Task.priority == priority.value)

    # Apply assignee filter if provided
    if assignee_id:
        query = query.filter(Task.assignee_id == assignee_id)

    # Order by most recently updated
    query = query.order_by(Task.updated_at.desc())

    # Apply pagination
    results = query.offset(skip).limit(limit).all()

    # Convert to response format
    tasks = []
    for task, subtasks_count in results:
        task_response = TaskWithSubtasks(
            id=task.id,
            project_id=task.project_id,
            task_key=task.task_key,
            title=task.title,
            description=task.description,
            task_type=task.task_type,
            status=task.status,
            priority=task.priority,
            story_points=task.story_points,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            reporter_id=task.reporter_id,
            parent_id=task.parent_id,
            sprint_id=task.sprint_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            subtasks_count=subtasks_count,
        )
        tasks.append(task_response)

    return tasks


@router.post(
    "/api/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Create a new task within a project. Only owners and editors can create tasks.",
    responses={
        201: {"description": "Task created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner or editor"},
        404: {"description": "Project not found"},
    },
)
async def create_task(
    project_id: UUID,
    task_data: TaskCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """
    Create a new task within a project.

    - **title**: Task title (required, 1-500 characters)
    - **description**: Detailed task description (optional)
    - **task_type**: Type of task (default: 'story')
    - **status**: Task status (default: 'todo')
    - **priority**: Task priority (default: 'medium')
    - **story_points**: Story point estimate (optional, 0-100)
    - **due_date**: Task due date (optional)
    - **assignee_id**: ID of assigned user (optional)
    - **parent_id**: ID of parent task for subtasks (optional)
    - **sprint_id**: ID of sprint (optional)

    The task will be created under the specified project.
    Reporter will be set to the current user if not provided.
    Only owners and editors can create tasks.
    """
    # Verify project access (require edit permission)
    project = verify_project_access(project_id, current_user, db, require_edit=True)

    # Validate that project_id in body matches URL (if provided)
    if task_data.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID in request body does not match URL parameter",
        )

    # Validate parent task if provided
    if task_data.parent_id:
        parent_task = db.query(Task).filter(
            Task.id == task_data.parent_id,
            Task.project_id == project_id,
        ).first()

        if not parent_task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent task not found or does not belong to this project",
            )

    # Validate assignee eligibility if provided
    if task_data.assignee_id:
        validate_assignee_eligibility(
            assignee_id=task_data.assignee_id,
            project_id=project_id,
            application_id=project.application_id,
            db=db,
        )

    # Generate task key
    task_key = generate_task_key(project, db)

    # Set reporter to current user if not provided
    reporter_id = task_data.reporter_id or current_user.id

    # Create new task instance
    task = Task(
        project_id=project_id,
        task_key=task_key,
        title=task_data.title,
        description=task_data.description,
        task_type=task_data.task_type.value if task_data.task_type else "story",
        status=task_data.status.value if task_data.status else "todo",
        priority=task_data.priority.value if task_data.priority else "medium",
        story_points=task_data.story_points,
        due_date=task_data.due_date,
        assignee_id=task_data.assignee_id,
        reporter_id=reporter_id,
        parent_id=task_data.parent_id,
        sprint_id=task_data.sprint_id,
    )

    # Save to database
    db.add(task)
    db.commit()
    db.refresh(task)

    return task


# ============================================================================
# Direct task endpoints (for getting, updating, and deleting individual tasks)
# ============================================================================


@router.get(
    "/api/tasks/{task_id}",
    response_model=TaskWithSubtasks,
    summary="Get a task by ID",
    description="Get details of a specific task. Any member can view tasks.",
    responses={
        200: {"description": "Task retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Task not found"},
    },
)
async def get_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TaskWithSubtasks:
    """
    Get a specific task by its ID.

    Returns the task with its subtask count.
    Any member (owner, editor, viewer) can view tasks.
    """
    # Query task with subtask count
    subtask_count_subquery = db.query(
        Task.parent_id,
        func.count(Task.id).label("subtasks_count"),
    ).filter(
        Task.parent_id.isnot(None),
    ).group_by(
        Task.parent_id,
    ).subquery()

    result = db.query(
        Task,
        func.coalesce(subtask_count_subquery.c.subtasks_count, 0).label("subtasks_count"),
    ).outerjoin(
        subtask_count_subquery,
        Task.id == subtask_count_subquery.c.parent_id,
    ).filter(
        Task.id == task_id,
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )

    task, subtasks_count = result

    # Verify access through project -> application membership chain
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task's parent project not found",
        )

    user_role = get_user_application_role(db, current_user.id, project.application_id)

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this task's application.",
        )

    return TaskWithSubtasks(
        id=task.id,
        project_id=task.project_id,
        task_key=task.task_key,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        story_points=task.story_points,
        due_date=task.due_date,
        assignee_id=task.assignee_id,
        reporter_id=task.reporter_id,
        parent_id=task.parent_id,
        sprint_id=task.sprint_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        subtasks_count=subtasks_count,
    )


@router.put(
    "/api/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
    description="Update an existing task's details. Only owners and editors can update tasks.",
    responses={
        200: {"description": "Task updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner or editor"},
        404: {"description": "Task not found"},
    },
)
async def update_task(
    task_id: UUID,
    task_data: TaskUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """
    Update an existing task.

    - **title**: New task title (optional, 1-500 characters)
    - **description**: New description (optional)
    - **task_type**: New task type (optional)
    - **status**: New status (optional)
    - **priority**: New priority (optional)
    - **story_points**: New story points (optional)
    - **due_date**: New due date (optional)
    - **assignee_id**: New assignee (optional)
    - **parent_id**: New parent task (optional)
    - **sprint_id**: New sprint (optional)

    Note: Task key cannot be changed after creation.
    Only owners and editors can update tasks.
    """
    # Verify access and get task (require edit permission)
    task = verify_task_access(task_id, current_user, db, require_edit=True)

    # Update fields if provided
    update_data = task_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update provided",
        )

    # Validate parent task if being updated
    if "parent_id" in update_data and update_data["parent_id"]:
        # Cannot set self as parent
        if update_data["parent_id"] == task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task cannot be its own parent",
            )

        parent_task = db.query(Task).filter(
            Task.id == update_data["parent_id"],
            Task.project_id == task.project_id,
        ).first()

        if not parent_task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent task not found or does not belong to the same project",
            )

    # Validate assignee eligibility if being updated
    if "assignee_id" in update_data and update_data["assignee_id"]:
        validate_assignee_eligibility(
            assignee_id=update_data["assignee_id"],
            project_id=task.project_id,
            application_id=task.project.application_id,
            db=db,
        )

    # Apply updates, converting enums to their values
    for field, value in update_data.items():
        if isinstance(value, (TaskType, TaskStatus, TaskPriority)):
            setattr(task, field, value.value)
        else:
            setattr(task, field, value)

    # Update timestamp
    task.updated_at = datetime.utcnow()

    # Save changes
    db.commit()
    db.refresh(task)

    return task


@router.delete(
    "/api/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Delete a task and all its associated subtasks and attachments. Only owners and editors can delete tasks.",
    responses={
        204: {"description": "Task deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner or editor"},
        404: {"description": "Task not found"},
    },
)
async def delete_task(
    task_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a task.

    This will cascade delete all associated:
    - Subtasks
    - Attachments linked to this task

    Only the application owner can delete their tasks.
    This action is irreversible.
    Only owners and editors can delete tasks.
    """
    # Verify access and get task (require edit permission)
    task = verify_task_access(task_id, current_user, db, require_edit=True)

    # Delete subtasks first (to handle self-referential cascade)
    db.query(Task).filter(Task.parent_id == task_id).delete(synchronize_session=False)

    # Delete the task (cascade will handle attachments)
    db.delete(task)
    db.commit()

    return None
