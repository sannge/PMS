"""Invitations CRUD API endpoints.

Provides endpoints for managing application invitations.
Supports creating, listing, accepting, rejecting, and cancelling invitations.
All endpoints require authentication.

Role-based permissions for creating invitations:
- Viewer: Cannot invite anyone
- Editor: Can invite with viewer or editor roles only
- Owner: Can invite with any role (owner, editor, viewer)
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.invitation import Invitation
from ..models.notification import Notification
from ..models.user import User
from ..schemas.invitation import (
    ApplicationRole,
    InvitationCreate,
    InvitationResponse,
    InvitationStatus,
    InvitationWithDetails,
    InvitationList,
)
from ..schemas.notification import EntityType, NotificationType
from ..services.auth_service import get_current_user
from ..websocket.handlers import (
    handle_invitation_notification,
    handle_invitation_response,
    handle_member_added,
)

router = APIRouter(prefix="/api/invitations", tags=["Invitations"])


# ============================================================================
# Helper Functions
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


async def create_invitation_notification(
    db: Session,
    invitation: Invitation,
    inviter: User,
    application: Application,
) -> None:
    """
    Create a notification and send WebSocket message for a new invitation.
    """
    # Create notification in database
    notification = Notification(
        user_id=invitation.invitee_id,
        type=NotificationType.APPLICATION_INVITE.value,
        title="Application Invitation",
        message=f"{inviter.display_name or inviter.email} invited you to join '{application.name}' as {invitation.role}",
        entity_type=EntityType.INVITATION.value,
        entity_id=invitation.id,
    )
    db.add(notification)
    db.commit()

    # Send WebSocket notification
    await handle_invitation_notification(
        user_id=invitation.invitee_id,
        invitation_data={
            "invitation_id": str(invitation.id),
            "application_id": str(invitation.application_id),
            "application_name": application.name,
            "inviter_id": str(inviter.id),
            "inviter_name": inviter.display_name or inviter.email,
            "inviter_email": inviter.email,
            "role": invitation.role,
        },
    )


# ============================================================================
# List endpoints
# ============================================================================


@router.get(
    "",
    response_model=List[InvitationWithDetails],
    summary="List my pending invitations",
    description="Get all pending invitations for the authenticated user.",
    responses={
        200: {"description": "List of invitations retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_my_invitations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    status_filter: Optional[InvitationStatus] = Query(
        None,
        alias="status",
        description="Filter by invitation status",
    ),
) -> List[InvitationWithDetails]:
    """
    List invitations for the authenticated user.

    By default returns only pending invitations unless a specific status is requested.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **status**: Optional filter by invitation status

    Returns invitations ordered by creation date (newest first).
    """
    query = db.query(Invitation).filter(
        Invitation.invitee_id == current_user.id,
    )

    # Apply status filter - default to pending if not specified
    if status_filter:
        query = query.filter(Invitation.status == status_filter.value)
    else:
        query = query.filter(Invitation.status == InvitationStatus.PENDING.value)

    # Order by newest first
    query = query.order_by(Invitation.created_at.desc())

    # Apply pagination
    invitations = query.offset(skip).limit(limit).all()

    return invitations


@router.get(
    "/sent",
    response_model=List[InvitationWithDetails],
    summary="List sent invitations",
    description="Get all invitations sent by the authenticated user.",
    responses={
        200: {"description": "List of sent invitations retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def list_sent_invitations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    status_filter: Optional[InvitationStatus] = Query(
        None,
        alias="status",
        description="Filter by invitation status",
    ),
) -> List[InvitationWithDetails]:
    """
    List invitations sent by the authenticated user.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **status**: Optional filter by invitation status

    Returns invitations ordered by creation date (newest first).
    """
    query = db.query(Invitation).filter(
        Invitation.inviter_id == current_user.id,
    )

    # Apply status filter if provided
    if status_filter:
        query = query.filter(Invitation.status == status_filter.value)

    # Order by newest first
    query = query.order_by(Invitation.created_at.desc())

    # Apply pagination
    invitations = query.offset(skip).limit(limit).all()

    return invitations


@router.get(
    "/count",
    response_model=dict,
    summary="Get invitation counts",
    description="Get pending invitation count for the authenticated user.",
    responses={
        200: {"description": "Invitation count retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def get_invitation_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> dict:
    """
    Get pending invitation count for the authenticated user.

    Returns:
    - count: Number of pending invitations
    """
    count = db.query(func.count(Invitation.id)).filter(
        Invitation.invitee_id == current_user.id,
        Invitation.status == InvitationStatus.PENDING.value,
    ).scalar() or 0

    return {"count": count}


# ============================================================================
# Individual invitation endpoints
# ============================================================================


@router.get(
    "/{invitation_id}",
    response_model=InvitationWithDetails,
    summary="Get an invitation by ID",
    description="Get details of a specific invitation.",
    responses={
        200: {"description": "Invitation retrieved successfully"},
        401: {"description": "Not authenticated"},
        404: {"description": "Invitation not found"},
    },
)
async def get_invitation(
    invitation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> InvitationWithDetails:
    """
    Get a specific invitation by its ID.

    Only the inviter or invitee can access the invitation.
    """
    # Include auth check in query to prevent information leakage
    # (attacker can't discover if invitation IDs exist by comparing error responses)
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id,
        or_(
            Invitation.inviter_id == current_user.id,
            Invitation.invitee_id == current_user.id,
        ),
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    return invitation


@router.post(
    "/{invitation_id}/accept",
    response_model=InvitationResponse,
    summary="Accept an invitation",
    description="Accept a pending invitation to join an application.",
    responses={
        200: {"description": "Invitation accepted successfully"},
        400: {"description": "Invitation is not pending"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the invitee"},
        404: {"description": "Invitation not found"},
    },
)
async def accept_invitation(
    invitation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """
    Accept a pending invitation.

    This will:
    1. Update the invitation status to 'accepted'
    2. Create an ApplicationMember record
    3. Notify the inviter

    Uses pessimistic locking to prevent race conditions on concurrent accepts.
    """
    # Use SELECT FOR UPDATE to prevent race conditions
    # Filter by invitee_id in the same query for efficiency and security
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id,
        Invitation.invitee_id == current_user.id,  # Auth check in query
    ).with_for_update().first()

    if not invitation:
        # Check if invitation exists at all (for better error message)
        exists = db.query(Invitation.id).filter(Invitation.id == invitation_id).first()
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invitation with ID {invitation_id} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the invitee can accept this invitation.",
        )

    # Must be pending (checked after lock acquired)
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is not pending. Current status: {invitation.status}",
        )

    # Check if user is already a member (with lock to prevent race)
    existing_member = db.query(ApplicationMember).filter(
        ApplicationMember.application_id == invitation.application_id,
        ApplicationMember.user_id == current_user.id,
    ).with_for_update().first()

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this application.",
        )

    # Update invitation status
    invitation.status = InvitationStatus.ACCEPTED.value
    invitation.responded_at = datetime.utcnow()

    # Create membership
    member = ApplicationMember(
        application_id=invitation.application_id,
        user_id=current_user.id,
        role=invitation.role,
        invitation_id=invitation.id,
        is_manager=False,
    )
    db.add(member)

    # Create notification for inviter
    notification = Notification(
        user_id=invitation.inviter_id,
        type=NotificationType.INVITATION_ACCEPTED.value,
        title="Invitation Accepted",
        message=f"{current_user.display_name or current_user.email} accepted your invitation to join '{invitation.application.name}'",
        entity_type=EntityType.INVITATION.value,
        entity_id=invitation.id,
    )
    db.add(notification)

    db.commit()
    db.refresh(invitation)

    # Send WebSocket notifications
    await handle_invitation_response(
        inviter_id=invitation.inviter_id,
        application_id=invitation.application_id,
        response_data={
            "invitation_id": str(invitation.id),
            "invitee_id": str(current_user.id),
            "invitee_name": current_user.display_name or current_user.email,
            "invitee_email": current_user.email,
            "status": InvitationStatus.ACCEPTED.value,
            "role": invitation.role,
        },
    )

    await handle_member_added(
        application_id=invitation.application_id,
        member_data={
            "user_id": str(current_user.id),
            "user_name": current_user.display_name or current_user.email,
            "user_email": current_user.email,
            "application_name": invitation.application.name,
            "role": invitation.role,
            "is_manager": False,
            "added_by": str(invitation.inviter_id),
        },
    )

    return invitation


@router.post(
    "/{invitation_id}/reject",
    response_model=InvitationResponse,
    summary="Reject an invitation",
    description="Reject a pending invitation to join an application.",
    responses={
        200: {"description": "Invitation rejected successfully"},
        400: {"description": "Invitation is not pending"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the invitee"},
        404: {"description": "Invitation not found"},
    },
)
async def reject_invitation(
    invitation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """
    Reject a pending invitation.

    This will:
    1. Update the invitation status to 'rejected'
    2. Notify the inviter

    Uses pessimistic locking to prevent race conditions.
    """
    # Use SELECT FOR UPDATE with auth check in query
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id,
        Invitation.invitee_id == current_user.id,  # Auth check in query
    ).with_for_update().first()

    if not invitation:
        # Check if invitation exists at all (for better error message)
        exists = db.query(Invitation.id).filter(Invitation.id == invitation_id).first()
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invitation with ID {invitation_id} not found",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the invitee can reject this invitation.",
        )

    # Must be pending (checked after lock acquired)
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is not pending. Current status: {invitation.status}",
        )

    # Update invitation status
    invitation.status = InvitationStatus.REJECTED.value
    invitation.responded_at = datetime.utcnow()

    # Create notification for inviter
    notification = Notification(
        user_id=invitation.inviter_id,
        type=NotificationType.INVITATION_REJECTED.value,
        title="Invitation Rejected",
        message=f"{current_user.display_name or current_user.email} declined your invitation to join '{invitation.application.name}'",
        entity_type=EntityType.INVITATION.value,
        entity_id=invitation.id,
    )
    db.add(notification)

    db.commit()
    db.refresh(invitation)

    # Send WebSocket notification to inviter
    await handle_invitation_response(
        inviter_id=invitation.inviter_id,
        application_id=invitation.application_id,
        response_data={
            "invitation_id": str(invitation.id),
            "invitee_id": str(current_user.id),
            "invitee_name": current_user.display_name or current_user.email,
            "invitee_email": current_user.email,
            "status": InvitationStatus.REJECTED.value,
            "role": invitation.role,
        },
    )

    return invitation


@router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel an invitation",
    description="Cancel a pending invitation (inviter only).",
    responses={
        204: {"description": "Invitation cancelled successfully"},
        400: {"description": "Invitation is not pending"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not the inviter"},
        404: {"description": "Invitation not found"},
    },
)
async def cancel_invitation(
    invitation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> None:
    """
    Cancel a pending invitation.

    Only the inviter can cancel an invitation.
    This will update the invitation status to 'cancelled'.
    """
    # Use pessimistic locking and include auth check in query to prevent
    # race conditions and information leakage
    invitation = db.query(Invitation).filter(
        Invitation.id == invitation_id,
        Invitation.inviter_id == current_user.id,  # Auth check in query
    ).with_for_update().first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Must be pending
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is not pending. Current status: {invitation.status}",
        )

    # Store invitee_id before update for WebSocket notification
    invitee_id = invitation.invitee_id
    application_id = invitation.application_id

    # Update status to cancelled
    invitation.status = InvitationStatus.CANCELLED.value
    invitation.responded_at = datetime.utcnow()

    db.commit()

    # Notify the invitee that the invitation was cancelled
    await handle_invitation_response(
        inviter_id=invitee_id,  # Notify the invitee (not the inviter)
        application_id=application_id,
        response_data={
            "invitation_id": str(invitation_id),
            "inviter_id": str(current_user.id),
            "inviter_name": current_user.display_name or current_user.email,
            "status": "cancelled",
            "role": invitation.role,
        },
    )

    return None


# ============================================================================
# Application-scoped invitation endpoints
# ============================================================================


@router.post(
    "/applications/{application_id}",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an invitation",
    description="Create an invitation to invite a user to an application.",
    responses={
        201: {"description": "Invitation created successfully"},
        400: {"description": "Invalid invitation (self-invite, duplicate, or already member)"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - insufficient permissions"},
        404: {"description": "Application or user not found"},
    },
)
async def create_invitation(
    application_id: UUID,
    invitation_data: InvitationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """
    Create an invitation to invite a user to an application.

    Role-based permissions:
    - Viewer: Cannot invite anyone
    - Editor: Can invite with viewer or editor roles only
    - Owner: Can invite with any role (owner, editor, viewer)

    - **invitee_id**: ID of the user to invite
    - **role**: Role to assign (owner, editor, viewer)

    Edge cases handled:
    - Cannot invite yourself
    - Cannot invite someone who is already a member
    - Cannot invite someone who has a pending invitation
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

    # Get current user's role (pass application to avoid re-fetching)
    current_user_role = get_user_application_role(db, current_user.id, application_id, application)

    if current_user_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a member of this application.",
        )

    # Viewers cannot invite
    if current_user_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Viewers cannot send invitations.",
        )

    # Editors can only invite with viewer or editor roles
    if current_user_role == "editor":
        if invitation_data.role == ApplicationRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Editors cannot invite with owner role. Only viewer or editor roles allowed.",
            )

    # Prevent self-invitation
    if invitation_data.invitee_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot invite yourself to an application.",
        )

    # Verify invitee exists
    invitee = db.query(User).filter(
        User.id == invitation_data.invitee_id,
    ).first()

    if not invitee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {invitation_data.invitee_id} not found",
        )

    # Check if invitee is already a member
    if is_application_member(db, invitation_data.invitee_id, application_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user is already a member of the application.",
        )

    # Check for existing pending invitation
    existing_invitation = db.query(Invitation).filter(
        Invitation.application_id == application_id,
        Invitation.invitee_id == invitation_data.invitee_id,
        Invitation.status == InvitationStatus.PENDING.value,
    ).first()

    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending invitation already exists for this user.",
        )

    # Create invitation
    invitation = Invitation(
        application_id=application_id,
        inviter_id=current_user.id,
        invitee_id=invitation_data.invitee_id,
        role=invitation_data.role.value,
        status=InvitationStatus.PENDING.value,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    # Create notification and send WebSocket message
    await create_invitation_notification(
        db=db,
        invitation=invitation,
        inviter=current_user,
        application=application,
    )

    return invitation


@router.get(
    "/applications/{application_id}",
    response_model=List[InvitationWithDetails],
    summary="List application invitations",
    description="Get all invitations for a specific application (owner only).",
    responses={
        200: {"description": "List of invitations retrieved successfully"},
        401: {"description": "Not authenticated"},
        403: {"description": "Access denied - not an owner"},
        404: {"description": "Application not found"},
    },
)
async def list_application_invitations(
    application_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of records to return"),
    status_filter: Optional[InvitationStatus] = Query(
        None,
        alias="status",
        description="Filter by invitation status",
    ),
) -> List[InvitationWithDetails]:
    """
    List invitations for a specific application.

    Only application owners can view all invitations.

    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return (1-100)
    - **status**: Optional filter by invitation status

    Returns invitations ordered by creation date (newest first).
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
            detail="Access denied. Only application owners can view all invitations.",
        )

    query = db.query(Invitation).filter(
        Invitation.application_id == application_id,
    )

    # Apply status filter if provided
    if status_filter:
        query = query.filter(Invitation.status == status_filter.value)

    # Order by newest first
    query = query.order_by(Invitation.created_at.desc())

    # Apply pagination
    invitations = query.offset(skip).limit(limit).all()

    return invitations
