"""Dashboard aggregation service."""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_task_status_agg import ProjectTaskStatusAgg
from ..models.task import Task
from ..models.task_status import TaskStatus
from ..schemas.dashboard import (
    CompletionDataPoint,
    DashboardResponse,
    ProjectHealthItem,
    TaskStatusBreakdown,
    TrendData,
    UpcomingTaskItem,
)
from ..utils.timezone import CENTRAL_TZ, central_now, utc_now

logger = logging.getLogger(__name__)

# Redis cache TTL for dashboard data (seconds)
_DASHBOARD_CACHE_TTL = 60


def _build_accessible_app_ids(user_id: UUID):
    """Build subquery for application IDs the user can access."""
    owned_apps = select(Application.id.label("app_id")).where(Application.owner_id == user_id)
    member_apps = select(ApplicationMember.application_id.label("app_id")).where(ApplicationMember.user_id == user_id)
    return owned_apps.union(member_apps).subquery()


async def _query_stats(
    db: AsyncSession,
    project_id_list: list[UUID],
    user_id: UUID,
    today: date,
    week_start: date,
) -> tuple[int, int, int, TaskStatusBreakdown, dict[date, int]]:
    """Query task stats, status breakdown, and completion trend data."""
    # Active tasks: assigned to user, in Active or Issue category, not archived
    active_tasks_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.assignee_id == user_id,
            Task.archived_at.is_(None),
            TaskStatus.category.in_(["Active", "Issue"]),
        )
    )
    active_tasks_count = active_tasks_result.scalar() or 0

    # Completed this week: tasks with completed_at >= week_start in accessible projects
    # Convert Central Time week_start to UTC for DB comparison
    week_start_utc = datetime.combine(week_start, datetime.min.time(), tzinfo=CENTRAL_TZ).astimezone(timezone.utc)
    completed_week_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.completed_at >= week_start_utc,
            Task.archived_at.is_(None),
            TaskStatus.category == "Done",
        )
    )
    completed_this_week = completed_week_result.scalar() or 0

    # Overdue tasks: due_date < today, status != Done, not archived
    overdue_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.due_date < today,
            Task.archived_at.is_(None),
            TaskStatus.category != "Done",
        )
    )
    overdue_count = overdue_result.scalar() or 0

    # Task status breakdown from ProjectTaskStatusAgg
    breakdown_result = await db.execute(
        select(
            func.coalesce(func.sum(ProjectTaskStatusAgg.todo_tasks), 0).label("todo"),
            func.coalesce(func.sum(ProjectTaskStatusAgg.active_tasks), 0).label("active"),
            func.coalesce(func.sum(ProjectTaskStatusAgg.review_tasks), 0).label("review"),
            func.coalesce(func.sum(ProjectTaskStatusAgg.issue_tasks), 0).label("issue"),
            func.coalesce(func.sum(ProjectTaskStatusAgg.done_tasks), 0).label("done"),
        ).where(
            ProjectTaskStatusAgg.project_id.in_(project_id_list),
        )
    )
    row = breakdown_result.one()
    breakdown = TaskStatusBreakdown(
        todo=row.todo,
        in_progress=row.active,
        in_review=row.review,
        issue=row.issue,
        done=row.done,
    )

    # Completion trend: last 14 days grouped by date
    # Convert Central Time boundary to UTC for DB comparison
    fourteen_days_ago = datetime.combine(today - timedelta(days=13), datetime.min.time(), tzinfo=CENTRAL_TZ).astimezone(
        timezone.utc
    )
    # Group by Central Time date (not UTC) so day boundaries match user expectations
    central_date_expr = func.date(func.timezone("America/Chicago", Task.completed_at))
    completion_trend_result = await db.execute(
        select(
            central_date_expr.label("completion_date"),
            func.count(Task.id).label("cnt"),
        )
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.completed_at >= fourteen_days_ago,
            Task.archived_at.is_(None),
            TaskStatus.category == "Done",
        )
        .group_by(central_date_expr)
    )
    completion_data: dict[date, int] = {}
    for crow in completion_trend_result.all():
        # Fix 4: func.date() may return str from PostgreSQL, parse to date object
        key = (
            crow.completion_date
            if isinstance(crow.completion_date, date)
            else date.fromisoformat(str(crow.completion_date))
        )
        completion_data[key] = crow.cnt

    return (
        active_tasks_count,
        completed_this_week,
        overdue_count,
        breakdown,
        completion_data,
    )


