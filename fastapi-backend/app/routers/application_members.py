"""Application Members CRUD API endpoints.

Provides endpoints for managing application members.
Supports listing members, updating roles, and removing members.
All endpoints require authentication.

Role-based permissions:
- Viewer: Can view members only. Cannot edit roles, invite, or remove members.
- Editor: Can promote viewers to editors. Can invite with viewer or editor roles.
- Owner: Full access - can invite with any role, update any role, remove members.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.task import Task
from ..models.task_status import TaskStatus, StatusCategory
from ..models.user import User
from ..schemas.application_member import (
    MemberUpdate,
    MemberWithUser,
)
from ..schemas.invitation import ApplicationRole
from ..schemas.notification import EntityType, NotificationType
from ..services.auth_service import get_current_user
from ..services.notification_service import NotificationService
from ..services.user_cache_service import invalidate_app_role
from ..schemas.notification import NotificationCreate
from ..websocket.handlers import (
    handle_member_removed,
    handle_role_updated,
)
from ..websocket.room_auth import invalidate_user_cache

router = APIRouter(prefix="/api/applications", tags=["Application Members"])


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


async def is_application_editor_or_above(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is an editor or owner of the application."""
    role = await get_user_application_role(db, user_id, application_id)
    return role in ("owner", "editor")


async def get_owner_count(
    db: AsyncSession,
    application_id: UUID,
) -> int:
    """
    Get the count of owners for an application.

    Counts both the original owner (from Application.owner_id) and any
    members with the 'owner' role.
    """
    # Count members with owner role
    result = await db.execute(
        select(func.count(ApplicationMember.id)).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.role == ApplicationRole.OWNER.value,
        )
    )
    member_owners = result.scalar() or 0

    # Check if original owner still exists
    result = await db.execute(select(Application).where(Application.id == application_id))
    app = result.scalar_one_or_none()
    if app and app.owner_id:
        # Check if original owner is also in members table
        result = await db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == application_id,
                ApplicationMember.user_id == app.owner_id,
                ApplicationMember.role == ApplicationRole.OWNER.value,
            )
        )
        original_in_members = result.scalar_one_or_none()

        # If not in members, count them as an additional owner
        if not original_in_members:
            return member_owners + 1

    return member_owners


# ============================================================================
# List endpoints
# ============================================================================


@router.get(
    "/{application_id}/members",
    response_model=List[MemberWithUser],
    summary="List application members",
    description="Get all members of an application.",
    responses={
        200: {"description": "List of members retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def list_application_members(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    role_filter: Optional[ApplicationRole] = Query(
        None,
        alias="role",
        description="Filter by member role",
    ),
) -> List[MemberWithUser]:
    """
    List members of an application.

    Any member of the application can view the member list.
    The application owner is always included in the list even if not in the
    ApplicationMembers table.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **role**: Optional filter by member role

    Returns members ordered by creation date (oldest first, so original members appear first).
    The owner appears first.
    """
    # Fetch application with owner eagerly loaded in single query
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.owner))
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Fetch all members with users eagerly loaded in a single optimized query
    # This also serves to check if current user is a member
    result = await db.execute(
        select(ApplicationMember)
        .options(selectinload(ApplicationMember.user))
        .where(ApplicationMember.application_id == application_id)
    )
    all_members = list(result.scalars().all())

    # Check if current user is a member (either app owner or in members list)
    is_app_owner = application.owner_id == current_user.id
    current_user_member = next(
        (m for m in all_members if m.user_id == current_user.id),
        None
    )

    if not is_app_owner and not current_user_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    result_members = []

    # Check if owner is in the members list
    owner_in_members = next(
        (m for m in all_members if m.user_id == application.owner_id),
        None
    )

    # If owner is not in members table, create a synthetic member entry
    # and add them at the beginning (only if not filtering by role or filtering by owner)
    if not owner_in_members and application.owner_id and application.owner:
        if role_filter is None or role_filter == ApplicationRole.OWNER:
            # Create a synthetic member object for the owner
            # This won't be persisted, just returned in the response
            synthetic_owner = ApplicationMember(
                id=application.owner_id,  # Use owner's user_id as member id
                application_id=application_id,
                user_id=application.owner_id,
                role=ApplicationRole.OWNER.value,
                created_at=application.created_at,  # Use app creation date
                updated_at=application.updated_at,
            )
            # Manually set the user relationship for serialization
            synthetic_owner.user = application.owner
            result_members.append(synthetic_owner)

    # Filter and sort members in memory (already fetched)
    filtered_members = all_members
    if role_filter:
        filtered_members = [m for m in all_members if m.role == role_filter.value]

    # Sort by creation date (oldest first)
    filtered_members = sorted(filtered_members, key=lambda m: m.created_at)

    # Apply pagination (account for synthetic owner if present)
    effective_skip = max(0, skip - len(result_members)) if result_members else skip
    effective_limit = limit - len(result_members) if result_members else limit

    if effective_limit > 0:
        paginated_members = filtered_members[effective_skip:effective_skip + effective_limit]
        result_members.extend(paginated_members)

    return result_members


