"""CopilotKit SDK bridge for AG-UI protocol support.

Wraps the Blair LangGraph agent in a CopilotKit SDK instance so
the frontend can interact with it via the standard AG-UI event
stream (TEXT_MESSAGE, TOOL_CALL, INTERRUPT, STATE_SNAPSHOT, etc.).

The CopilotKit Python SDK is an *optional* dependency.  If the
package is not installed the factory returns ``None`` and the
``/api/copilotkit`` endpoint is disabled at startup.  The primary
chat endpoints (``/api/ai/chat`` and ``/api/ai/chat/stream``) work
independently of CopilotKit.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_copilotkit_sdk(agent_graph: Any) -> Any | None:
    """Create a CopilotKit SDK instance configured with the Blair agent.

    Args:
        agent_graph: Compiled LangGraph ``CompiledStateGraph`` returned by
            ``build_agent_graph()``.

    Returns:
        A ``CopilotKitSDK`` instance, or ``None`` if the ``copilotkit``
        package is unavailable or initialisation fails.
    """
    try:
        from copilotkit import CopilotKitSDK  # type: ignore[import-untyped]
        from copilotkit.langgraph import LangGraphAgent  # type: ignore[import-untyped]

        sdk = CopilotKitSDK(
            agents=[
                LangGraphAgent(
                    name="blair",
                    description=(
                        "Blair — PM Desktop AI Copilot for projects, "
                        "tasks, and knowledge base"
                    ),
                    agent=agent_graph,
                )
            ]
        )
        logger.info("CopilotKit SDK initialised with Blair agent")
        return sdk

    except ImportError:
        logger.warning(
            "copilotkit package not installed — CopilotKit endpoints disabled"
        )
        return None

    except Exception:
        logger.warning(
            "Failed to initialise CopilotKit SDK", exc_info=True
        )
        return None