async def _query_project_health(
    db: AsyncSession,
    app_id_list: list[UUID],
) -> list[ProjectHealthItem]:
    """Query top 10 projects by updated_at with health info."""
    result = await db.execute(
        select(
            Project.id,
            Project.name,
            Project.key,
            Project.application_id,
            Application.name.label("application_name"),
            Project.due_date,
            Project.updated_at,
            TaskStatus.name.label("derived_status_name"),
            func.coalesce(ProjectTaskStatusAgg.total_tasks, 0).label("total_tasks"),
            func.coalesce(ProjectTaskStatusAgg.done_tasks, 0).label("done_tasks"),
            func.coalesce(ProjectTaskStatusAgg.issue_tasks, 0).label("issue_tasks"),
            func.coalesce(ProjectTaskStatusAgg.review_tasks, 0).label("review_tasks"),
            func.coalesce(ProjectTaskStatusAgg.active_tasks, 0).label("active_tasks"),
        )
        .join(Application, Project.application_id == Application.id)
        .outerjoin(
            ProjectTaskStatusAgg,
            Project.id == ProjectTaskStatusAgg.project_id,
        )
        .outerjoin(TaskStatus, Project.derived_status_id == TaskStatus.id)
        .where(
            Project.application_id.in_(app_id_list),
            Project.archived_at.is_(None),
        )
        .order_by(Project.updated_at.desc())
        .limit(10)
    )
    rows = result.all()

    items: list[ProjectHealthItem] = []
    for r in rows:
        total = r.total_tasks
        done = r.done_tasks
        pct = (done * 100) // total if total > 0 else 0
        items.append(
            ProjectHealthItem(
                id=str(r.id),
                name=r.name,
                key=r.key,
                application_id=str(r.application_id),
                application_name=r.application_name,
                derived_status=r.derived_status_name,
                due_date=r.due_date.isoformat() if r.due_date else None,
                total_tasks=total,
                done_tasks=done,
                issue_tasks=r.issue_tasks,
                review_tasks=r.review_tasks,
                active_tasks=r.active_tasks,
                completion_pct=pct,
            )
        )

    return items


async def _query_task_lists(
    db: AsyncSession,
    project_id_list: list[UUID],
    today: date,
    seven_days_ago: datetime,
) -> tuple[list[UpcomingTaskItem], list[UpcomingTaskItem], list[UpcomingTaskItem]]:
    """Query overdue, upcoming, and recently completed task lists."""

    def _task_to_item(row) -> UpcomingTaskItem:
        return UpcomingTaskItem(
            id=str(row.id),
            task_key=row.task_key,
            title=row.title,
            priority=row.priority,
            due_date=row.due_date.isoformat() if row.due_date else None,
            status_name=row.status_name,
            status_category=row.status_category,
            project_id=str(row.project_id),
            project_name=row.project_name,
            project_key=row.project_key,
            application_id=str(row.application_id),
            application_name=row.application_name,
        )

    base_columns = [
        Task.id,
        Task.task_key,
        Task.title,
        Task.priority,
        Task.due_date,
        TaskStatus.name.label("status_name"),
        TaskStatus.category.label("status_category"),
        Project.id.label("project_id"),
        Project.name.label("project_name"),
        Project.key.label("project_key"),
        Project.application_id,
        Application.name.label("application_name"),
    ]

    base_join = (
        select(*base_columns)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Project, Task.project_id == Project.id)
        .join(Application, Project.application_id == Application.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.archived_at.is_(None),
        )
    )

    # Overdue tasks: due_date < today AND category != Done
    overdue_result = await db.execute(
        base_join.where(
            Task.due_date < today,
            TaskStatus.category != "Done",
        )
        .order_by(Task.due_date.asc())
        .limit(5)
    )
    overdue_tasks = [_task_to_item(r) for r in overdue_result.all()]

    # Upcoming tasks: due within 14 days, not done
    upcoming_end = today + timedelta(days=14)
    upcoming_result = await db.execute(
        base_join.where(
            Task.due_date >= today,
            Task.due_date <= upcoming_end,
            TaskStatus.category != "Done",
        )
        .order_by(Task.due_date.asc())
        .limit(10)
    )
    upcoming_tasks = [_task_to_item(r) for r in upcoming_result.all()]

    # Recently completed: completed in last 7 days, must be Done category
    recently_result = await db.execute(
        base_join.where(
            Task.completed_at >= seven_days_ago,
            TaskStatus.category == "Done",
        )
        .order_by(Task.completed_at.desc())
        .limit(5)
    )
    recently_completed = [_task_to_item(r) for r in recently_result.all()]

    return overdue_tasks, upcoming_tasks, recently_completed


