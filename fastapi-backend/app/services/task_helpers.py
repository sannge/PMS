"""Shared helper functions for task operations."""
from typing import Optional
from ..schemas.task import TaskStatusInfo


def get_task_status_info(task) -> Optional[TaskStatusInfo]:
    """Convert a task's task_status relationship to TaskStatusInfo, or return None."""
    ts = getattr(task, "task_status", None)
    if ts is None:
        return None
    return TaskStatusInfo(
        id=ts.id,
        name=ts.name,
        category=ts.category,
        rank=ts.rank,
    )
