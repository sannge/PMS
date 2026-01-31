"""Invitation SQLAlchemy model for pending user invitations."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .application import Application
    from .application_member import ApplicationMember
    from .user import User


class Invitation(Base):
    """
    Invitation model representing pending user invitations to applications.

    Invitations track the process of inviting users to collaborate on
    applications with specific roles (owner, editor, viewer).

    Attributes:
        id: Unique identifier (UUID)
        application_id: FK to the application being shared
        inviter_id: FK to the user sending the invitation
        invitee_id: FK to the user being invited
        role: Role being offered (owner, editor, viewer)
        status: Current status (pending, accepted, rejected, cancelled)
        created_at: Timestamp when invitation was created
        responded_at: Timestamp when invitation was responded to
    """

    __tablename__ = "Invitations"
    __allow_unmapped__ = True

    # Composite indexes for optimal query performance
    __table_args__ = (
        # For listing pending invitations by invitee (most common query)
        Index('ix_invitations_invitee_status_created', 'invitee_id', 'status', 'created_at'),
        # For listing sent invitations by inviter
        Index('ix_invitations_inviter_status_created', 'inviter_id', 'status', 'created_at'),
        # For duplicate invitation check on create
        Index('ix_invitations_app_invitee_status', 'application_id', 'invitee_id', 'status'),
    )

    # Primary key - UUID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Foreign keys
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inviter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Invitation details
    role = Column(
        String(50),
        nullable=False,
        index=True,
    )
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    responded_at = Column(
        DateTime,
        nullable=True,
    )

    # Relationships
    application = relationship(
        "Application",
        back_populates="invitations",
        lazy="joined",
    )
    inviter = relationship(
        "User",
        foreign_keys=[inviter_id],
        back_populates="sent_invitations",
        lazy="joined",
    )
    invitee = relationship(
        "User",
        foreign_keys=[invitee_id],
        back_populates="received_invitations",
        lazy="joined",
    )
    membership = relationship(
        "ApplicationMember",
        back_populates="invitation",
        uselist=False,
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of Invitation."""
        return f"<Invitation(id={self.id}, application_id={self.application_id}, status={self.status})>"
