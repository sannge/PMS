"""Dashboard API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..schemas.dashboard import DashboardResponse
from ..services.auth_service import get_current_user
from ..services.dashboard_service import get_dashboard_data

router = APIRouter(tags=["dashboard"])


@router.get("/api/me/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Get aggregated dashboard data for the current user."""
    response.headers["Cache-Control"] = "no-store, no-cache"
    return await get_dashboard_data(db, current_user.id)
