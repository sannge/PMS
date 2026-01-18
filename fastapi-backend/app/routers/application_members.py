"""Application Members CRUD API endpoints.

Provides endpoints for managing application members.
Supports listing members, updating roles, removing members, and manager assignment.
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
from ..models.application_member import ApplicationMember
from ..models.notification import Notification
from ..models.user import User
from ..schemas.application_member import (
    ManagerAssignment,
    MemberResponse,
    MemberUpdate,
    MemberWithUser,
)
from ..schemas.invitation import ApplicationRole
from ..schemas.notification import EntityType, NotificationType
from ..services.auth_service import get_current_user
from ..websocket.handlers import (
    handle_member_removed,
    handle_role_updated,
)

router = APIRouter(prefix="/api/applications", tags=["Application Members"])


# ============================================================================
# Helper Functions
# ============================================================================


def get_user_application_role(
    db: Session,
    user_id: UUID,
    application_id: UUID,
) -> Optional[str]:
    """
    Get the user's role in an application.

    Returns:
        The role string ('owner', 'editor', 'viewer') or None if not a member.
    """
    # Check if user is the owner
    app = db.query(Application).filter(Application.id == application_id).first()
    if app and app.owner_id == user_id:
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


def is_application_creator(
    db: Session,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """
    Check if the user is the original creator of the application.

    The creator is the user referenced by owner_id in the Application table.
    This is different from being an owner through membership - only the
    original creator can assign manager roles.
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    return app is not None and app.owner_id == user_id


def get_owner_count(
    db: Session,
    application_id: UUID,
) -> int:
    """
    Get the count of owners for an application.

    Counts both the original owner (from Application.owner_id) and any
    members with the 'owner' role.
    """
    # Count members with owner role
    member_owners = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.role == ApplicationRole.OWNER.value,
    ).scalar() or 0

    # Check if original owner still exists
    app = db.query(Application).filter(Application.id == application_id).first()
    if app and app.owner_id:
        # Check if original owner is also in members table
        original_in_members = db.query(ApplicationMember).filter(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == app.owner_id,
            ApplicationMember.role == ApplicationRole.OWNER.value,
        ).first()

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
    db: Session = Depends(get_db),
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

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **role**: Optional filter by member role

    Returns members ordered by creation date (oldest first, so original members appear first).
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is a member
    if not is_application_member(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    query = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
    )

    # Apply role filter if provided
    if role_filter:
        query = query.filter(ApplicationMember.role == role_filter.value)

    # Order by creation date (oldest first)
    query = query.order_by(ApplicationMember.created_at.asc())

    # Apply pagination
    members = query.offset(skip).limit(limit).all()

    return members


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
    db: Session = Depends(get_db),
) -> dict:
    """
    Get member count for an application.

    Returns:
    - total: Total number of members
    - by_role: Count breakdown by role
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is a member
    if not is_application_member(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    total = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
    ).scalar() or 0

    owners = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.role == ApplicationRole.OWNER.value,
    ).scalar() or 0

    editors = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.role == ApplicationRole.EDITOR.value,
    ).scalar() or 0

    viewers = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.role == ApplicationRole.VIEWER.value,
    ).scalar() or 0

    managers = db.query(func.count(ApplicationMember.id)).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.is_manager == True,
    ).scalar() or 0

    return {
        "total": total,
        "by_role": {
            "owners": owners,
            "editors": editors,
            "viewers": viewers,
        },
        "managers": managers,
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
    db: Session = Depends(get_db),
) -> MemberWithUser:
    """
    Get a specific member by user ID.

    Any member of the application can view member details.
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is a member
    if not is_application_member(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

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
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Application or member not found"},
    },
)
async def update_member_role(
    application_id: UUID,
    user_id: UUID,
    member_data: MemberUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MemberWithUser:
    """
    Update a member's role.

    Only application owners can update member roles.
    Cannot remove the last owner from an application.

    - **role**: New role (owner, editor, viewer)
    - **is_manager**: Whether to grant/revoke manager privileges (editors only)
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Verify current user is owner
    if not is_application_owner(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only application owners can update member roles.",
        )

    # Cannot update your own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot update your own role.",
        )

    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    old_role = member.role

    # Validate role change
    if member_data.role is not None:
        new_role = member_data.role.value

        # Prevent removing last owner
        if old_role == ApplicationRole.OWNER.value and new_role != ApplicationRole.OWNER.value:
            owner_count = get_owner_count(db, application_id)
            if owner_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change role. This is the last owner of the application.",
                )

        member.role = new_role

        # If downgrading from editor to viewer, remove manager role
        if old_role == ApplicationRole.EDITOR.value and new_role == ApplicationRole.VIEWER.value:
            member.is_manager = False

    # Handle is_manager separately (only for editors)
    if member_data.is_manager is not None:
        # Manager role can only be assigned to editors
        if member.role != ApplicationRole.EDITOR.value and member_data.is_manager:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager role can only be assigned to editors.",
            )

        # Only the application creator can assign manager role
        if member_data.is_manager and not is_application_creator(db, current_user.id, application_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the application creator can assign manager role.",
            )

        member.is_manager = member_data.is_manager

    member.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(member)

    # Create notification for affected user
    if member_data.role is not None and old_role != member.role:
        notification = Notification(
            user_id=user_id,
            type=NotificationType.ROLE_CHANGED.value,
            title="Role Changed",
            message=f"Your role in '{application.name}' has been changed from {old_role} to {member.role}",
            entity_type=EntityType.APPLICATION_MEMBER.value,
            entity_id=member.id,
        )
        db.add(notification)
        db.commit()

        # Send WebSocket notification
        await handle_role_updated(
            application_id=application_id,
            user_id=user_id,
            role_data={
                "user_id": str(user_id),
                "user_name": member.user.display_name or member.user.email if member.user else None,
                "old_role": old_role,
                "new_role": member.role,
                "is_manager": member.is_manager,
                "updated_by": str(current_user.id),
            },
        )

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
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Application or member not found"},
    },
)
async def remove_member(
    application_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Remove a member from the application.

    Only application owners can remove members.
    Cannot remove the last owner.
    Members can remove themselves from an application.
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Members can remove themselves, owners can remove anyone
    is_self_removal = user_id == current_user.id
    is_owner = is_application_owner(db, current_user.id, application_id)

    if not is_self_removal and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only application owners can remove other members.",
        )

    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    # Prevent removing last owner
    if member.role == ApplicationRole.OWNER.value:
        owner_count = get_owner_count(db, application_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last owner of the application.",
            )

    # Store member info for notifications before deletion
    member_user = member.user
    member_name = member_user.display_name or member_user.email if member_user else None

    db.delete(member)
    db.commit()

    # Send WebSocket notification
    await handle_member_removed(
        application_id=application_id,
        removed_user_id=user_id,
        member_data={
            "user_id": str(user_id),
            "user_name": member_name,
            "removed_by": str(current_user.id),
            "reason": "self_removal" if is_self_removal else "removed_by_owner",
        },
    )

    return None


# ============================================================================
# Manager role endpoints
# ============================================================================


@router.post(
    "/{application_id}/members/{user_id}/manager",
    response_model=MemberWithUser,
    summary="Grant manager role",
    description="Grant manager role to an editor.",
    responses={
        200: {"description": "Manager role granted successfully"},
        400: {"description": "User is not an editor or already a manager"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the creator"},
        404: {"description": "Application or member not found"},
    },
)
async def grant_manager_role(
    application_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MemberWithUser:
    """
    Grant manager role to an editor.

    Only the application creator can grant manager role.
    Manager role can only be assigned to editors.
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Only creator can assign manager role
    if not is_application_creator(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the application creator can grant manager role.",
        )

    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    # Manager role is only for editors
    if member.role != ApplicationRole.EDITOR.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager role can only be assigned to editors.",
        )

    if member.is_manager:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This member is already a manager.",
        )

    member.is_manager = True
    member.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(member)

    # Create notification for affected user
    notification = Notification(
        user_id=user_id,
        type=NotificationType.ROLE_CHANGED.value,
        title="Manager Role Granted",
        message=f"You have been granted manager privileges in '{application.name}'",
        entity_type=EntityType.APPLICATION_MEMBER.value,
        entity_id=member.id,
    )
    db.add(notification)
    db.commit()

    # Send WebSocket notification
    await handle_role_updated(
        application_id=application_id,
        user_id=user_id,
        role_data={
            "user_id": str(user_id),
            "user_name": member.user.display_name or member.user.email if member.user else None,
            "old_role": member.role,
            "new_role": member.role,
            "is_manager": True,
            "updated_by": str(current_user.id),
        },
    )

    return member


