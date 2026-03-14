"""Per-request context for Blair AI agent tools.

Provides async-safe context variables (via ``contextvars``) that carry
user identity, RBAC scope, and infrastructure references through the
tool call chain.  Must be initialised via ``set_tool_context`` before
invoking the agent graph, and torn down via ``clear_tool_context``
afterward.
"""

from __future__ import annotations

import contextvars
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# Per-request context — uses contextvars for async/concurrency safety
# ---------------------------------------------------------------------------


class _Unset:
    """Singleton sentinel for uninitialized tool context."""


_UNSET = _Unset()

_tool_context_var: contextvars.ContextVar[dict[str, Any] | _Unset] = contextvars.ContextVar(
    "tool_context", default=_UNSET
)

# Module-level dict — TEST-ONLY, kept for backward compat with tests
# that do ``_tool_context.update(...)``.
#
# *** PRODUCTION CODE MUST NEVER READ FROM THIS DICT. ***
#
# Production code MUST use ``_get_ctx()`` which reads the ContextVar.
# Direct mutations (e.g. ``_tool_context["key"] = val``) will NOT sync to
# the ContextVar.  Only ``set_tool_context`` / ``clear_tool_context`` keep
# both stores in sync.
#
# ``clear_tool_context()`` always clears this dict alongside the ContextVar.
_tool_context: dict[str, Any] = {}


def set_tool_context(
    user_id: str,
    accessible_app_ids: list[str],
    accessible_project_ids: list[str],
    db_session_factory: Any,
    provider_registry: Any,
) -> None:
    """Configure the per-request context used by all tools.

    Uses ``contextvars.ContextVar`` for async-safe isolation between
    concurrent requests. Must be called before invoking the agent graph.

    Args:
        user_id: UUID string of the requesting user.
        accessible_app_ids: List of application UUID strings the user can access.
        accessible_project_ids: List of project UUID strings the user can access.
        db_session_factory: Async context manager that yields an AsyncSession.
        provider_registry: ProviderRegistry singleton for AI providers.
    """
    ctx = {
        "user_id": user_id,
        "accessible_app_ids": accessible_app_ids,
        "accessible_project_ids": accessible_project_ids,
        "db_session_factory": db_session_factory,
        "provider_registry": provider_registry,
    }
    _tool_context_var.set(ctx)
    # Update module-level dict for test backward compat
    _tool_context.clear()
    _tool_context.update(ctx)


def clear_tool_context() -> None:
    """Clear the tool context after graph execution."""
    _tool_context_var.set(_UNSET)
    _tool_context.clear()


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------


def _get_ctx() -> dict[str, Any]:
    """Return the current request's tool context (async-safe).

    Always reads from the ContextVar — never falls back to the
    module-level ``_tool_context`` dict.  The module-level dict is
    only kept for test backward compatibility (tests that do
    ``_tool_context.update(...)``), but production code reads
    exclusively from the ContextVar to avoid cross-request races.

    Raises:
        RuntimeError: If the context is empty (set_tool_context not called).
    """
    ctx = _tool_context_var.get()
    if isinstance(ctx, _Unset) or not ctx:
        raise RuntimeError(
            "Tool context is empty — call set_tool_context() before invoking agent tools. "
            "This usually means the agent graph was invoked without proper RBAC setup."
        )
    return ctx


def _get_user_id() -> UUID:
    """Return the current user's UUID from tool context.

    Raises:
        RuntimeError: If tool context has not been set.
    """
    uid = _get_ctx().get("user_id")
    if uid is None:
        raise RuntimeError("Tool context not set — call set_tool_context() first")
    return UUID(uid)


def _check_app_access(app_id: str) -> bool:
    """Check whether the current user has access to an application."""
    return app_id in _get_ctx().get("accessible_app_ids", [])


def _check_project_access(project_id: str) -> bool:
    """Check whether the current user has access to a project."""
    return project_id in _get_ctx().get("accessible_project_ids", [])
