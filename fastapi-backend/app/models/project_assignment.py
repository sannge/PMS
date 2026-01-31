"""ProjectAssignment SQLAlchemy model for project-user assignments."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .project import Project
    from .user import User


class ProjectAssignment(Base):
    """
    ProjectAssignment model representing user assignments to projects.

    ProjectAssignments track which users are assigned to work on specific
    projects within an application. Only owners and editors can be assigned
    to projects (not viewers).

    Attributes:
        id: Unique identifier (UUID)
        project_id: FK to the project
        user_id: FK to the assigned user
        assigned_by: FK to the user who made the assignment
        created_at: Timestamp when assignment was created
    """

    __tablename__ = "ProjectAssignments"
    __allow_unmapped__ = True

    # Primary key - UUID
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Foreign keys
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    # Relationships
    project = relationship(
        "Project",
        back_populates="assignments",
        lazy="joined",
    )
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="project_assignments",
        lazy="joined",
    )
    assigner = relationship(
        "User",
        foreign_keys=[assigned_by],
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of ProjectAssignment."""
        return f"<ProjectAssignment(id={self.id}, project_id={self.project_id}, user_id={self.user_id})>"
