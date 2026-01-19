"""Project Members CRUD API endpoints.

Provides endpoints for managing project members within projects.
ProjectMembers act as a "gate" for Editors - Editors must be ProjectMembers
to create, edit, or move tasks within a project.

Access Control:
- List members: Any application member (owner, editor, viewer)
- Add/Remove members: Only application owners
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
from ..models.project_member import ProjectMember
from ..models.user import User
from ..schemas.project_member import (
    ProjectMemberBase,
    ProjectMemberResponse,
    ProjectMemberWithUser,
)
from ..services.auth_service import get_current_user
from ..services.permission_service import get_permission_service

router = APIRouter(tags=["Project Members"])


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
    require_owner: bool = False,
) -> Project:
    """
    Verify that the project exists and the user has appropriate access.

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session
        require_owner: If True, require application owner role

    Returns:
        Project: The verified project with application loaded

    Raises:
        HTTPException: If project not found or user doesn't have access
    """
    # Fetch project with application eagerly loaded
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

    # Get user's role in the parent application
    user_role = get_user_application_role(
        db, current_user.id, project.application_id, project.application
    )

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this project's application.",
        )

    if require_owner and user_role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only application owners can manage project members.",
        )

    return project


# ============================================================================
# List endpoints
# ============================================================================


@router.get(
    "/api/projects/{project_id}/members",
    response_model=List[ProjectMemberWithUser],
    summary="List project members",
    description="Get all members of a project.",
    responses={
        200: {"description": "List of project members retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an application member"},
        404: {"description": "Project not found"},
    },
)
async def list_project_members(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
) -> List[ProjectMemberWithUser]:
    """
    List members of a project.

    Any member of the parent application can view the project member list.
    Returns members with their user information.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)

    Returns members ordered by creation date (oldest first).
    """
    # Verify user has access to view the project (any application member)
    project = verify_project_access(project_id, current_user, db)

    # Fetch all project members with users eagerly loaded
    members_query = db.query(ProjectMember).options(
        joinedload(ProjectMember.user)
    ).filter(
        ProjectMember.project_id == project_id,
    ).order_by(
        ProjectMember.created_at.asc()
    )

    # Apply pagination
    members = members_query.offset(skip).limit(limit).all()

    # Convert to response model with user info
    result = []
    for member in members:
        member_response = ProjectMemberWithUser(
            id=member.id,
            project_id=member.project_id,
            user_id=member.user_id,
            added_by_user_id=member.added_by_user_id,
            created_at=member.created_at,
            user_email=member.user.email if member.user else None,
            user_display_name=member.user.display_name if member.user else None,
        )
        result.append(member_response)

    return result


@router.get(
    "/api/projects/{project_id}/members/count",
    response_model=dict,
    summary="Get project member count",
    description="Get total member count for a project.",
    responses={
        200: {"description": "Member count retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an application member"},
        404: {"description": "Project not found"},
    },
)
async def get_project_member_count(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Get member count for a project.

    Returns:
    - total: Total number of project members
    """
    # Verify user has access to view the project
    project = verify_project_access(project_id, current_user, db)

    total = db.query(func.count(ProjectMember.id)).filter(
        ProjectMember.project_id == project_id,
    ).scalar() or 0

    return {"total": total}


# ============================================================================
# Individual member endpoints
# ============================================================================


@router.get(
    "/api/projects/{project_id}/members/{user_id}",
    response_model=ProjectMemberWithUser,
    summary="Get a project member by user ID",
    description="Get details of a specific project member.",
    responses={
        200: {"description": "Project member retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an application member"},
        404: {"description": "Project or member not found"},
    },
)
async def get_project_member(
    project_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectMemberWithUser:
    """
    Get a specific project member by user ID.

    Any member of the parent application can view member details.
    """
    # Verify user has access to view the project
    project = verify_project_access(project_id, current_user, db)

    member = db.query(ProjectMember).options(
        joinedload(ProjectMember.user)
    ).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this project",
        )

    return ProjectMemberWithUser(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        added_by_user_id=member.added_by_user_id,
        created_at=member.created_at,
        user_email=member.user.email if member.user else None,
        user_display_name=member.user.display_name if member.user else None,
    )


# ============================================================================
# Add/Remove member endpoints (Owner-only)
# ============================================================================


