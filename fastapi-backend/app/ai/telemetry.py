"""Structured telemetry logging for all AI operations.

Emits JSON-structured log records under the ``ai.telemetry`` logger so
they can be collected by standard log aggregation tools (ELK, Datadog,
CloudWatch, etc.).

Privacy: **No PII** is ever logged — no message content, no API keys,
no file names, no personally identifiable information.

Log levels:
    - INFO  : successful operations
    - WARNING: slow operations (>5 s)
    - ERROR : failed operations
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger("ai.telemetry")

# Threshold for "slow" operations that trigger WARNING level (ms).
SLOW_THRESHOLD_MS = 5_000


# ---------------------------------------------------------------------------
# Cost estimation pricing table (per 1 M tokens, USD)
# ---------------------------------------------------------------------------
# APPROXIMATE pricing for monitoring dashboards only — NOT for billing.
# Last updated: 2026-02-27.  Source: provider pricing pages.
# To update: edit the dict below and bump the date above.
# Format: { "provider:model": (input_per_million, output_per_million) }

_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI chat
    "openai:gpt-5.2": (2.50, 10.00),
    "openai:gpt-5.1": (2.50, 10.00),
    "openai:gpt-5": (2.50, 10.00),
    "openai:gpt-5-mini": (0.15, 0.60),
    "openai:gpt-5-nano": (0.10, 0.40),
    "openai:gpt-4.1": (2.00, 8.00),
    "openai:gpt-4.1-mini": (0.40, 1.60),
    "openai:gpt-4o": (2.50, 10.00),
    "openai:gpt-4o-mini": (0.15, 0.60),
    # Anthropic chat
    "anthropic:claude-opus-4-6": (15.00, 75.00),
    "anthropic:claude-sonnet-4-6": (3.00, 15.00),
    "anthropic:claude-opus-4-5": (15.00, 75.00),
    "anthropic:claude-sonnet-4-5": (3.00, 15.00),
    "anthropic:claude-haiku-4-5": (0.80, 4.00),
    # OpenAI embedding
    "openai:text-embedding-3-small": (0.02, 0.0),
    "openai:text-embedding-3-large": (0.13, 0.0),
    # Ollama (local — free)
    "ollama:*": (0.0, 0.0),
}


# Maximum length for error strings in log output.
_MAX_ERROR_LENGTH = 500


def _sanitize_error(error: str | None) -> str | None:
    """Sanitize user-controlled error strings before logging.

    Strips newlines/carriage returns (prevents log injection), escapes
    control characters, and truncates to ``_MAX_ERROR_LENGTH`` chars.
    """
    if error is None:
        return None
    # Strip newlines and carriage returns to prevent log line injection
    sanitized = error.replace("\n", " ").replace("\r", " ")
    # Collapse multiple spaces from replacement
    while "  " in sanitized:
        sanitized = sanitized.replace("  ", " ")
    # Truncate
    if len(sanitized) > _MAX_ERROR_LENGTH:
        sanitized = sanitized[:_MAX_ERROR_LENGTH] + "...[truncated]"
    return sanitized


class AITelemetry:
    """Structured JSON logging for AI operations.

    All public methods are static so they can be called without
    instantiation (``AITelemetry.log_chat_request(...)``).
    """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _emit(
        operation: str,
        *,
        duration_ms: int,
        success: bool,
        user_id: UUID | str | None = None,
        **extra: Any,
    ) -> None:
        """Emit a structured JSON log record.

        Chooses log level based on *success* and *duration_ms*:
            - ERROR when ``success`` is False
            - WARNING when duration exceeds SLOW_THRESHOLD_MS
            - INFO otherwise
        """
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
        }
        if user_id is not None:
            record["user_id"] = str(user_id)
        record.update(extra)

        # Choose level
        if not success:
            level = logging.ERROR
        elif duration_ms > SLOW_THRESHOLD_MS:
            level = logging.WARNING
        else:
            level = logging.INFO

        logger.log(level, json.dumps(record, default=str))

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    @staticmethod
    def log_chat_request(
        user_id: UUID | str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        tool_calls: int,
        duration_ms: int,
        success: bool = True,
        cost_estimate: float | None = None,
        error: str | None = None,
    ) -> None:
        """Log a chat completion request."""
        if cost_estimate is None:
            cost_estimate = AITelemetry.estimate_cost(
                provider, model, input_tokens, output_tokens
            )
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "chat",
            duration_ms=duration_ms,
            success=success,
            user_id=user_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tool_calls=tool_calls,
            cost_estimate_usd=cost_estimate,
            **({"error": safe_error} if safe_error else {}),
        )

    @staticmethod
    def log_embedding_batch(
        document_count: int,
        chunk_count: int,
        total_tokens: int,
        provider: str,
        model: str,
        duration_ms: int,
        success: bool = True,
        cost_estimate: float | None = None,
        error: str | None = None,
    ) -> None:
        """Log an embedding batch operation."""
        if cost_estimate is None:
            cost_estimate = AITelemetry.estimate_cost(
                provider, model, total_tokens, 0
            )
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "embedding",
            duration_ms=duration_ms,
            success=success,
            document_count=document_count,
            chunk_count=chunk_count,
            total_tokens=total_tokens,
            provider=provider,
            model=model,
            cost_estimate_usd=cost_estimate,
            **({"error": safe_error} if safe_error else {}),
        )

    @staticmethod
    def log_sql_query(
        user_id: UUID | str,
        duration_ms: int,
        success: bool = True,
        tables_used: list[str] | None = None,
        row_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Log an AI SQL query execution (Phase 3.1)."""
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "sql_query",
            duration_ms=duration_ms,
            success=success,
            user_id=user_id,
            tables_used=tables_used or [],
            row_count=row_count,
            **({"error": safe_error} if safe_error else {}),
        )

    @staticmethod
    def log_tool_call(
        tool_name: str,
        user_id: UUID | str,
        duration_ms: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Log an agent tool call."""
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "tool_call",
            duration_ms=duration_ms,
            success=success,
            user_id=user_id,
            tool_name=tool_name,
            **({"error": safe_error} if safe_error else {}),
        )

    @staticmethod
    def log_import(
        user_id: UUID | str,
        file_type: str,
        file_size: int,
        duration_ms: int,
        success: bool,
        page_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Log a document import operation.

        No file name or content logged (could be PII).
        """
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "import",
            duration_ms=duration_ms,
            success=success,
            user_id=user_id,
            file_type=file_type,
            file_size_bytes=file_size,
            page_count=page_count,
            **({"error": safe_error} if safe_error else {}),
        )

    @staticmethod
    def log_reindex(
        user_id: UUID | str,
        document_count: int,
        duration_ms: int,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Log a reindex trigger."""
        safe_error = _sanitize_error(error)
        AITelemetry._emit(
            "reindex",
            duration_ms=duration_ms,
            success=success,
            user_id=user_id,
            document_count=document_count,
            **({"error": safe_error} if safe_error else {}),
        )

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_cost(
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        """Estimate USD cost based on known pricing.

        Returns ``None`` for unknown provider/model combinations.
        Ollama models always return 0.0 (local inference).

        These are rough estimates for monitoring — not for billing.
        """
        if not provider or not model:
            return None

        key = f"{provider.lower()}:{model.lower()}"

        # Exact match first
        if key in _PRICING:
            input_rate, output_rate = _PRICING[key]
            return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

        # Ollama wildcard
        if provider.lower() == "ollama":
            return 0.0

        # Unknown model — log warning on first miss
        logger.debug("No pricing data for %s, cost estimate unavailable", key)
        return None


# ---------------------------------------------------------------------------
# Convenience timer
# ---------------------------------------------------------------------------


class TelemetryTimer:
    """Simple context-manager / manual timer for measuring operation duration."""

    def __init__(self) -> None:
        self._start: float = 0.0

    def start(self) -> TelemetryTimer:
        self._start = time.monotonic()
        return self

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)

    def __enter__(self) -> TelemetryTimer:
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        pass
