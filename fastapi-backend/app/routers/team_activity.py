"""Team Activity API router.

Provides endpoints for team-level activity dashboards:
overview KPIs, member breakdowns, project breakdowns, activity feed, and export.
All endpoints are scoped to applications owned by the authenticated user.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from ..database import get_db
from ..models.user import User
from ..schemas.team_activity import (
    MemberDetailResponse,
    MembersSummaryResponse,
    OverviewResponse,
    ProjectDetailResponse,
    ProjectsSummaryResponse,
)
from ..services import team_activity_service as svc
from ..services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/team-activity", tags=["team-activity"])

# Maximum date range allowed for export (365 days)
_MAX_EXPORT_DAYS = 365

def _is_statement_timeout(exc: OperationalError) -> bool:
    """Check if an OperationalError is a PostgreSQL statement timeout (pgcode 57014)."""
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    return pgcode == "57014"


# ============================================================================
# Shared dependency
# ============================================================================


async def require_app_owner(
    application_id: str = Query("all"),
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[list[UUID], list[UUID], date, date]:
    """Resolve owned application IDs and scoped project IDs.

    Returns:
        Tuple of (app_ids, project_ids, date_from, date_to).

    Raises:
        HTTPException 403 if user owns no applications.
        HTTPException 400 if date_from > date_to.
    """
    if date_from > date_to:
        raise HTTPException(400, "date_from must be <= date_to")

    # Get all apps owned by this user
    all_app_ids = await svc.get_owned_app_ids(db, current_user.id)
    if not all_app_ids:
        raise HTTPException(403, "You do not own any applications.")

    # Filter to a specific application if requested
    if application_id != "all":
        try:
            target_id = UUID(application_id)
        except ValueError:
            raise HTTPException(400, "Invalid application_id format.")
        if target_id not in all_app_ids:
            raise HTTPException(403, "You do not own this application.")
        app_ids = [target_id]
    else:
        app_ids = all_app_ids

    # Resolve project IDs
    project_ids = await svc.get_project_ids_for_apps(db, app_ids, date_from, date_to)

    return app_ids, project_ids, date_from, date_to


# Type alias for the dependency
AppOwnerDep = Annotated[
    tuple[list[UUID], list[UUID], date, date],
    Depends(require_app_owner),
]


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    response: Response,
    scope: AppOwnerDep,
    db: AsyncSession = Depends(get_db),
) -> OverviewResponse:
    """Get overview KPIs, completion trend, and breakdowns."""
    app_ids, project_ids, date_from, date_to = scope
    response.headers["Cache-Control"] = "no-store, no-cache"

    # Build a stable cache key from sorted app IDs
    app_id_key = ",".join(sorted(str(a) for a in app_ids))

    try:
        return await asyncio.wait_for(
            svc.get_overview_cached(db, app_id_key, project_ids, date_from, date_to),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Query timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Query timed out. Try a shorter date range.")
        raise


@router.get("/members", response_model=MembersSummaryResponse)
async def get_members(
    response: Response,
    scope: AppOwnerDep,
    db: AsyncSession = Depends(get_db),
) -> MembersSummaryResponse:
    """Get member summary table."""
    app_ids, project_ids, date_from, date_to = scope
    response.headers["Cache-Control"] = "no-store, no-cache"

    try:
        return await asyncio.wait_for(
            svc.get_members_summary(db, app_ids, project_ids, date_from, date_to),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Query timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Query timed out. Try a shorter date range.")
        raise


@router.get("/members/{user_id}", response_model=MemberDetailResponse)
async def get_member_detail(
    user_id: str,
    response: Response,
    scope: AppOwnerDep,
    db: AsyncSession = Depends(get_db),
) -> MemberDetailResponse:
    """Get detailed task/doc breakdown for a single member."""
    app_ids, project_ids, date_from, date_to = scope
    response.headers["Cache-Control"] = "no-store, no-cache"

    try:
        member_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user_id format.")

    try:
        return await asyncio.wait_for(
            svc.get_member_detail(db, member_uuid, app_ids, project_ids, date_from, date_to),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Query timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Query timed out. Try a shorter date range.")
        raise


@router.get("/projects", response_model=ProjectsSummaryResponse)
async def get_projects(
    response: Response,
    scope: AppOwnerDep,
    db: AsyncSession = Depends(get_db),
) -> ProjectsSummaryResponse:
    """Get project summary table."""
    app_ids, _, date_from, date_to = scope
    response.headers["Cache-Control"] = "no-store, no-cache"

    try:
        return await asyncio.wait_for(
            svc.get_projects_summary(db, app_ids, date_from, date_to),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Query timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Query timed out. Try a shorter date range.")
        raise


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project_detail(
    project_id: str,
    response: Response,
    scope: AppOwnerDep,
    db: AsyncSession = Depends(get_db),
) -> ProjectDetailResponse:
    """Get member breakdown + task list for a single project."""
    app_ids, project_ids, date_from, date_to = scope
    response.headers["Cache-Control"] = "no-store, no-cache"

    try:
        proj_uuid = UUID(project_id)
    except ValueError:
        raise HTTPException(400, "Invalid project_id format.")

    # Verify this project belongs to owned apps (check ALL projects, not just
    # date-filtered ones — the date filter scopes data, not authorization)
    all_owned_project_ids = await svc.get_all_project_ids_for_apps(db, app_ids)
    if proj_uuid not in all_owned_project_ids:
        raise HTTPException(403, "Project not accessible.")

    try:
        return await asyncio.wait_for(
            svc.get_project_detail(db, proj_uuid, date_from, date_to),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Query timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Query timed out. Try a shorter date range.")
        raise


@router.get("/export")
async def export_data(
    scope: AppOwnerDep,
    current_user: User = Depends(get_current_user),
    tab: str = Query("all", pattern="^(overview|members|projects|all)$"),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Export team activity data as an Excel file.

    Validates max 365-day range before generating.
    """
    app_ids, project_ids, date_from, date_to = scope

    # Validate date range
    day_span = (date_to - date_from).days
    if day_span > _MAX_EXPORT_DAYS:
        raise HTTPException(
            400,
            f"Export date range cannot exceed {_MAX_EXPORT_DAYS} days. "
            f"Requested: {day_span} days.",
        )

    try:
        path = await asyncio.wait_for(
            svc.generate_export(
                db,
                app_ids,
                project_ids,
                current_user.id,
                date_from,
                date_to,
                tab,
            ),
            timeout=30.0,  # Export can take longer
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "Export timed out. Try a shorter date range.")
    except OperationalError as exc:
        if _is_statement_timeout(exc):
            raise HTTPException(504, "Export timed out. Try a shorter date range.")
        raise

    filename = f"team_activity_{date_from}_{date_to}.xlsx"
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(os.unlink, str(path)),
    )
