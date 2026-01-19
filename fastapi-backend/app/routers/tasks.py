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
from ..models.project_task_status_agg import ProjectTaskStatusAgg
from ..models.task import Task
from ..models.task_status import StatusName
from ..models.user import User
from ..schemas.task import (
    TaskCreate,
    TaskMove,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskType,
    TaskUpdate,
    TaskWithSubtasks,
)
from ..services.auth_service import get_current_user
from ..services.permission_service import PermissionService, get_permission_service
from ..services.status_derivation_service import (
    update_aggregation_on_task_create,
    update_aggregation_on_task_delete,
    update_aggregation_on_task_status_change,
)

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
# Status Derivation Helper Functions
# ============================================================================


# Mapping from legacy status values (lowercase) to StatusName values (Title Case)
LEGACY_STATUS_TO_STATUS_NAME = {
    "todo": StatusName.TODO.value,
    "in_progress": StatusName.IN_PROGRESS.value,
    "in_review": StatusName.IN_REVIEW.value,
    "issue": StatusName.ISSUE.value,
    "blocked": StatusName.ISSUE.value,  # blocked -> issue migration
    "done": StatusName.DONE.value,
}


def get_status_name_from_legacy(legacy_status: str) -> str:
    """
    Convert a legacy task status value to the new StatusName value.

    Legacy statuses are lowercase: 'todo', 'in_progress', 'in_review', 'done', 'blocked'
    New StatusName values are Title Case: 'Todo', 'In Progress', 'In Review', 'Done', 'Issue'

    Args:
        legacy_status: The legacy status string (lowercase)

    Returns:
        The StatusName value string (Title Case)
    """
    return LEGACY_STATUS_TO_STATUS_NAME.get(legacy_status, StatusName.TODO.value)


def get_or_create_project_aggregation(
    db: Session,
    project_id: UUID,
) -> ProjectTaskStatusAgg:
    """
    Get or create the ProjectTaskStatusAgg for a project.

    If the aggregation record doesn't exist, creates one with all counters at zero.

    Args:
        db: Database session
        project_id: The UUID of the project

    Returns:
        ProjectTaskStatusAgg: The aggregation record
    """
    agg = db.query(ProjectTaskStatusAgg).filter(
        ProjectTaskStatusAgg.project_id == project_id
    ).first()

    if agg is None:
        # Create new aggregation with zero counts
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
        # Flush to ensure the record is created before we modify it
        db.flush()

    return agg


def update_project_derived_status(
    db: Session,
    project: Project,
    new_status_name: str,
) -> None:
    """
    Update a project's derived_status based on the newly derived status name.

    Finds the TaskStatus record matching the status name for this project
    and updates the project's derived_status_id.

    Args:
        db: Database session
        project: The Project to update
        new_status_name: The derived status name ('Todo', 'In Progress', 'Issue', 'Done')
    """
    from ..models.task_status import TaskStatus as TaskStatusModel

    # Find the TaskStatus record for this project with the derived status name
    # Note: derived status is a category, so we look for the first status matching
    # We map the derived status to a TaskStatus by category/name:
    # 'Todo' -> TaskStatus with name='Todo'
    # 'In Progress' -> TaskStatus with name='In Progress'
    # 'Issue' -> TaskStatus with name='Issue'
    # 'Done' -> TaskStatus with name='Done'
    task_status = db.query(TaskStatusModel).filter(
        TaskStatusModel.project_id == project.id,
        TaskStatusModel.name == new_status_name,
    ).first()

    if task_status:
        project.derived_status_id = task_status.id
    else:
        # If no matching TaskStatus found (shouldn't happen normally),
        # set derived_status_id to None
        project.derived_status_id = None


# ============================================================================
# Lexorank Helper Functions for Task Ordering
# ============================================================================


