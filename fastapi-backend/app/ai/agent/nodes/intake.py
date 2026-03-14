"""Intake node — initialises pipeline state and caches LLM model.

Pure setup node with zero LLM calls.  Runs once at the start of each
user message to prepare the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from ..prompts import load_system_prompt
from ..state import AgentState

logger = logging.getLogger(__name__)


async def intake_node(
    state: AgentState,
    *,
    tools: list,
    provider_registry: Any,
    db_session_factory: Any,
    chat_model_cache: list[Any],
    system_prompt_cache: list[str],
    bound_model_cache: list[Any],
) -> dict:
    """Initialise counters, cache chat model, and load custom system prompt.

    This node runs exactly once per user message.  It does NOT call the
    LLM — it only resolves the provider config and caches the model so
    that downstream nodes can reuse it without re-querying the database.

    Args:
        state: Current pipeline state.
        tools: All available LangChain tool objects.
        provider_registry: ProviderRegistry instance.
        db_session_factory: Async session factory.
        chat_model_cache: Mutable list used as a single-element cache
            for the resolved LangChain chat model.
        system_prompt_cache: Mutable list used as a single-element cache
            for the effective system prompt string.
        bound_model_cache: Mutable list used as a single-element cache
            for the model with tools pre-bound (avoids re-binding per iteration).

    Returns:
        State update dict with initialised counters.
    """
    # Deferred import: graph.py imports nodes/, so importing graph at
    # module level would create a circular dependency.
    from ..graph import _get_langchain_chat_model

    # Resolve chat model once per graph invocation
    if not chat_model_cache:
        try:
            async with db_session_factory() as db:
                user_id_val = state.get("user_id")
                user_uuid = UUID(user_id_val) if user_id_val else None

                chat_model = await _get_langchain_chat_model(
                    provider_registry, db, user_uuid
                )

                # Load system prompt (base + optional custom addendum)
                system_prompt_cache.append(await load_system_prompt(db))

            chat_model_cache.append(chat_model)
            # Pre-bind tools once (avoids re-binding on every agent iteration)
            if tools:
                bound_model_cache.append(chat_model.bind_tools(tools))
        except Exception as exc:
            logger.error("intake_node: failed to initialise AI model: %s", exc)
            # Caches remain empty — downstream nodes will detect and return
            # graceful error messages via their empty-cache guards.

    return {
        # Reset per-turn safety counters for each new user message.
        # Counters accumulate within a single turn (agent → tools loop)
        # but must not carry over across turns in the same thread.
        # Intake only runs at the start of a new turn — resume from
        # interrupt re-enters the tools node directly, so these resets
        # don't affect in-flight interrupt/resume cycles.
        "total_tool_calls": 0,
        "total_llm_calls": 0,
        "iteration_count": 0,
        # DA-007: Reset auto-clarify guard so each new turn gets one attempt.
        "auto_clarify_attempted": False,
        # B1/B3: Reset loop guard counters for new turn.
        "clarify_count": 0,
        "synthesize_count": 0,
        # INVARIANT: intake_node runs only once per new user turn (graph entry
        # point). Resetting research here clears stale accumulator from previous
        # turns/HITL interrupts. DA3-MED-001: Stale tool_results from a previous
        # turn (e.g. after HITL interrupt) must not mix with new results. Intake
        # only runs for new user messages, not on HITL resumes which re-enter
        # explore_tools directly.
        "research": {},
    }
