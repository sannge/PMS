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
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.application import Application
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

router = APIRouter(tags=["Tasks"])


def verify_project_ownership(
    project_id: UUID,
    current_user: User,
    db: Session,
) -> Project:
    """
    Verify that the project exists and the user owns its parent application.

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


def verify_task_access(
    task_id: UUID,
    current_user: User,
    db: Session,
) -> Task:
    """
    Verify that the task exists and the user has access via project/application ownership.

    Args:
        task_id: The UUID of the task
        current_user: The authenticated user
        db: Database session

    Returns:
        Task: The verified task

    Raises:
        HTTPException: If task not found or user doesn't have access
    """
    task = db.query(Task).filter(
        Task.id == task_id,
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found",
        )

    # Verify ownership through project -> application chain
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task's parent project not found",
        )

    application = db.query(Application).filter(
        Application.id == project.application_id,
    ).first()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this task's application.",
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


# ============================================================================
# Project-nested endpoints (for listing and creating tasks)
# ============================================================================


@router.get(
    "/api/projects/{project_id}/tasks",
    response_model=List[TaskWithSubtasks],
    summary="List all tasks in a project",
    description="Get all tasks within a specific project.",
    responses={
        200: {"description": "List of tasks retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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
    """
    # Verify project ownership
    verify_project_ownership(project_id, current_user, db)

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
    description="Create a new task within a project.",
    responses={
        201: {"description": "Task created successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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
    """
    # Verify project ownership
    project = verify_project_ownership(project_id, current_user, db)

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
    description="Get details of a specific task.",
    responses={
        200: {"description": "Task retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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
    Only the application owner can access their tasks.
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

    # Verify ownership through project -> application chain
    project = db.query(Project).filter(
        Project.id == task.project_id,
    ).first()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task's parent project not found",
        )

    application = db.query(Application).filter(
        Application.id == project.application_id,
    ).first()

    if not application or application.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not the owner of this task's application.",
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
    description="Update an existing task's details.",
    responses={
        200: {"description": "Task updated successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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
    Only the application owner can update their tasks.
    """
    # Verify access and get task
    task = verify_task_access(task_id, current_user, db)

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
    description="Delete a task and all its associated subtasks and attachments.",
    responses={
        204: {"description": "Task deleted successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the owner"},
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
    """
    # Verify access and get task
    task = verify_task_access(task_id, current_user, db)

    # Delete subtasks first (to handle self-referential cascade)
    db.query(Task).filter(Task.parent_id == task_id).delete(synchronize_session=False)

    # Delete the task (cascade will handle attachments)
    db.delete(task)
    db.commit()

    return None