@router.delete(
    "/{application_id}/members/{user_id}/manager",
    response_model=MemberWithUser,
    summary="Revoke manager role",
    description="Revoke manager role from an editor.",
    responses={
        200: {"description": "Manager role revoked successfully"},
        400: {"description": "User is not a manager"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the creator"},
        404: {"description": "Application or member not found"},
    },
)
async def revoke_manager_role(
    application_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> MemberWithUser:
    """
    Revoke manager role from an editor.

    Only the application creator can revoke manager role.
    """
    # Verify application exists
    application = db.query(Application).filter(
        Application.id == application_id,
    ).first()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application with ID {application_id} not found",
        )

    # Only creator can revoke manager role
    if not is_application_creator(db, current_user.id, application_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the application creator can revoke manager role.",
        )

    member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == application_id,
        ApplicationMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member with user ID {user_id} not found in this application",
        )

    if not member.is_manager:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This member is not a manager.",
        )

    member.is_manager = False
    member.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(member)

    # Create notification for affected user
    notification = Notification(
        user_id=user_id,
        type=NotificationType.ROLE_CHANGED.value,
        title="Manager Role Revoked",
        message=f"Your manager privileges in '{application.name}' have been revoked",
        entity_type=EntityType.APPLICATION_MEMBER.value,
        entity_id=member.id,
    )
    db.add(notification)
    db.commit()

    # Send WebSocket notification
    await handle_role_updated(
        application_id=application_id,
        user_id=user_id,
        role_data={
            "user_id": str(user_id),
            "user_name": member.user.display_name or member.user.email if member.user else None,
            "old_role": member.role,
            "new_role": member.role,
            "is_manager": False,
            "updated_by": str(current_user.id),
        },
    )

    return member
