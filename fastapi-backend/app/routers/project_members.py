"""Project Members CRUD API endpoints.

Provides endpoints for managing project members within projects.
ProjectMembers act as a "gate" for Editors - Editors must be ProjectMembers
to create, edit, or move tasks within a project.

Access Control:
- List members: Any application member (owner, editor, viewer)
- Add/Remove members: Application owners OR Project admins
- Change roles: Application owners OR Project admins

Project Member Roles:
- Admin: Can manage project members + edit/move tasks
- Member: Can edit/move tasks only
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
from ..models.project_member import ProjectMember, ProjectMemberRole
from ..models.task import Task
from ..models.user import User
from ..schemas.project_member import (
    ProjectMemberBase,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectMemberWithUser,
    ProjectMemberRole as ProjectMemberRoleSchema,
    UserSummary,
)
from ..schemas.notification import NotificationType, EntityType, NotificationCreate
from ..services.auth_service import get_current_user
from ..services.permission_service import get_permission_service
from ..services.notification_service import NotificationService
from ..services.user_cache_service import invalidate_project_role
from ..websocket.manager import MessageType, manager

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
    require_member_management: bool = False,
) -> Project:
    """
    Verify that the project exists and the user has appropriate access.

    Args:
        project_id: The UUID of the project
        current_user: The authenticated user
        db: Database session
        require_member_management: If True, require permission to manage members
                                   (app owner OR project admin)

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

    if require_member_management:
        # Check if user can manage members (app owner OR project admin)
        permission_service = get_permission_service(db)
        can_manage = permission_service.check_can_manage_project_members(
            current_user, project_id, project.application_id
        )
        if not can_manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Only application owners or project admins can manage project members.",
            )

    return project


