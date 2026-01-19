"""ProjectTaskStatusAgg SQLAlchemy model for incremental status aggregation."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .project import Project


class ProjectTaskStatusAgg(Base):
    """
    ProjectTaskStatusAgg model for tracking task status counts per project.

    This table maintains incremental counters for task status derivation,
    avoiding expensive full table scans when computing project status.
    The counters are updated on every task create/update/delete operation.

    Attributes:
        project_id: PK and FK to Projects table (one aggregation row per project)
        total_tasks: Total number of tasks in the project
        todo_tasks: Count of tasks in Todo status
        active_tasks: Count of tasks in In Progress status
        review_tasks: Count of tasks in In Review status
        issue_tasks: Count of tasks in Issue status
        done_tasks: Count of tasks in Done status
        updated_at: Timestamp of last aggregation update
    """

    __tablename__ = "ProjectTaskStatusAgg"
    __allow_unmapped__ = True

    # Primary key is also foreign key to Projects
    project_id = Column(
        UNIQUEIDENTIFIER,
        ForeignKey("Projects.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    # Task count aggregations by status category
    total_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )
    todo_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )
    active_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )
    review_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )
    issue_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )
    done_tasks = Column(
        Integer,
        nullable=False,
        default=0,
    )

    # Timestamp
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    project = relationship(
        "Project",
        back_populates="task_status_agg",
        lazy="select",
    )

    def __repr__(self) -> str:
        """String representation of ProjectTaskStatusAgg."""
        return (
            f"<ProjectTaskStatusAgg("
            f"project_id={self.project_id}, "
            f"total={self.total_tasks}, "
            f"todo={self.todo_tasks}, "
            f"active={self.active_tasks}, "
            f"review={self.review_tasks}, "
            f"issue={self.issue_tasks}, "
            f"done={self.done_tasks})>"
        )

    def reset_counts(self) -> None:
        """Reset all counters to zero."""
        self.total_tasks = 0
        self.todo_tasks = 0
        self.active_tasks = 0
        self.review_tasks = 0
        self.issue_tasks = 0
        self.done_tasks = 0
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Convert aggregation to dictionary for status derivation."""
        return {
            "total_tasks": self.total_tasks,
            "todo_tasks": self.todo_tasks,
            "active_tasks": self.active_tasks,
            "review_tasks": self.review_tasks,
            "issue_tasks": self.issue_tasks,
            "done_tasks": self.done_tasks,
        }
