"""
Status derivation service for computing project status from task aggregations.

This module provides pure functions for deterministic project status derivation
based on task distribution across status categories. The core principle is that
project status is derived from task reality, not manually set.

Derivation Priority Order: Done → Issue → In Progress → Todo
"""

from dataclasses import dataclass

from ..models.task_status import StatusCategory


@dataclass
class ProjectAggregation:
    """
    Aggregation counts for project status derivation.

    This dataclass holds the count of tasks in each category/status
    for efficient status derivation without requiring full table scans.

    Attributes:
        total_tasks: Total number of tasks in the project
        todo_tasks: Number of tasks in Todo status
        active_tasks: Number of tasks in Active category (In Progress)
        review_tasks: Number of tasks in In Review status
        issue_tasks: Number of tasks in Issue status
        done_tasks: Number of tasks in Done status
    """

    total_tasks: int
    todo_tasks: int
    active_tasks: int
    review_tasks: int
    issue_tasks: int
    done_tasks: int

    def __post_init__(self) -> None:
        """Validate that all counts are non-negative."""
        for field_name in [
            "total_tasks",
            "todo_tasks",
            "active_tasks",
            "review_tasks",
            "issue_tasks",
            "done_tasks",
        ]:
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative: {value}")

    @classmethod
    def empty(cls) -> "ProjectAggregation":
        """Create an empty aggregation with all counts at zero."""
        return cls(
            total_tasks=0,
            todo_tasks=0,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=0,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectAggregation":
        """
        Create a ProjectAggregation from a dictionary.

        Args:
            data: Dictionary with aggregation counts

        Returns:
            ProjectAggregation instance
        """
        return cls(
            total_tasks=data.get("total_tasks", 0),
            todo_tasks=data.get("todo_tasks", 0),
            active_tasks=data.get("active_tasks", 0),
            review_tasks=data.get("review_tasks", 0),
            issue_tasks=data.get("issue_tasks", 0),
            done_tasks=data.get("done_tasks", 0),
        )


def derive_project_status(agg: ProjectAggregation) -> str:
    """
    Derive project status from task aggregation counts.

    This is a pure function with no side effects. It deterministically
    computes the project status based on the distribution of tasks
    across different status categories.

    Derivation Rules (in priority order):
    1. No tasks = Todo (empty project)
    2. All done = Done (project complete)
    3. Any issue = Issue (issue escalation - visibility priority)
    4. Any active work = In Progress (work is happening)
    5. Default = Todo (only todo tasks remaining)

    Args:
        agg: ProjectAggregation containing task counts by status

    Returns:
        Derived project status string: "Todo", "In Progress", "Issue", or "Done"

    Examples:
        >>> derive_project_status(ProjectAggregation(0, 0, 0, 0, 0, 0))
        'Todo'
        >>> derive_project_status(ProjectAggregation(5, 0, 0, 0, 0, 5))
        'Done'
        >>> derive_project_status(ProjectAggregation(5, 3, 1, 0, 1, 0))
        'Issue'
        >>> derive_project_status(ProjectAggregation(5, 3, 2, 0, 0, 0))
        'In Progress'
    """
    # Rule 1: No tasks = Todo (empty project defaults to Todo)
    if agg.total_tasks == 0:
        return StatusCategory.TODO.value

    # Rule 2: All tasks done = Done (project is complete)
    if agg.done_tasks == agg.total_tasks:
        return StatusCategory.DONE.value

    # Rule 3: Any issue = Issue (issue escalation has highest priority after Done)
    # This ensures issues are visible at the project level
    if agg.issue_tasks > 0:
        return StatusCategory.ISSUE.value

    # Rule 4: Any active work = In Progress (includes both in_progress and in_review)
    # review_tasks are also considered active work
    if agg.active_tasks > 0 or agg.review_tasks > 0:
        return "In Progress"

    # Rule 5: Default = Todo (only todo tasks, or mixed with done)
    return StatusCategory.TODO.value


def derive_project_status_from_model(agg_model) -> str:
    """
    Derive project status from a ProjectTaskStatusAgg model instance.

    This is a convenience function that converts a SQLAlchemy model
    to a ProjectAggregation and derives the status.

    Args:
        agg_model: ProjectTaskStatusAgg model instance

    Returns:
        Derived project status string
    """
    if agg_model is None:
        return StatusCategory.TODO.value

    project_agg = ProjectAggregation(
        total_tasks=agg_model.total_tasks or 0,
        todo_tasks=agg_model.todo_tasks or 0,
        active_tasks=agg_model.active_tasks or 0,
        review_tasks=agg_model.review_tasks or 0,
        issue_tasks=agg_model.issue_tasks or 0,
        done_tasks=agg_model.done_tasks or 0,
    )

    return derive_project_status(project_agg)


# Re-export StatusCategory for convenience
__all__ = [
    "StatusCategory",
    "ProjectAggregation",
    "derive_project_status",
    "derive_project_status_from_model",
]
