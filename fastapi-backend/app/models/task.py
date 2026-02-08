"""Task SQLAlchemy model for issue/task tracking."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .attachment import Attachment
    from .checklist import Checklist
    from .comment import Comment
    from .project import Project
    from .task_status import TaskStatus
    from .user import User


class Task(Base):
    """
    Task model representing issues/tasks within a project.

    Tasks are the lowest level of the hierarchy: Application > Projects > Tasks
    Tasks support Jira-like features including types, statuses, priorities,
    assignees, reporters, and parent-child relationships (subtasks).

    Attributes:
        id: Unique identifier (UUID)
        project_id: FK to parent project
        task_status_id: FK to TaskStatuses table (new unified status system)
        task_key: Unique task key (e.g., "PROJ-123")
        title: Task title/summary
        description: Detailed task description
        task_type: Type of task (story, bug, epic, subtask)
        priority: Priority level (lowest, low, medium, high, highest)
        assignee_id: FK to assigned user
        reporter_id: FK to reporting user
        parent_id: FK to parent task (for subtasks)
        sprint_id: FK to sprint (for future use)
        story_points: Story point estimate
        due_date: Task due date
        task_rank: Lexorank string for ordering tasks within a status column
        row_version: Version for optimistic concurrency control
        checklist_total: Total checklist items across all checklists
        checklist_done: Completed checklist items
        created_at: Timestamp when task was created
        updated_at: Timestamp when task was last updated
    """

    __tablename__ = "Tasks"
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
    assignee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reporter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sprint_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    task_status_id = Column(
        UUID(as_uuid=True),
        ForeignKey("TaskStatuses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Task identification
    task_key = Column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
    )

    # Task details
    title = Column(
        String(500),
        nullable=False,
    )
    description = Column(
        Text,
        nullable=True,
    )
    task_type = Column(
        String(50),
        nullable=False,
        default="story",
    )
    priority = Column(
        String(20),
        nullable=False,
        default="medium",
    )

    # Estimation and planning
    story_points = Column(
        Integer,
        nullable=True,
    )
    due_date = Column(
        Date,
        nullable=True,
    )

    # Ordering and concurrency
    task_rank = Column(
        String(50),
        nullable=True,
    )
    row_version = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # Denormalized checklist counts for efficient display on task cards
    checklist_total = Column(
        Integer,
        nullable=False,
        default=0,
    )
    checklist_done = Column(
        Integer,
        nullable=False,
        default=0,
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
    completed_at = Column(
        DateTime,
        nullable=True,
    )
    archived_at = Column(
        DateTime,
        nullable=True,
        # Index created via Alembic migration: ix_Tasks_archived_at
    )

    # Relationships
    project = relationship(
        "Project",
        back_populates="tasks",
        lazy="joined",
    )
    task_status = relationship(
        "TaskStatus",
        back_populates="tasks",
        lazy="joined",
    )
    assignee = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tasks",
        lazy="joined",
    )
    reporter = relationship(
        "User",
        foreign_keys=[reporter_id],
        back_populates="reported_tasks",
        lazy="joined",
    )
    parent = relationship(
        "Task",
        remote_side=[id],
        back_populates="subtasks",
        lazy="joined",
    )
    subtasks = relationship(
        "Task",
        back_populates="parent",
        lazy="dynamic",
    )
    attachments = relationship(
        "Attachment",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    comments = relationship(
        "Comment",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    checklists = relationship(
        "Checklist",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        """String representation of Task."""
        return f"<Task(id={self.id}, key={self.task_key}, title={self.title[:30]})>"
