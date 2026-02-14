"""
Status derivation service for computing project status from task aggregations.

This module provides pure functions for deterministic project status derivation
based on task distribution across status categories. The core principle is that
project status is derived from task reality, not manually set.

Derivation Priority Order: Done → Issue → In Progress → Todo

This module also provides aggregation update functions to increment/decrement
counters when tasks are created, updated, or deleted. These ensure efficient
status derivation without requiring full table scans.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from ..models.task_status import StatusCategory, StatusName

if TYPE_CHECKING:
    from ..models.project_task_status_agg import ProjectTaskStatusAgg


# Mapping from status name to the corresponding counter field in ProjectTaskStatusAgg
STATUS_TO_COUNTER_FIELD = {
    StatusName.TODO.value: "todo_tasks",
    StatusName.IN_PROGRESS.value: "active_tasks",
    StatusName.IN_REVIEW.value: "review_tasks",
    StatusName.ISSUE.value: "issue_tasks",
    StatusName.DONE.value: "done_tasks",
}


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


def get_counter_field_for_status(status_name: str) -> str:
    """
    Get the counter field name for a given task status.

    Maps each of the 5 task statuses to the corresponding counter field
    in ProjectTaskStatusAgg:
    - "Todo" -> "todo_tasks"
    - "In Progress" -> "active_tasks"
    - "In Review" -> "review_tasks"
    - "Issue" -> "issue_tasks"
    - "Done" -> "done_tasks"

    Args:
        status_name: The task status name string

    Returns:
        The counter field name for the status

    Raises:
        ValueError: If status_name is not a valid status
    """
    counter_field = STATUS_TO_COUNTER_FIELD.get(status_name)
    if counter_field is None:
        raise ValueError(
            f"Invalid status name: '{status_name}'. "
            f"Must be one of: {list(STATUS_TO_COUNTER_FIELD.keys())}"
        )
    return counter_field


def update_aggregation_on_task_create(
    agg: "ProjectTaskStatusAgg",
    task_status_name: str,
) -> str:
    """
    Update aggregation counters when a task is created.

    Increments the appropriate status counter and total_tasks count.
    This is a mutating function that modifies the aggregation in place.

    Args:
        agg: The ProjectTaskStatusAgg model instance to update
        task_status_name: The status name of the created task

    Returns:
        The newly derived project status after the update

    Example:
        >>> agg = ProjectTaskStatusAgg(project_id=project_id)
        >>> new_status = update_aggregation_on_task_create(agg, "Todo")
        >>> # agg.total_tasks is now 1, agg.todo_tasks is now 1
    """
    counter_field = get_counter_field_for_status(task_status_name)

    # Increment the status-specific counter
    current_value = getattr(agg, counter_field) or 0
    setattr(agg, counter_field, current_value + 1)

    # Increment total tasks
    agg.total_tasks = (agg.total_tasks or 0) + 1

    # Update timestamp
    agg.updated_at = datetime.utcnow()

    # Return the new derived status
    return derive_project_status_from_model(agg)


def update_aggregation_on_task_status_change(
    agg: "ProjectTaskStatusAgg",
    old_status_name: str,
    new_status_name: str,
) -> str:
    """
    Update aggregation counters when a task's status changes.

    Decrements the old status counter and increments the new status counter.
    Total tasks count remains unchanged. This is a mutating function.

    Args:
        agg: The ProjectTaskStatusAgg model instance to update
        old_status_name: The previous status name of the task
        new_status_name: The new status name of the task

    Returns:
        The newly derived project status after the update

    Note:
        If old_status_name == new_status_name, no changes are made
        but the derived status is still computed and returned.

    Example:
        >>> agg = ProjectTaskStatusAgg(project_id=project_id, todo_tasks=5)
        >>> new_status = update_aggregation_on_task_status_change(
        ...     agg, "Todo", "In Progress"
        ... )
        >>> # agg.todo_tasks is now 4, agg.active_tasks is now 1
    """
    # If status hasn't changed, just return current derived status
    if old_status_name == new_status_name:
        return derive_project_status_from_model(agg)

    old_counter_field = get_counter_field_for_status(old_status_name)
    new_counter_field = get_counter_field_for_status(new_status_name)

    # Decrement the old status counter (ensure non-negative)
    old_value = getattr(agg, old_counter_field) or 0
    setattr(agg, old_counter_field, max(0, old_value - 1))

    # Increment the new status counter
    new_value = getattr(agg, new_counter_field) or 0
    setattr(agg, new_counter_field, new_value + 1)

    # Update timestamp
    agg.updated_at = datetime.utcnow()

    # Return the new derived status
    return derive_project_status_from_model(agg)


def update_aggregation_on_task_delete(
    agg: "ProjectTaskStatusAgg",
    task_status_name: str,
) -> str:
    """
    Update aggregation counters when a task is deleted.

    Decrements the appropriate status counter and total_tasks count.
    This is a mutating function that modifies the aggregation in place.

    Args:
        agg: The ProjectTaskStatusAgg model instance to update
        task_status_name: The status name of the deleted task

    Returns:
        The newly derived project status after the update

    Example:
        >>> agg = ProjectTaskStatusAgg(
        ...     project_id=project_id, total_tasks=5, todo_tasks=3
        ... )
        >>> new_status = update_aggregation_on_task_delete(agg, "Todo")
        >>> # agg.total_tasks is now 4, agg.todo_tasks is now 2
    """
    counter_field = get_counter_field_for_status(task_status_name)

    # Decrement the status-specific counter (ensure non-negative)
    current_value = getattr(agg, counter_field) or 0
    setattr(agg, counter_field, max(0, current_value - 1))

    # Decrement total tasks (ensure non-negative)
    agg.total_tasks = max(0, (agg.total_tasks or 0) - 1)

    # Update timestamp
    agg.updated_at = datetime.utcnow()

    # Return the new derived status
    return derive_project_status_from_model(agg)


def recalculate_aggregation_from_tasks(
    agg: "ProjectTaskStatusAgg",
    tasks: list,
) -> str:
    """
    Recalculate aggregation counters from a list of tasks.

    This is a full recalculation that resets all counters and rebuilds
    them from the provided task list. Use this for data integrity checks
    or when migrating existing data.

    Args:
        agg: The ProjectTaskStatusAgg model instance to update
        tasks: List of task objects with a 'status' attribute or
               task_status relationship with 'name' attribute

    Returns:
        The newly derived project status after recalculation

    Note:
        This function is O(n) where n is the number of tasks.
        For regular operations, use the incremental update functions.
    """
    # Reset all counters
    agg.total_tasks = 0
    agg.todo_tasks = 0
    agg.active_tasks = 0
    agg.review_tasks = 0
    agg.issue_tasks = 0
    agg.done_tasks = 0

    # Count tasks by status
    for task in tasks:
        # Get status name from task_status relationship (primary source)
        if hasattr(task, "task_status") and task.task_status is not None:
            status_name = task.task_status.name
        else:
            # Default to Todo if no status found
            status_name = StatusName.TODO.value

        # Increment appropriate counter
        try:
            counter_field = get_counter_field_for_status(status_name)
            current_value = getattr(agg, counter_field) or 0
            setattr(agg, counter_field, current_value + 1)
            agg.total_tasks += 1
        except ValueError:
            # Unknown status, skip this task or default to todo
            agg.todo_tasks = (agg.todo_tasks or 0) + 1
            agg.total_tasks += 1

    # Update timestamp
    agg.updated_at = datetime.utcnow()

    # Return the new derived status
    return derive_project_status_from_model(agg)


# Re-export StatusCategory for convenience
__all__ = [
    "StatusCategory",
    "StatusName",
    "STATUS_TO_COUNTER_FIELD",
    "ProjectAggregation",
    "derive_project_status",
    "derive_project_status_from_model",
    "get_counter_field_for_status",
    "update_aggregation_on_task_create",
    "update_aggregation_on_task_status_change",
    "update_aggregation_on_task_delete",
    "recalculate_aggregation_from_tasks",
]
