"""Dashboard response schemas."""

from pydantic import BaseModel


class TaskStatusBreakdown(BaseModel):
    todo: int = 0
    in_progress: int = 0
    in_review: int = 0
    issue: int = 0
    done: int = 0


class ProjectHealthItem(BaseModel):
    id: str
    name: str
    key: str
    application_id: str
    application_name: str
    derived_status: str | None
    due_date: str | None = None
    total_tasks: int
    done_tasks: int
    issue_tasks: int
    review_tasks: int = 0
    active_tasks: int
    completion_pct: int  # 0-100


class UpcomingTaskItem(BaseModel):
    id: str
    task_key: str
    title: str
    priority: str
    due_date: str | None
    status_name: str
    status_category: str
    project_id: str
    project_name: str
    project_key: str
    application_id: str
    application_name: str


class CompletionDataPoint(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class TrendData(BaseModel):
    value: int  # absolute percentage change
    is_positive: bool


class DashboardResponse(BaseModel):
    # Stat cards
    applications_count: int
    projects_count: int
    active_tasks_count: int  # Tasks assigned to current user in Active/Issue status
    completed_this_week: int
    overdue_tasks_count: int  # All overdue tasks in accessible projects (team-wide)

    # Trends (current 30d vs prior 30d)
    active_tasks_trend: TrendData | None  # Approximate: based on task creation date, not historical snapshots
    completed_trend: TrendData | None

    # Charts
    task_status_breakdown: TaskStatusBreakdown  # Aggregated across all accessible projects
    project_health: list[ProjectHealthItem]  # Top 10 by updated_at
    completion_trend: list[CompletionDataPoint]  # Last 14 days

    # Actionable lists
    overdue_tasks: list[UpcomingTaskItem]  # Past due, not done (limit 5)
    upcoming_tasks: list[UpcomingTaskItem]  # Due within 14 days (limit 10)
    recently_completed: list[UpcomingTaskItem]  # Completed last 7 days (limit 5)

    generated_at: str  # ISO timestamp