@router.get(
    "/{application_id}/members/count",
    response_model=dict,
    summary="Get member count",
    description="Get total member count for an application.",
    responses={
        200: {"description": "Member count retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application not found"},
    },
)
async def get_member_count(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get member count for an application.

    Returns:
    - total: Total number of members
    - by_role: Count breakdown by role
    """
    # Verify application exists
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is a member
    if not await is_application_member(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    # Single query with GROUP BY instead of 4 separate queries
    result = await db.execute(
        select(
            ApplicationMember.role,
            func.count(ApplicationMember.id).label("count"),
        )
        .where(ApplicationMember.application_id == application_id)
        .group_by(ApplicationMember.role)
    )
    role_counts = result.all()

    # Convert to dict for easy lookup
    counts_by_role = {role: count for role, count in role_counts}

    owners = counts_by_role.get(ApplicationRole.OWNER.value, 0)
    editors = counts_by_role.get(ApplicationRole.EDITOR.value, 0)
    viewers = counts_by_role.get(ApplicationRole.VIEWER.value, 0)
    total = owners + editors + viewers

    return {
        "total": total,
        "by_role": {
            "owners": owners,
            "editors": editors,
            "viewers": viewers,
        },
    }


# ============================================================================
# Individual member endpoints
# ============================================================================


@router.get(
    "/{application_id}/members/{user_id}",
    response_model=MemberWithUser,
    summary="Get a member by user ID",
    description="Get details of a specific member.",
    responses={
        200: {"description": "Member retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not a member"},
        404: {"description": "Application or member not found"},
    },
)
async def get_member(
    application_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> MemberWithUser:
    """
    Get a specific member by user ID.

    Any member of the application can view member details.
    """
    # Verify application exists
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is a member
    if not await is_application_member(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    result = await db.execute(
        select(ApplicationMember).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    return member


@router.put(
    "/{application_id}/members/{user_id}",
    response_model=MemberWithUser,
    summary="Update a member's role",
    description="Update a member's role in the application.",
    responses={
        200: {"description": "Member updated successfully"},
        400: {"description": "Invalid role change"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - insufficient permissions"},
        404: {"description": "Application or member not found"},
    },
)
async def update_member_role(
    application_id: UUID,
    user_id: UUID,
    member_data: MemberUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> MemberWithUser:
    """
    Update a member's role.

    Role-based permissions:
    - Viewer: Cannot update roles
    - Editor: Can only promote viewers to editors
    - Owner: Can update any role (owner, editor, viewer)

    Cannot remove the last owner from an application.
    """
    # Verify application exists
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Get current user's role (pass application to avoid re-fetching)
    current_user_role = await get_user_application_role(db, current_user.id, application_id, application)

    if current_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    # Viewers cannot update roles
    if current_user_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Viewers cannot update member roles.",
        )

    # Cannot update your own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot update your own role.",
        )

    # Fetch member with user eagerly loaded
    result = await db.execute(
        select(ApplicationMember)
        .options(selectinload(ApplicationMember.user))
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    old_role = member.role

    if member_data.role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role is required.",
        )

    new_role = member_data.role.value

    # Editor permission checks
    if current_user_role == "editor":
        # Editors can only promote viewers to editors
        if old_role != ApplicationRole.VIEWER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Editors can only change the role of viewers.",
            )
        if new_role != ApplicationRole.EDITOR.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Editors can only promote viewers to editors.",
            )

    # Owner permission checks
    if current_user_role == "owner":
        # Prevent removing last owner
        if old_role == ApplicationRole.OWNER.value and new_role != ApplicationRole.OWNER.value:
            owner_count = await get_owner_count(db, application_id)
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change role. This is the last owner of the application.",
                )

    member.role = new_role
    member.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(member)

    # Invalidate role cache for affected user
    invalidate_app_role(user_id, application_id)

    # Create notification for affected user (with WebSocket broadcast)
    if old_role != member.role:
        notification_data = NotificationCreate(
            user_id=user_id,
            type=NotificationType.ROLE_CHANGED,
            title="Role Changed",
            message=f"Your role in '{application.name}' has been changed from {old_role} to {member.role}",
            entity_type=EntityType.APPLICATION_MEMBER,
            entity_id=member.id,
        )
        await NotificationService.create_notification(db, notification_data)

        # Send WebSocket notification
        await handle_role_updated(
            application_id=application_id,
            user_id=user_id,
            role_data={
                "user_id": str(user_id),
                "user_name": member.user.display_name or member.user.email if member.user else None,
                "application_name": application.name,
                "old_role": old_role,
                "new_role": member.role,
                "updated_by": str(current_user.id),
                "updated_by_name": current_user.display_name or current_user.email,
            },
        )

        # Invalidate room auth cache so WS room access reflects new role
        invalidate_user_cache(user_id)

    return member


@router.delete(
    "/{application_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member",
    description="Remove a member from the application.",
    responses={
        204: {"description": "Member removed successfully"},
        400: {"description": "Cannot remove last owner"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - insufficient permissions"},
        404: {"description": "Application or member not found"},
        409: {"description": "Member has active tasks assigned in one or more projects"},
    },
)
async def remove_member(
    application_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a member from the application.

    Role-based permissions:
    - Any member can remove themselves (self-removal)
    - Viewer: Cannot remove other members
    - Editor: Cannot remove other members
    - Owner: Can remove any member

    Removal is blocked if the member has active tasks assigned (not Done, not archived)
    in any project within the application.

    Cannot remove the last owner.
    """
    # Verify application exists
    result = await db.execute(select(Application).where(Application.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Get current user's role (pass application to avoid re-fetching)
    current_user_role = await get_user_application_role(db, current_user.id, application_id, application)

    if current_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    is_self_removal = user_id == current_user.id
    is_owner = current_user_role == "owner"

    # Only owners can remove other members (anyone can self-remove)
    if not is_self_removal and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only owners can remove other members.",
        )

    # Fetch member with user eagerly loaded
    result = await db.execute(
        select(ApplicationMember)
        .options(selectinload(ApplicationMember.user))
        .where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    # Prevent removing last owner
    if member.role == ApplicationRole.OWNER.value:
        owner_count = await get_owner_count(db, application_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner of the application.",
            )

    # Check for active tasks assigned to this user across all projects in the application
    # Active = not Done and not archived
    result = await db.execute(
        select(Task.id, Project.name)
        .join(Project, Task.project_id == Project.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Project.application_id == application_id,
            Task.assignee_id == user_id,
            Task.archived_at.is_(None),
            TaskStatus.category != StatusCategory.DONE.value,
        )
    )
    active_tasks = result.all()

    active_assignments: list[dict] = []
    if active_tasks:
        # Group active tasks by project name
        project_counts: dict[str, int] = {}
        for _task_id, project_name in active_tasks:
            project_counts[project_name] = project_counts.get(project_name, 0) + 1

        active_assignments = [
            {"project_name": name, "active_task_count": count}
            for name, count in project_counts.items()
        ]

    if active_assignments:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Cannot remove member. They have active tasks assigned.",
                "active_assignments": active_assignments,
            },
        )

    # Store member info for notifications before deletion
    member_user = member.user
    member_name = member_user.display_name or member_user.email if member_user else None

    await db.delete(member)
    await db.commit()

    # Invalidate role cache for removed user
    invalidate_app_role(user_id, application_id)

    # Create notification for removed user (with WebSocket broadcast, unless self-removal)
    if not is_self_removal:
        remover_name = current_user.display_name or current_user.email
        notification_data = NotificationCreate(
            user_id=user_id,
            type=NotificationType.MEMBER_REMOVED,
            title="Removed from Application",
            message=f"You were removed from '{application.name}' by {remover_name}",
            entity_type=EntityType.APPLICATION,
            entity_id=application_id,
        )
        await NotificationService.create_notification(db, notification_data)

    # Send WebSocket notification
    remover_name = current_user.display_name or current_user.email
    await handle_member_removed(
        application_id=application_id,
        removed_user_id=user_id,
        member_data={
            "user_id": str(user_id),
            "user_name": member_name,
            "application_name": application.name,
            "removed_by": str(current_user.id),
            "removed_by_name": remover_name,
            "reason": "self_removal" if is_self_removal else "removed_by_owner",
        },
    )

    # Invalidate room auth cache so removed user can no longer join rooms
    invalidate_user_cache(user_id)

    return None