async def _query_trends(
    db: AsyncSession,
    project_id_list: list[UUID],
    now: datetime,
    thirty_days_ago: datetime,
    sixty_days_ago: datetime,
) -> tuple[TrendData | None, TrendData | None]:
    """Compute completed and active task trends (current 30d vs prior 30d)."""

    # Completed tasks: current 30 days
    current_completed_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.completed_at >= thirty_days_ago,
            Task.completed_at < now,
            Task.archived_at.is_(None),
            TaskStatus.category == "Done",
        )
    )
    current_completed = current_completed_result.scalar() or 0

    # Completed tasks: prior 30 days (30-60 days ago)
    prior_completed_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.completed_at >= sixty_days_ago,
            Task.completed_at < thirty_days_ago,
            Task.archived_at.is_(None),
            TaskStatus.category == "Done",
        )
    )
    prior_completed = prior_completed_result.scalar() or 0

    # Build completed trend
    if current_completed == 0 and prior_completed == 0:
        completed_trend = None
    elif prior_completed == 0:
        completed_trend = TrendData(value=100, is_positive=True)
    else:
        diff = current_completed - prior_completed
        if diff == 0:
            completed_trend = None
        else:
            pct = abs(diff * 100) // prior_completed
            completed_trend = TrendData(value=pct, is_positive=diff > 0)

    # Active tasks trend: current active count vs tasks created in prior 30d still active
    # Current active count
    current_active_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.archived_at.is_(None),
            TaskStatus.category.in_(["Active", "Issue"]),
        )
    )
    current_active = current_active_result.scalar() or 0

    # Approximate prior active: tasks created before 30d ago that were in active state
    # Use tasks created in prior 30d period that are still active as approximation
    prior_active_result = await db.execute(
        select(func.count(Task.id))
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .where(
            Task.project_id.in_(project_id_list),
            Task.archived_at.is_(None),
            Task.created_at >= sixty_days_ago,
            Task.created_at < thirty_days_ago,
            TaskStatus.category.in_(["Active", "Issue"]),
        )
    )
    prior_active = prior_active_result.scalar() or 0

    # Build active trend (more active tasks = negative, means more unfinished work)
    if current_active == 0 and prior_active == 0:
        active_trend = None
    elif prior_active == 0:
        active_trend = TrendData(value=100, is_positive=False)
    else:
        diff = current_active - prior_active
        if diff == 0:
            active_trend = None
        else:
            pct = abs(diff * 100) // prior_active
            active_trend = TrendData(value=pct, is_positive=diff < 0)

    return completed_trend, active_trend


def _build_completion_trend(
    completion_data: dict[date, int],
    today: date,
) -> list[CompletionDataPoint]:
    """Fill gaps in completion trend data to produce 14 entries."""
    points: list[CompletionDataPoint] = []
    for i in range(14):
        d = today - timedelta(days=13 - i)
        count = completion_data.get(d, 0)
        points.append(CompletionDataPoint(date=d.isoformat(), count=count))
    return points


async def get_dashboard_data(db: AsyncSession, user_id: UUID) -> DashboardResponse:
    """Aggregate all dashboard data using sequential queries on a single session.

    Results are cached in Redis for 60 seconds per user to reduce DB load.
    """
    from ..config import _app_env
    from .redis_service import redis_service

    cache_key = f"dashboard:{_app_env}:{user_id}"

    # Check Redis cache first
    if redis_service.is_connected:
        try:
            cached = await redis_service.get(cache_key)
            if cached:
                return DashboardResponse.model_validate_json(cached)
        except Exception:
            logger.debug("Dashboard cache miss or error for user %s", user_id)

    result = await _compute_dashboard_data(db, user_id)

    # Store in Redis cache (best-effort, don't fail the request)
    if redis_service.is_connected:
        try:
            await redis_service.set(
                cache_key,
                result.model_dump_json(),
                ttl=_DASHBOARD_CACHE_TTL,
            )
        except Exception:
            logger.debug("Failed to cache dashboard for user %s", user_id)

    return result