def calculate_lexorank_between(
    before_rank: Optional[str],
    after_rank: Optional[str],
) -> str:
    """
    Calculate a lexorank string that sorts between before_rank and after_rank.

    Lexorank uses a simple alphabetic midpoint calculation for ordering.
    This implementation uses lowercase letters 'a'-'z' for simplicity.

    Args:
        before_rank: The rank of the task that should come before (or None if first)
        after_rank: The rank of the task that should come after (or None if last)

    Returns:
        A new rank string that sorts between before_rank and after_rank

    Examples:
        calculate_lexorank_between(None, None) -> "n" (middle of alphabet)
        calculate_lexorank_between(None, "n") -> "g" (before n)
        calculate_lexorank_between("n", None) -> "t" (after n)
        calculate_lexorank_between("a", "c") -> "b" (between a and c)
    """
    # Default boundaries if not provided
    if before_rank is None:
        before_rank = ""
    if after_rank is None:
        after_rank = ""

    # If both empty, start in the middle
    if not before_rank and not after_rank:
        return "n"  # Middle of alphabet

    # If only after_rank exists, create rank before it
    if not before_rank:
        # Find a rank before after_rank
        if after_rank[0] > 'b':
            # Use character between 'a' and first char of after_rank
            mid_char = chr((ord('a') + ord(after_rank[0])) // 2)
            return mid_char if mid_char != 'a' else 'a' + 'n'
        else:
            # Need to extend with a character
            return 'a' + 'n'

    # If only before_rank exists, create rank after it
    if not after_rank:
        # Find a rank after before_rank
        if before_rank[-1] < 'y':
            # Use character after last char of before_rank
            return before_rank[:-1] + chr(ord(before_rank[-1]) + 1)
        else:
            # Extend the rank with middle character
            return before_rank + 'n'

    # Both ranks exist - find midpoint
    return _calculate_midpoint_rank(before_rank, after_rank)


def _calculate_midpoint_rank(before_rank: str, after_rank: str) -> str:
    """
    Calculate the midpoint rank between two existing ranks.

    Args:
        before_rank: The lower rank
        after_rank: The higher rank

    Returns:
        A rank string that sorts between before_rank and after_rank
    """
    # Ensure ranks are comparable by padding to same length
    max_len = max(len(before_rank), len(after_rank))
    before_padded = before_rank.ljust(max_len, 'a')
    after_padded = after_rank.ljust(max_len, 'z')

    result = []
    carry_needed = False

    for i in range(max_len):
        before_char = before_padded[i]
        after_char = after_padded[i]

        if before_char == after_char:
            result.append(before_char)
            continue

        # Calculate midpoint character
        mid_ord = (ord(before_char) + ord(after_char)) // 2

        if mid_ord > ord(before_char):
            result.append(chr(mid_ord))
            break
        else:
            # Characters are adjacent, need to extend
            result.append(before_char)
            carry_needed = True
            continue

    result_str = ''.join(result)

    # If we couldn't find a midpoint, extend with 'n'
    if carry_needed or result_str == before_rank:
        result_str = before_rank + 'n'

    return result_str


def get_rank_for_position(
    db: Session,
    project_id: UUID,
    target_status: str,
    before_task_id: Optional[UUID],
    after_task_id: Optional[UUID],
) -> str:
    """
    Calculate the rank for a task being moved to a specific position.

    Args:
        db: Database session
        project_id: The project ID
        target_status: The target status column
        before_task_id: ID of the task to position before (or None)
        after_task_id: ID of the task to position after (or None)

    Returns:
        The calculated rank string for the new position
    """
    before_rank: Optional[str] = None
    after_rank: Optional[str] = None

    # Get the rank of the task to position before
    if before_task_id:
        before_task = db.query(Task).filter(
            Task.id == before_task_id,
            Task.project_id == project_id,
        ).first()
        if before_task:
            before_rank = before_task.task_rank

    # Get the rank of the task to position after
    if after_task_id:
        after_task = db.query(Task).filter(
            Task.id == after_task_id,
            Task.project_id == project_id,
        ).first()
        if after_task:
            after_rank = after_task.task_rank

    # If neither provided, get the last task in the target status to append
    if not before_task_id and not after_task_id:
        last_task = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == target_status,
            Task.task_rank.isnot(None),
        ).order_by(Task.task_rank.desc()).first()

        if last_task and last_task.task_rank:
            before_rank = last_task.task_rank
            after_rank = None

    return calculate_lexorank_between(after_rank, before_rank)


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
    db.flush()  # Flush to get task ID before updating aggregation

    # Update status aggregation for project status derivation
    task_status_name = get_status_name_from_legacy(task.status)
    agg = get_or_create_project_aggregation(db, project_id)
    new_derived_status = update_aggregation_on_task_create(agg, task_status_name)

    # Update project's derived status
    update_project_derived_status(db, project, new_derived_status)

    # Commit all changes
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

    # Track old status for aggregation update
    old_status = task.status

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

    # Check if status changed and update aggregation
    new_status = task.status
    if old_status != new_status:
        old_status_name = get_status_name_from_legacy(old_status)
        new_status_name = get_status_name_from_legacy(new_status)

        # Get or create aggregation and update counters
        agg = get_or_create_project_aggregation(db, task.project_id)
        new_derived_status = update_aggregation_on_task_status_change(
            agg, old_status_name, new_status_name
        )

        # Update project's derived status
        # Need to fetch the project to update derived_status_id
        project = db.query(Project).filter(Project.id == task.project_id).first()
        if project:
            update_project_derived_status(db, project, new_derived_status)

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

    # Store task info for aggregation update before deletion
    project_id = task.project_id
    task_status = task.status

    # Get subtasks statuses before deletion (for aggregation update)
    subtasks = db.query(Task).filter(Task.parent_id == task_id).all()
    subtask_statuses = [subtask.status for subtask in subtasks]

    # Delete subtasks first (to handle self-referential cascade)
    db.query(Task).filter(Task.parent_id == task_id).delete(synchronize_session=False)

    # Delete the task (cascade will handle attachments)
    db.delete(task)

    # Update status aggregation for the deleted task and subtasks
    agg = get_or_create_project_aggregation(db, project_id)

    # Update aggregation for the main task
    task_status_name = get_status_name_from_legacy(task_status)
    new_derived_status = update_aggregation_on_task_delete(agg, task_status_name)

    # Update aggregation for each deleted subtask
    for subtask_status in subtask_statuses:
        subtask_status_name = get_status_name_from_legacy(subtask_status)
        new_derived_status = update_aggregation_on_task_delete(agg, subtask_status_name)

    # Update project's derived status
    project = db.query(Project).filter(Project.id == project_id).first()
    if project:
        update_project_derived_status(db, project, new_derived_status)

    db.commit()

    return None


