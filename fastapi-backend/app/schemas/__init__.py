"""Pydantic schemas package for request/response validation."""

from .application import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    ApplicationWithProjects,
)
from .project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ProjectWithTasks,
)
from .project_member import (
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectMemberWithUser,
)
from .task import (
    TaskCreate,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskType,
    TaskUpdate,
    TaskWithSubtasks,
)
from .user import (
    UserCreate,
    UserInDB,
    UserResponse,
    UserUpdate,
)

__all__ = [
    # Application schemas
    "ApplicationCreate",
    "ApplicationResponse",
    "ApplicationUpdate",
    "ApplicationWithProjects",
    # Project schemas
    "ProjectCreate",
    "ProjectResponse",
    "ProjectUpdate",
    "ProjectWithTasks",
    # Project member schemas
    "ProjectMemberCreate",
    "ProjectMemberResponse",
    "ProjectMemberUpdate",
    "ProjectMemberWithUser",
    # Task schemas
    "TaskCreate",
    "TaskPriority",
    "TaskResponse",
    "TaskStatus",
    "TaskType",
    "TaskUpdate",
    "TaskWithSubtasks",
    # User schemas
    "UserCreate",
    "UserInDB",
    "UserResponse",
    "UserUpdate",
]
