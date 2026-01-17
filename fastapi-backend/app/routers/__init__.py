"""API routers package.

This package contains all FastAPI routers for the application.
Each router handles a specific domain of the API.
"""

from .auth import router as auth_router

__all__ = [
    "auth_router",
]