@router.put(
    "/api/tasks/{task_id}/move",
    response_model=TaskResponse,
    summary="Move a task to a new status and/or position",
    description="Move a task between status columns and/or reorder within a column. "
                "Supports Kanban-style drag-and-drop operations. "
                "Only owners and editors can move tasks.",
    responses={
        200: {"description": "Task moved successfully"},
        400: {"description": "Validation error or invalid position"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner or editor"},
        404: {"description": "Task not found"},
        409: {"description": "Concurrent modification detected (row_version mismatch)"},
    },
)
async def move_task(
    task_id: UUID,
    move_data: TaskMove,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> TaskResponse:
    """
    Move a task to a new status column and/or reorder within a column.

    This endpoint supports Kanban-style drag-and-drop operations:
    - **Status change**: Use `target_status` or `target_status_id` to move between columns
    - **Reordering**: Use `target_rank` directly, or `before_task_id`/`after_task_id` for auto-calculation
    - **Both**: Change status and position in a single operation

    Rank calculation:
    - If `target_rank` is provided, it is used directly
    - If `before_task_id` and/or `after_task_id` are provided, rank is calculated automatically
    - If neither is provided, task is placed at the end of the target column

    Concurrency control:
    - Provide `row_version` to enable optimistic locking
    - If version mismatch, returns 409 Conflict

    Only owners and editors can move tasks.
    """
    # Verify access and get task (require edit permission)
    task = verify_task_access(task_id, current_user, db, require_edit=True)

    # Check for at least one field to update
    if (move_data.target_status is None and
        move_data.target_status_id is None and
        move_data.target_rank is None and
        move_data.before_task_id is None and
        move_data.after_task_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of target_status, target_status_id, target_rank, "
                   "before_task_id, or after_task_id must be provided",
        )

    # Optimistic concurrency check
    if move_data.row_version is not None:
        if task.row_version != move_data.row_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Concurrent modification detected. Expected version {move_data.row_version}, "
                       f"but current version is {task.row_version}. Please refresh and try again.",
            )

    # Track old status for aggregation update
    old_status = task.status
    new_status = old_status  # Default to same status

    # Handle status change
    if move_data.target_status is not None:
        new_status = move_data.target_status.value
        task.status = new_status

    # Handle task_status_id change (for new unified status system)
    if move_data.target_status_id is not None:
        from ..models.task_status import TaskStatus as TaskStatusModel

        # Verify the target status exists and belongs to this project
        target_task_status = db.query(TaskStatusModel).filter(
            TaskStatusModel.id == move_data.target_status_id,
            TaskStatusModel.project_id == task.project_id,
        ).first()

        if not target_task_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target task status not found or does not belong to this project",
            )

        task.task_status_id = move_data.target_status_id

        # Also update the legacy status field to match the new status name
        # Map status name to legacy status value
        status_name_to_legacy = {
            "Todo": "todo",
            "In Progress": "in_progress",
            "In Review": "in_review",
            "Issue": "issue",
            "Done": "done",
        }
        legacy_status = status_name_to_legacy.get(target_task_status.name, "todo")
        new_status = legacy_status
        task.status = new_status

    # Validate before_task_id and after_task_id belong to the same project
    if move_data.before_task_id:
        before_task = db.query(Task).filter(
            Task.id == move_data.before_task_id,
            Task.project_id == task.project_id,
        ).first()
        if not before_task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="before_task_id not found or does not belong to the same project",
            )

    if move_data.after_task_id:
        after_task = db.query(Task).filter(
            Task.id == move_data.after_task_id,
            Task.project_id == task.project_id,
        ).first()
        if not after_task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="after_task_id not found or does not belong to the same project",
            )

    # Calculate and set the new rank
    if move_data.target_rank is not None:
        # Use the explicitly provided rank
        task.task_rank = move_data.target_rank
    elif move_data.before_task_id is not None or move_data.after_task_id is not None:
        # Auto-calculate rank based on neighboring tasks
        task.task_rank = get_rank_for_position(
            db=db,
            project_id=task.project_id,
            target_status=new_status,
            before_task_id=move_data.before_task_id,
            after_task_id=move_data.after_task_id,
        )
    else:
        # Status change only, no position specified - append to end of column
        task.task_rank = get_rank_for_position(
            db=db,
            project_id=task.project_id,
            target_status=new_status,
            before_task_id=None,
            after_task_id=None,
        )

    # Update timestamp and version
    task.updated_at = datetime.utcnow()
    task.row_version = (task.row_version or 0) + 1

    # Check if status changed and update aggregation
    if old_status != new_status:
        old_status_name = get_status_name_from_legacy(old_status)
        new_status_name = get_status_name_from_legacy(new_status)

        # Get or create aggregation and update counters
        agg = get_or_create_project_aggregation(db, task.project_id)
        new_derived_status = update_aggregation_on_task_status_change(
            agg, old_status_name, new_status_name
        )

        # Update project's derived status
        project = db.query(Project).filter(Project.id == task.project_id).first()
        if project:
            update_project_derived_status(db, project, new_derived_status)

    # Save changes
    db.commit()
    db.refresh(task)

    return task
