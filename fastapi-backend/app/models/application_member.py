"""ApplicationMember SQLAlchemy model for user-application relationships with roles."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .application import Application
    from .invitation import Invitation
    from .user import User


class ApplicationMember(Base):
    """
    ApplicationMember model representing user-application relationships.

    ApplicationMembers track which users have access to an application
    and what role they have (owner, editor, viewer).

    Attributes:
        id: Unique identifier (UUID)
        application_id: FK to the application
        user_id: FK to the member user
        role: Role of the user (owner, editor, viewer)
        invitation_id: FK to the invitation that created this membership (optional)
        created_at: Timestamp when membership was created
        updated_at: Timestamp when membership was last updated
    """

    __tablename__ = "ApplicationMembers"
    __allow_unmapped__ = True

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
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invitation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Invitations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Membership details
    role = Column(
        String(50),
        nullable=False,
        index=True,
    )
    is_manager = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    application = relationship(
        "Application",
        back_populates="members",
        lazy="joined",
    )
    user = relationship(
        "User",
        back_populates="memberships",
        lazy="joined",
    )
    invitation = relationship(
        "Invitation",
        back_populates="membership",
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of ApplicationMember."""
        return f"<ApplicationMember(id={self.id}, application_id={self.application_id}, user_id={self.user_id}, role={self.role})>"