async def _compute_dashboard_data(db: AsyncSession, user_id: UUID) -> DashboardResponse:
    """Run all dashboard queries and build the response."""
    # Build accessible app IDs subquery
    all_app_ids = _build_accessible_app_ids(user_id)

    # Materialize accessible app IDs into a Python list (eliminates subquery re-evaluations)
    app_ids_result = await db.execute(select(all_app_ids.c.app_id))
    app_id_list: list[UUID] = [row[0] for row in app_ids_result.all()]

    # Use Central Time for business logic (what day is "today", week boundaries)
    now_central = central_now()
    today = now_central.date()
    # For DB queries, use timezone-aware UTC datetimes (columns are timestamptz)
    now = utc_now()

    # Early return for users with no accessible applications
    if not app_id_list:
        return DashboardResponse(
            applications_count=0,
            projects_count=0,
            active_tasks_count=0,
            completed_this_week=0,
            overdue_tasks_count=0,
            active_tasks_trend=None,
            completed_trend=None,
            task_status_breakdown=TaskStatusBreakdown(),
            project_health=[],
            completion_trend=_build_completion_trend({}, today),
            overdue_tasks=[],
            upcoming_tasks=[],
            recently_completed=[],
            generated_at=now_central.isoformat(),
        )

    # Materialize accessible non-archived project IDs
    accessible_projects = select(Project.id).where(
        Project.application_id.in_(app_id_list),
        Project.archived_at.is_(None),
    )
    project_ids_result = await db.execute(accessible_projects)
    project_id_list: list[UUID] = [row[0] for row in project_ids_result.all()]

    # Early return when user has apps but all projects are archived
    if not project_id_list:
        return DashboardResponse(
            applications_count=len(app_id_list),
            projects_count=0,
            active_tasks_count=0,
            completed_this_week=0,
            overdue_tasks_count=0,
            active_tasks_trend=None,
            completed_trend=None,
            task_status_breakdown=TaskStatusBreakdown(),
            project_health=[],
            completion_trend=_build_completion_trend({}, today),
            overdue_tasks=[],
            upcoming_tasks=[],
            recently_completed=[],
            generated_at=now_central.isoformat(),
        )

    week_start = today - timedelta(days=today.weekday())  # Monday
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Inline counts (no DB query needed)
    app_count = len(app_id_list)
    project_count = len(project_id_list)

    # Run all queries sequentially on the single injected session to avoid
    # opening extra pool connections.  11 queries at ~5ms each = ~55ms total,
    # well within the 200ms API read target.
    stats_result = await _query_stats(db, project_id_list, user_id, today, week_start)
    health_result = await _query_project_health(db, app_id_list)
    tasks_result = await _query_task_lists(db, project_id_list, today, seven_days_ago)
    trend_result = await _query_trends(db, project_id_list, now, thirty_days_ago, sixty_days_ago)

    # Unpack stats
    (
        active_tasks_count,
        completed_this_week,
        overdue_count,
        breakdown,
        completion_trend_data,
    ) = stats_result

    # Build completion trend (fill gaps)
    completion_trend = _build_completion_trend(completion_trend_data, today)

    # Unpack trends
    completed_trend, active_trend = trend_result

    # Unpack task lists
    overdue_tasks, upcoming_tasks, recently_completed = tasks_result

    return DashboardResponse(
        applications_count=app_count,
        projects_count=project_count,
        active_tasks_count=active_tasks_count,
        completed_this_week=completed_this_week,
        overdue_tasks_count=overdue_count,
        active_tasks_trend=active_trend,
        completed_trend=completed_trend,
        task_status_breakdown=breakdown,
        project_health=health_result,
        completion_trend=completion_trend,
        overdue_tasks=overdue_tasks,
        upcoming_tasks=upcoming_tasks,
        recently_completed=recently_completed,
        generated_at=now_central.isoformat(),
    )