@router.post(
    "/api/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a project member",
    description="Add a user as a project member. Only application owners can add members.",
    responses={
        201: {"description": "Project member added successfully"},
        400: {"description": "User is already a member or not an application member"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - only owners can add members"},
        404: {"description": "Project or user not found"},
    },
)
async def add_project_member(
    project_id: UUID,
    member_data: ProjectMemberBase,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectMemberResponse:
    """
    Add a user as a project member.

    Only application owners can add project members.
    The user being added must be a member of the parent application.

    This grants the user (if they are an Editor) permission to manage
    tasks within this project.
    """
    # Verify current user is an owner of the application
    project = verify_project_access(project_id, current_user, db, require_owner=True)

    # Verify the target user exists
    target_user = db.query(User).filter(User.id == member_data.user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {member_data.user_id} not found",
        )

    # Verify the target user is a member of the application
    target_role = get_user_application_role(
        db, member_data.user_id, project.application_id, project.application
    )
    if not target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be a member of the application before being added to a project.",
        )

    # Check if user is already a project member
    existing_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_data.user_id,
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this project.",
        )

    # Create the project member
    new_member = ProjectMember(
        project_id=project_id,
        user_id=member_data.user_id,
        added_by_user_id=current_user.id,
    )

    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    return ProjectMemberResponse(
        id=new_member.id,
        project_id=new_member.project_id,
        user_id=new_member.user_id,
        added_by_user_id=new_member.added_by_user_id,
        created_at=new_member.created_at,
    )


@router.delete(
    "/api/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a project member",
    description="Remove a user from project membership. Only application owners can remove members.",
    responses={
        204: {"description": "Project member removed successfully"},
        400: {"description": "Cannot remove the project owner"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - only owners can remove members"},
        404: {"description": "Project or member not found"},
    },
)
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Remove a user from project membership.

    Only application owners can remove project members.

    Note: If the user has tasks assigned in this project, those assignments
    are not automatically removed. Consider reassigning or unassigning tasks
    before removing a member.

    The project owner (project_owner_user_id) cannot be removed from membership.
    """
    # Verify current user is an owner of the application
    project = verify_project_access(project_id, current_user, db, require_owner=True)

    # Check if trying to remove the project owner
    if project.project_owner_user_id and project.project_owner_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project owner from project membership. "
                   "Transfer project ownership first.",
        )

    # Find the member record
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this project",
        )

    db.delete(member)
    db.commit()

    return None


# ============================================================================
# Utility endpoints
# ============================================================================


@router.get(
    "/api/projects/{project_id}/members/assignable",
    response_model=List[ProjectMemberWithUser],
    summary="List assignable users for a project",
    description="Get users who can be assigned to tasks in this project.",
    responses={
        200: {"description": "List of assignable users retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an application member"},
        404: {"description": "Project not found"},
    },
)
async def list_assignable_users(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> List[ProjectMemberWithUser]:
    """
    List users who can be assigned to tasks in this project.

    A user is assignable if they are:
    1. A project member, AND
    2. An Owner or Editor in the parent application (not a Viewer)

    Any member of the parent application can view assignable users.
    """
    # Verify user has access to view the project
    project = verify_project_access(project_id, current_user, db)

    # Get all project members
    members = db.query(ProjectMember).options(
        joinedload(ProjectMember.user)
    ).filter(
        ProjectMember.project_id == project_id,
    ).all()

    # Filter to only those with owner/editor role in the application
    assignable = []
    for member in members:
        role = get_user_application_role(
            db, member.user_id, project.application_id, project.application
        )
        if role in ("owner", "editor"):
            assignable.append(ProjectMemberWithUser(
                id=member.id,
                project_id=member.project_id,
                user_id=member.user_id,
                added_by_user_id=member.added_by_user_id,
                created_at=member.created_at,
                user_email=member.user.email if member.user else None,
                user_display_name=member.user.display_name if member.user else None,
            ))

    return assignable


@router.get(
    "/api/projects/{project_id}/members/check/{user_id}",
    response_model=dict,
    summary="Check if a user is a project member",
    description="Check if a specific user is a member of the project.",
    responses={
        200: {"description": "Membership check result"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an application member"},
        404: {"description": "Project not found"},
    },
)
async def check_project_membership(
    project_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Check if a user is a member of a project.

    Returns a boolean indicating membership status.
    Any member of the parent application can check membership.
    """
    # Verify user has access to view the project
    project = verify_project_access(project_id, current_user, db)

    is_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first() is not None

    return {"is_member": is_member, "user_id": str(user_id), "project_id": str(project_id)}
