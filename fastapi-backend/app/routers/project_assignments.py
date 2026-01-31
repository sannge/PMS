"""Project Assignments API endpoints.

Provides endpoints for managing user assignments to projects.
Only owners and editors can be assigned to projects (not viewers).
Assignment/removal operations require owner or manager privileges.
All endpoints require authentication.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_assignment import ProjectAssignment
from ..models.user import User
from ..schemas.invitation import ApplicationRole
from ..schemas.project_assignment import (
    AssignmentCreate,
    AssignmentList,
    AssignmentResponse,
    AssignmentWithUser,
)
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/api/projects", tags=["Project Assignments"])


# ============================================================================
# Helper functions
# ============================================================================


async def get_project_with_access(
    project_id: UUID,
    current_user: User,
    db: AsyncSession,
) -> tuple[Project, ApplicationMember | None]:
    """
    Get a project and verify user has access via application membership.

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session

    Returns:
        Tuple of (Project, ApplicationMember or None if owner)

    Raises:
        HTTPException: If project not found or user doesn't have access
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found",
        )

    # Get the application
    result = await db.execute(select(Application).where(Application.id == project.application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    # Check if user is the owner
    if application.owner_id == current_user.id:
        return project, None

    # Check if user is a member
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application.id,
            ApplicationMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this application.",
        )

    return project, member


def verify_assignment_permission(
    project: Project,
    current_user: User,
    member: ApplicationMember | None,
    db: AsyncSession,
) -> None:
    """
    Verify the current user has permission to manage assignments.

    Only owners can assign users to projects.

    Args:
        project: The project being modified
        current_user: The authenticated user
        member: The user's membership (None if owner)
        db: Database session

    Raises:
        HTTPException: If user doesn't have assignment permission
    """
    # Owner always has permission
    if member is None:
        return

    # Check if user is an owner
    if member.role == ApplicationRole.OWNER.value:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied. Only owners can manage project assignments.",
    )


async def get_assignable_member(
    application_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> ApplicationMember:
    """
    Get a member that can be assigned to a project.

    Only owners and editors can be assigned (not viewers).

    Args:
        application_id: The application ID
        user_id: The user ID to check
        db: Database session

    Returns:
        ApplicationMember: The member record

    Raises:
        HTTPException: If user is not a member or is a viewer
    """
    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this application.",
        )

    if member.role == ApplicationRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Viewers cannot be assigned to projects. Only owners and editors can be assigned.",
        )

    return member


# ============================================================================
# List endpoints
# ============================================================================


@router.get(
    "/{project_id}/assignments",
    response_model=AssignmentList,
    summary="List project assignments",
    description="Get all user assignments for a project.",
    responses={
        200: {"description": "List of assignments retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Project not found"},
    },
)
async def list_assignments(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
) -> AssignmentList:
    """
    List all user assignments for a project.

    - **project_id**: ID of the project
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)

    Any member of the application can view assignments.
    Returns assignments ordered by creation date (newest first).
    """
    # Verify access
    project, _ = await get_project_with_access(project_id, current_user, db)

    # Get total count
    result = await db.execute(
        select(func.count(ProjectAssignment.id)).where(ProjectAssignment.project_id == project_id)
    )
    total = result.scalar() or 0

    # Query assignments with user details
    result = await db.execute(
        select(ProjectAssignment)
        .where(ProjectAssignment.project_id == project_id)
        .order_by(ProjectAssignment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    assignments = result.scalars().all()

    return AssignmentList(
        items=assignments,
        total=total,
        skip=skip,
        limit=limit,
    )


# ============================================================================
# Create endpoints
# ============================================================================


@router.post(
    "/{project_id}/assignments",
    response_model=AssignmentWithUser,
    status_code=status.HTTP_201_CREATED,
    summary="Assign user to project",
    description="Assign a user to a project. Only owners and managers can assign users.",
    responses={
        201: {"description": "User assigned successfully"},
        400: {"description": "User is not a member or is a viewer"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not owner or manager"},
        404: {"description": "Project not found"},
        409: {"description": "User is already assigned to this project"},
    },
)
async def create_assignment(
    project_id: UUID,
    assignment_data: AssignmentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> AssignmentWithUser:
    """
    Assign a user to a project.

    - **project_id**: ID of the project
    - **user_id**: ID of the user to assign

    Requirements:
    - Current user must be an owner or manager of the application
    - Target user must be an owner or editor (viewers cannot be assigned)
    - User cannot already be assigned to this project
    """
    # Verify access and permission
    project, member = await get_project_with_access(project_id, current_user, db)
    verify_assignment_permission(project, current_user, member, db)

    # Check if user is the owner (owners can always be assigned)
    result = await db.execute(select(Application).where(Application.id == project.application_id))
    application = result.scalar_one_or_none()

    is_owner = application.owner_id == assignment_data.user_id

    # If not owner, verify user is an assignable member
    if not is_owner:
        await get_assignable_member(project.application_id, assignment_data.user_id, db)

    # Check for existing assignment
    result = await db.execute(
        select(ProjectAssignment).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.user_id == assignment_data.user_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already assigned to this project.",
        )

    # Create assignment
    assignment = ProjectAssignment(
        project_id=project_id,
        user_id=assignment_data.user_id,
        assigned_by=current_user.id,
    )

    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return assignment


# ============================================================================
# Delete endpoints
# ============================================================================


@router.delete(
    "/{project_id}/assignments/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove user from project",
    description="Remove a user's assignment from a project. Only owners and managers can remove assignments.",
    responses={
        204: {"description": "Assignment removed successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not owner or manager"},
        404: {"description": "Project or assignment not found"},
    },
)
async def remove_assignment(
    project_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a user's assignment from a project.

    - **project_id**: ID of the project
    - **user_id**: ID of the user to remove

    Only owners and managers can remove assignments.
    This action is irreversible.
    """
    # Verify access and permission
    project, member = await get_project_with_access(project_id, current_user, db)
    verify_assignment_permission(project, current_user, member, db)

    # Find the assignment
    result = await db.execute(
        select(ProjectAssignment).where(
            ProjectAssignment.project_id == project_id,
            ProjectAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment for user {user_id} not found in this project.",
        )

    await db.delete(assignment)
    await db.commit()

    return None
