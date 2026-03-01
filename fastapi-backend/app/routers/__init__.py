"""API routers package.

This package contains all FastAPI routers for the application.
Each router handles a specific domain of the API.
"""

from .ai_chat import router as ai_chat_router
from .ai_config import router as ai_config_router
from .ai_import import router as ai_import_router
from .ai_oauth import router as ai_oauth_router
from .ai_query import router as ai_query_router
from .application_members import router as application_members_router
from .applications import router as applications_router
from .auth import router as auth_router
from .checklists import router as checklists_router
from .comments import router as comments_router
from .dashboard import router as dashboard_router
from .document_folders import router as document_folders_router
from .document_tags import router as document_tags_router
from .document_locks import router as document_locks_router
from .document_search import router as document_search_router
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
    "ai_chat_router",
    "ai_config_router",
    "ai_import_router",
    "ai_oauth_router",
    "ai_query_router",
    "application_members_router",
    "applications_router",
    "auth_router",
    "checklists_router",
    "comments_router",
    "dashboard_router",
    "document_folders_router",
    "document_tags_router",
    "document_locks_router",
    "document_search_router",
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
