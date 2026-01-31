"""User SQLAlchemy model for authentication and user management."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .application import Application
    from .application_member import ApplicationMember
    from .attachment import Attachment
    from .invitation import Invitation
    from .note import Note
    from .notification import Notification
    from .project_assignment import ProjectAssignment
    from .task import Task


class User(Base):
    """
    User model representing application users.

    Attributes:
        id: Unique identifier (UUID)
        email: User's email address (unique)
        password_hash: Hashed password for authentication
        display_name: User's display name
        avatar_url: URL to user's avatar image
        created_at: Timestamp when user was created
        updated_at: Timestamp when user was last updated
    """

    __tablename__ = "Users"
    __allow_unmapped__ = True

    # Primary key - UUID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Authentication fields
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash = Column(
        String(255),
        nullable=False,
    )

    # Profile fields
    display_name = Column(
        String(100),
        nullable=True,
    )
    avatar_url = Column(
        String(500),
        nullable=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    owned_applications = relationship(
        "Application",
        back_populates="owner",
        lazy="dynamic",
    )
    assigned_tasks = relationship(
        "Task",
        foreign_keys="Task.assignee_id",
        back_populates="assignee",
        lazy="dynamic",
    )
    reported_tasks = relationship(
        "Task",
        foreign_keys="Task.reporter_id",
        back_populates="reporter",
        lazy="dynamic",
    )
    created_notes = relationship(
        "Note",
        back_populates="creator",
        lazy="dynamic",
    )
    uploaded_attachments = relationship(
        "Attachment",
        back_populates="uploader",
        lazy="dynamic",
    )
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    memberships = relationship(
        "ApplicationMember",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    sent_invitations = relationship(
        "Invitation",
        foreign_keys="Invitation.inviter_id",
        back_populates="inviter",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    received_invitations = relationship(
        "Invitation",
        foreign_keys="Invitation.invitee_id",
        back_populates="invitee",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    project_assignments = relationship(
        "ProjectAssignment",
        foreign_keys="ProjectAssignment.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, email={self.email})>"
