"""Team Activity response schemas."""

from pydantic import BaseModel

# ============================================================================
# Overview tab
# ============================================================================


class KPICards(BaseModel):
    completed: int
    in_progress: int
    in_review: int
    overdue: int
    total_story_points: int


class WeeklyCompletion(BaseModel):
    week: str  # ISO date of Monday
    count: int


class ProjectBreakdown(BaseModel):
    project_id: str
    project_name: str
    project_key: str
    completed: int
    in_progress: int
    in_review: int
    overdue: int
    todo: int


class MemberBreakdown(BaseModel):
    user_id: str
    display_name: str
    email: str
    completed: int
    in_progress: int


class OverviewResponse(BaseModel):
    kpi: KPICards
    completion_trend: list[WeeklyCompletion]
    by_project: list[ProjectBreakdown]
    by_member: list[MemberBreakdown]


# ============================================================================
# Members tab (summary + lazy-loaded detail)
# ============================================================================


class MemberSummary(BaseModel):
    user_id: str
    display_name: str
    email: str
    avatar_url: str | None
    role: str
    done_count: int
    in_progress_count: int
    in_review_count: int
    story_points_sum: int
    docs_count: int
    comments_count: int


class MembersSummaryResponse(BaseModel):
    members: list[MemberSummary]


class MemberTaskDetail(BaseModel):
    task_id: str
    task_key: str
    title: str
    project_name: str
    project_key: str
    status_name: str
    status_category: str
    priority: str
    story_points: int | None
    completed_at: str | None
    created_at: str


class MemberDocDetail(BaseModel):
    document_id: str
    title: str
    scope: str
    scope_name: str
    created_at: str
    updated_at: str


class MemberDetailResponse(BaseModel):
    user_id: str
    tasks: list[MemberTaskDetail]
    documents: list[MemberDocDetail]
    comments_count: int


# ============================================================================
# Projects tab (summary + lazy-loaded detail)
# ============================================================================


class ProjectSummary(BaseModel):
    project_id: str
    project_name: str
    project_key: str
    application_name: str
    due_date: str | None
    total: int
    done: int
    in_progress: int
    in_review: int
    issue: int
    todo: int
    archived: int
    unassigned: int
    is_archived: bool
    archived_at: str | None
    members: list[str]  # display names
    progress_pct: float


class ProjectsSummaryResponse(BaseModel):
    projects: list[ProjectSummary]


class ProjectMemberBreakdown(BaseModel):
    user_id: str
    display_name: str
    done: int
    in_progress: int
    in_review: int
    issue: int
    todo: int
    story_points: int


class ProjectTaskRow(BaseModel):
    task_id: str
    task_key: str
    title: str
    status_name: str
    status_category: str
    priority: str
    assignee_name: str | None
    completed_at: str | None
    is_archived: bool


class ProjectDetailResponse(BaseModel):
    project_id: str
    member_breakdown: list[ProjectMemberBreakdown]
    tasks: list[ProjectTaskRow]