def get_project_member_role(db: Session, user_id: UUID, project_id: UUID) -> Optional[str]:
    """Get the user's role within a project."""
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    return member.role if member else None


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
        user_summary = None
        if member.user:
            user_summary = UserSummary(
                id=member.user.id,
                email=member.user.email,
                display_name=member.user.display_name,
                avatar_url=member.user.avatar_url,
            )
        member_response = ProjectMemberWithUser(
            id=member.id,
            project_id=member.project_id,
            user_id=member.user_id,
            role=member.role,
            added_by_user_id=member.added_by_user_id,
            created_at=member.created_at,
            updated_at=member.updated_at,
            user=user_summary,
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

    user_summary = None
    if member.user:
        user_summary = UserSummary(
            id=member.user.id,
            email=member.user.email,
            display_name=member.user.display_name,
            avatar_url=member.user.avatar_url,
        )

    return ProjectMemberWithUser(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        added_by_user_id=member.added_by_user_id,
        created_at=member.created_at,
        updated_at=member.updated_at,
        user=user_summary,
    )


# ============================================================================
# Add/Remove/Update member endpoints (Owner or Project Admin)
# ============================================================================


class AddProjectMemberRequest(ProjectMemberBase):
    """Request schema for adding a project member with optional role."""

    role: ProjectMemberRoleSchema = ProjectMemberRoleSchema.MEMBER


@router.post(
    "/api/projects/{project_id}/members",
    response_model=ProjectMemberWithUser,
    status_code=status.HTTP_201_CREATED,
    summary="Add a project member",
    description="Add a user as a project member. Application owners or project admins can add members.",
    responses={
        201: {"description": "Project member added successfully"},
        400: {"description": "User is already a member, not an owner/editor, or is a viewer"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - only owners or project admins can add members"},
        404: {"description": "Project or user not found"},
    },
)
async def add_project_member(
    project_id: UUID,
    member_data: AddProjectMemberRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectMemberWithUser:
    """
    Add a user as a project member.

    Application owners or project admins can add project members.
    The user being added must be an owner or editor of the parent application
    (viewers cannot be added as project members since they already have read-only access).

    This grants the user (if they are an Editor) permission to manage
    tasks within this project.
    """
    # Verify current user can manage members (app owner OR project admin)
    project = verify_project_access(project_id, current_user, db, require_member_management=True)

    # Verify the target user exists
    target_user = db.query(User).filter(User.id == member_data.user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {member_data.user_id} not found",
        )

    # Verify the target user is an owner or editor of the application (not viewer)
    target_role = get_user_application_role(
        db, member_data.user_id, project.application_id, project.application
    )
    if not target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be a member of the application before being added to a project.",
        )
    if target_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application viewers cannot be added as project members. "
                   "Viewers already have read-only access to all projects.",
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

    # Create the project member with the specified role
    new_member = ProjectMember(
        project_id=project_id,
        user_id=member_data.user_id,
        role=member_data.role.value,
        added_by_user_id=current_user.id,
    )

    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    # Create notification for the added user
    notification_data = NotificationCreate(
        user_id=member_data.user_id,
        type=NotificationType.PROJECT_MEMBER_ADDED,
        title=f"Added to {project.name}",
        message=f"You were added to {project.name} as {member_data.role.value}",
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
    )
    await NotificationService.create_notification(db, notification_data)

    # Broadcast member added to project room for real-time updates
    room_id = f"project:{project_id}"
    await manager.broadcast_to_room(
        room_id,
        {
            "type": MessageType.PROJECT_MEMBER_ADDED,
            "data": {
                "project_id": str(project_id),
                "member_id": str(new_member.id),
                "user_id": str(new_member.user_id),
                "role": new_member.role,
                "user": {
                    "id": str(target_user.id),
                    "email": target_user.email,
                    "display_name": target_user.display_name,
                    "avatar_url": target_user.avatar_url,
                },
                "added_by": str(current_user.id),
            },
        },
    )

    # Return with user info
    user_summary = UserSummary(
        id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        avatar_url=target_user.avatar_url,
    )

    return ProjectMemberWithUser(
        id=new_member.id,
        project_id=new_member.project_id,
        user_id=new_member.user_id,
        role=new_member.role,
        added_by_user_id=new_member.added_by_user_id,
        created_at=new_member.created_at,
        updated_at=new_member.updated_at,
        user=user_summary,
    )


@router.delete(
    "/api/projects/{project_id}/members/{user_id}",
    response_model=dict,
    summary="Remove a project member",
    description="Remove a user from project membership. Application owners or project admins can remove members.",
    responses={
        200: {"description": "Project member removed successfully"},
        400: {"description": "Cannot remove the last project admin"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - only owners or project admins can remove members"},
        404: {"description": "Project or member not found"},
    },
)
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Remove a user from project membership.

    Application owners or project admins can remove project members.

    When a member is removed:
    - All tasks assigned to them in this project are unassigned
    - Project admins are notified if tasks need reassignment
    - The removed user receives a notification

    Cannot remove the last admin - must promote another member first.
    """
    # Verify current user can manage members (app owner OR project admin)
    project = verify_project_access(project_id, current_user, db, require_member_management=True)

    # Find the member record
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

    # Cannot remove the project creator
    if project.created_by == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project creator. The creator must always remain a member.",
        )

    # Check if this is the last admin
    if member.role == "admin":
        admin_count = db.query(func.count(ProjectMember.id)).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "admin",
        ).scalar()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last project admin. Promote another member to admin first.",
            )

    # Find all tasks assigned to this user in this project
    assigned_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignee_id == user_id,
    ).all()

    # Clear assignee from all tasks
    task_ids_cleared = []
    for task in assigned_tasks:
        task.assignee_id = None
        task.updated_at = datetime.utcnow()
        task_ids_cleared.append(str(task.id))

    # Store member name before deletion
    removed_user_name = member.user.display_name or member.user.email if member.user else "User"

    # Remove the member
    db.delete(member)
    db.commit()

    # Invalidate project role cache for removed user
    invalidate_project_role(user_id, project_id)

    # Create notifications
    # Notify the removed user
    removed_notification = NotificationCreate(
        user_id=user_id,
        type=NotificationType.PROJECT_MEMBER_REMOVED,
        title=f"Removed from {project.name}",
        message=f"You were removed from {project.name}",
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
    )
    await NotificationService.create_notification(db, removed_notification)

    # Notify project admins about tasks needing reassignment
    if task_ids_cleared:
        project_admins = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "admin",
        ).all()

        for admin in project_admins:
            admin_notification = NotificationCreate(
                user_id=admin.user_id,
                type=NotificationType.TASK_REASSIGNMENT_NEEDED,
                title=f"{len(task_ids_cleared)} task(s) need reassignment",
                message=f"Tasks were unassigned when {removed_user_name} was removed from {project.name}",
                entity_type=EntityType.PROJECT,
                entity_id=project_id,
            )
            await NotificationService.create_notification(db, admin_notification)

    # Broadcast member removed to project room for real-time updates
    room_id = f"project:{project_id}"
    await manager.broadcast_to_room(
        room_id,
        {
            "type": MessageType.PROJECT_MEMBER_REMOVED,
            "data": {
                "project_id": str(project_id),
                "user_id": str(user_id),
                "removed_by": str(current_user.id),
                "tasks_unassigned": len(task_ids_cleared),
            },
        },
    )

    return {
        "message": "Member removed",
        "tasks_unassigned": len(task_ids_cleared),
    }


@router.patch(
    "/api/projects/{project_id}/members/{user_id}/role",
    response_model=ProjectMemberWithUser,
    summary="Change a project member's role",
    description="Change a member's role (admin/member). Application owners or project admins can change roles.",
    responses={
        200: {"description": "Role changed successfully"},
        400: {"description": "Cannot demote the last admin"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - only owners or project admins can change roles"},
        404: {"description": "Project or member not found"},
    },
)
async def change_project_member_role(
    project_id: UUID,
    user_id: UUID,
    role_data: ProjectMemberUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProjectMemberWithUser:
    """
    Change a project member's role.

    Application owners or project admins can change member roles.
    Cannot demote the last admin - must have at least one admin.
    """
    # Verify current user can manage members (app owner OR project admin)
    project = verify_project_access(project_id, current_user, db, require_member_management=True)

    if not role_data.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role is required",
        )

    # Find the member record
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

    old_role = member.role
    new_role = role_data.role.value

    # No change needed
    if old_role == new_role:
        user_summary = UserSummary(
            id=member.user.id,
            email=member.user.email,
            display_name=member.user.display_name,
            avatar_url=member.user.avatar_url,
        ) if member.user else None

        return ProjectMemberWithUser(
            id=member.id,
            project_id=member.project_id,
            user_id=member.user_id,
            role=member.role,
            added_by_user_id=member.added_by_user_id,
            created_at=member.created_at,
            updated_at=member.updated_at,
            user=user_summary,
        )

    # Cannot demote the project creator
    if project.created_by == user_id and new_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote the project creator. The creator must always be an admin.",
        )

    # Check if demoting the last admin
    if old_role == "admin" and new_role == "member":
        admin_count = db.query(func.count(ProjectMember.id)).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "admin",
        ).scalar()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last project admin. Promote another member to admin first.",
            )

    # Update the role
    member.role = new_role
    member.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(member)

    # Invalidate project role cache for affected user
    invalidate_project_role(user_id, project_id)

    # Create notification for the affected user
    role_notification = NotificationCreate(
        user_id=user_id,
        type=NotificationType.PROJECT_ROLE_CHANGED,
        title=f"Role changed in {project.name}",
        message=f"Your role in {project.name} changed from {old_role} to {new_role}",
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
    )
    await NotificationService.create_notification(db, role_notification)

    # Broadcast role change to project room for real-time updates
    room_id = f"project:{project_id}"
    await manager.broadcast_to_room(
        room_id,
        {
            "type": MessageType.PROJECT_ROLE_CHANGED,
            "data": {
                "project_id": str(project_id),
                "user_id": str(user_id),
                "old_role": old_role,
                "new_role": new_role,
                "changed_by": str(current_user.id),
            },
        },
    )

    user_summary = UserSummary(
        id=member.user.id,
        email=member.user.email,
        display_name=member.user.display_name,
        avatar_url=member.user.avatar_url,
    ) if member.user else None

    return ProjectMemberWithUser(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        added_by_user_id=member.added_by_user_id,
        created_at=member.created_at,
        updated_at=member.updated_at,
        user=user_summary,
    )


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
    seen_user_ids = set()

    for member in members:
        app_role = get_user_application_role(
            db, member.user_id, project.application_id, project.application
        )
        if app_role in ("owner", "editor"):
            user_summary = None
            if member.user:
                user_summary = UserSummary(
                    id=member.user.id,
                    email=member.user.email,
                    display_name=member.user.display_name,
                    avatar_url=member.user.avatar_url,
                )
            assignable.append(ProjectMemberWithUser(
                id=member.id,
                project_id=member.project_id,
                user_id=member.user_id,
                role=member.role,
                added_by_user_id=member.added_by_user_id,
                created_at=member.created_at,
                updated_at=member.updated_at,
                user=user_summary,
            ))
            seen_user_ids.add(member.user_id)

    # Also include App Owners even if not project members
    # Include the original owner
    if project.application.owner_id not in seen_user_ids:
        owner_user = db.query(User).filter(
            User.id == project.application.owner_id
        ).first()
        if owner_user:
            user_summary = UserSummary(
                id=owner_user.id,
                email=owner_user.email,
                display_name=owner_user.display_name,
                avatar_url=owner_user.avatar_url,
            )
            # Create a "virtual" member response for the owner
            assignable.append(ProjectMemberWithUser(
                id=project.application.owner_id,  # Use owner's user ID as placeholder
                project_id=project_id,
                user_id=project.application.owner_id,
                role="owner",  # Virtual role for display
                added_by_user_id=None,
                created_at=project.created_at,
                updated_at=project.updated_at or project.created_at,
                user=user_summary,
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

    Returns membership status and role if member.
    Any member of the parent application can check membership.
    """
    # Verify user has access to view the project
    project = verify_project_access(project_id, current_user, db)

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    return {
        "is_member": member is not None,
        "role": member.role if member else None,
        "user_id": str(user_id),
        "project_id": str(project_id),
    }
