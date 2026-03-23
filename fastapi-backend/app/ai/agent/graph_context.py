"""Per-request mutable state for the agent graph.

The compiled LangGraph is cached and reused across requests.
Per-request mutable caches are stored in ContextVars so concurrent
requests do not pollute each other's state.

Nodes read from these ContextVars at runtime.  Tests can still pass
caches directly via keyword arguments (the ContextVar is only consulted
when the kwarg is ``None``).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# Mutable caches populated by intake_node (or pre-warmed by the caller),
# read by other nodes.  All vars have ``default=None`` so that ``.get()``
# never raises ``LookupError`` — callers must handle the None case.
chat_model_var: ContextVar[list[Any] | None] = ContextVar("chat_model_var", default=None)
system_prompt_var: ContextVar[list[str] | None] = ContextVar("system_prompt_var", default=None)
bound_model_var: ContextVar[list[Any] | None] = ContextVar("bound_model_var", default=None)

# Per-request singletons set by the caller before graph invocation.
provider_registry_var: ContextVar[Any] = ContextVar("provider_registry_var", default=None)
db_session_factory_var: ContextVar[Any] = ContextVar("db_session_factory_var", default=None)
tools_var: ContextVar[list[Any] | None] = ContextVar("tools_var", default=None)
