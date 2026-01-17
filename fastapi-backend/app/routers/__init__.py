"""API routers package.

This package contains all FastAPI routers for the application.
Each router handles a specific domain of the API.
"""

from .applications import router as applications_router
from .auth import router as auth_router

__all__ = [
    "applications_router",
    "auth_router",
]
