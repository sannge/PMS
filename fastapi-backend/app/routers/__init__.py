"""API routers package.

This package contains all FastAPI routers for the application.
Each router handles a specific domain of the API.
"""

from .applications import router as applications_router
from .auth import router as auth_router
from .files import router as files_router
from .notes import router as notes_router
from .projects import router as projects_router
from .tasks import router as tasks_router

__all__ = [
    "applications_router",
    "auth_router",
    "files_router",
    "notes_router",
    "projects_router",
    "tasks_router",
]
