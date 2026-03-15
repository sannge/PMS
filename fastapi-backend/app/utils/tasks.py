"""Utilities for safe fire-and-forget asyncio task management.

Provides a helper that keeps a strong reference to background tasks
so they are not garbage-collected before completion, and logs any
exceptions that occur instead of silently swallowing them.
"""

import asyncio
import logging
from typing import Coroutine, Any

logger = logging.getLogger(__name__)

# Module-level set keeps strong references so the event loop does not
# garbage-collect tasks before they finish.
_background_tasks: set[asyncio.Task[Any]] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any]:
    """Schedule a coroutine as a tracked background task.

    The task is added to a module-level set to prevent GC, and a
    done-callback is attached that logs exceptions and removes the
    task from the set.

    Args:
        coro: The coroutine to run in the background.
        name: Optional name for the task (for logging).

    Returns:
        The created asyncio.Task.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_task_done)
    return task


def _task_done(task: asyncio.Task[Any]) -> None:
    """Done callback: discard from set and log exceptions."""
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %s failed: %s: %s",
            task.get_name(),
            type(exc).__name__,
            exc,
        )


async def drain_background_tasks(timeout: float = 5.0) -> None:
    """Wait for all pending background tasks to finish, cancelling stragglers.

    Called during application shutdown to give in-flight fire-and-forget
    tasks a chance to complete before the process exits.

    Args:
        timeout: Maximum seconds to wait before cancelling remaining tasks.
    """
    if not _background_tasks:
        return
    logger.info("Draining %d background tasks...", len(_background_tasks))
    done, pending = await asyncio.wait(_background_tasks, timeout=timeout)
    for t in pending:
        t.cancel()
    if pending:
        logger.warning("Cancelled %d background tasks that did not finish in %.1fs", len(pending), timeout)
