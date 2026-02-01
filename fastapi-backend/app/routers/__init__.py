"""API routers package.

This package contains all FastAPI routers for the application.
Each router handles a specific domain of the API.
"""

from .application_members import router as application_members_router
from .applications import router as applications_router
from .auth import router as auth_router
from .checklists import router as checklists_router
from .comments import router as comments_router
from .document_folders import router as document_folders_router
from .document_tags import router as document_tags_router
from .documents import router as documents_router
from .files import router as files_router
from .invitations import router as invitations_router

from .notifications import router as notifications_router
from .project_assignments import router as project_assignments_router
from .project_members import router as project_members_router
from .projects import router as projects_router
from .tasks import router as tasks_router
from .users import router as users_router

__all__ = [
    "application_members_router",
    "applications_router",
    "auth_router",
    "checklists_router",
    "comments_router",
    "document_folders_router",
    "document_tags_router",
    "documents_router",
    "files_router",
    "invitations_router",

    "notifications_router",
    "project_assignments_router",
    "project_members_router",
    "projects_router",
    "tasks_router",
    "users_router",
]
