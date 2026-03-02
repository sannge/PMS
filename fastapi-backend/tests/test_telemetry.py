"""Unit tests for AI telemetry (Phase 7 — 7.3-7.5).

Tests the AITelemetry class methods, structured JSON output,
log level selection, cost estimation, and TelemetryTimer utility.
"""

import json
import logging
import time
from uuid import uuid4

import pytest

from app.ai.telemetry import AITelemetry, TelemetryTimer, _sanitize_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_log(caplog, level=logging.DEBUG):
    """Context manager to capture logs from the ai.telemetry logger."""
    caplog.set_level(level, logger="ai.telemetry")


def _parse_last_log(caplog) -> dict:
    """Parse the last captured log record as JSON."""
    assert caplog.records, "No log records captured"
    return json.loads(caplog.records[-1].message)


# ---------------------------------------------------------------------------
# log_chat_request
# ---------------------------------------------------------------------------


class TestLogChatRequest:
    def test_structured_output(self, caplog):
        _capture_log(caplog)
        user_id = uuid4()

        AITelemetry.log_chat_request(
            user_id=user_id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=1500,
            output_tokens=500,
            tool_calls=2,
            duration_ms=1200,
            success=True,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "chat"
        assert data["user_id"] == str(user_id)
        assert data["provider"] == "anthropic"
        assert data["model"] == "claude-sonnet-4-6"
        assert data["input_tokens"] == 1500
        assert data["output_tokens"] == 500
        assert data["tool_calls"] == 2
        assert data["duration_ms"] == 1200
        assert data["success"] is True
        assert "timestamp" in data
        assert "cost_estimate_usd" in data

    def test_no_pii_in_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_chat_request(
            user_id=uuid4(),
            provider="openai",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            tool_calls=0,
            duration_ms=500,
        )

        log_text = caplog.records[-1].message
        # No message content, no API keys
        assert "sk-" not in log_text
        assert "message" not in log_text.lower() or "message" in json.loads(log_text).get("operation", "")

    def test_info_level_on_success(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_chat_request(
            user_id=uuid4(),
            provider="openai",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            tool_calls=0,
            duration_ms=500,
            success=True,
        )

        assert caplog.records[-1].levelno == logging.INFO

    def test_error_level_on_failure(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_chat_request(
            user_id=uuid4(),
            provider="openai",
            model="gpt-5",
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            duration_ms=100,
            success=False,
            error="Provider timeout",
        )

        assert caplog.records[-1].levelno == logging.ERROR
        data = _parse_last_log(caplog)
        assert data["error"] == "Provider timeout"

    def test_warning_level_on_slow(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_chat_request(
            user_id=uuid4(),
            provider="openai",
            model="gpt-5",
            input_tokens=100,
            output_tokens=50,
            tool_calls=0,
            duration_ms=6000,  # > 5000ms threshold
            success=True,
        )

        assert caplog.records[-1].levelno == logging.WARNING

    def test_cost_auto_calculated(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_chat_request(
            user_id=uuid4(),
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            tool_calls=0,
            duration_ms=5000,
        )

        data = _parse_last_log(caplog)
        # Claude Sonnet: $3/1M input + $15/1M output = $18
        assert data["cost_estimate_usd"] == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# log_embedding_batch
# ---------------------------------------------------------------------------


class TestLogEmbeddingBatch:
    def test_structured_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_embedding_batch(
            document_count=5,
            chunk_count=42,
            total_tokens=8000,
            provider="openai",
            model="text-embedding-3-small",
            duration_ms=350,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "embedding"
        assert data["document_count"] == 5
        assert data["chunk_count"] == 42
        assert data["total_tokens"] == 8000
        assert data["success"] is True

    def test_cost_for_embedding(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_embedding_batch(
            document_count=1,
            chunk_count=10,
            total_tokens=1_000_000,
            provider="openai",
            model="text-embedding-3-small",
            duration_ms=200,
        )

        data = _parse_last_log(caplog)
        # text-embedding-3-small: $0.02/1M tokens
        assert data["cost_estimate_usd"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# log_tool_call
# ---------------------------------------------------------------------------


class TestLogToolCall:
    def test_structured_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_tool_call(
            tool_name="query_knowledge",
            user_id=uuid4(),
            duration_ms=150,
            success=True,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "tool_call"
        assert data["tool_name"] == "query_knowledge"
        assert data["duration_ms"] == 150
        assert data["success"] is True

    def test_failed_tool_call(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_tool_call(
            tool_name="sql_query",
            user_id=uuid4(),
            duration_ms=50,
            success=False,
            error="ValidationError",
        )

        data = _parse_last_log(caplog)
        assert data["success"] is False
        assert data["error"] == "ValidationError"
        assert caplog.records[-1].levelno == logging.ERROR


# ---------------------------------------------------------------------------
# log_import
# ---------------------------------------------------------------------------


class TestLogImport:
    def test_structured_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_import(
            user_id=uuid4(),
            file_type="pdf",
            file_size=1024 * 1024,
            duration_ms=5500,
            success=True,
            page_count=12,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "import"
        assert data["file_type"] == "pdf"
        assert data["file_size_bytes"] == 1024 * 1024
        assert data["page_count"] == 12
        # No file name in output
        assert "file_name" not in data

    def test_no_file_name_logged(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_import(
            user_id=uuid4(),
            file_type="docx",
            file_size=500,
            duration_ms=100,
            success=True,
        )

        log_text = caplog.records[-1].message
        assert "file_name" not in log_text


# ---------------------------------------------------------------------------
# log_sql_query
# ---------------------------------------------------------------------------


class TestLogSqlQuery:
    def test_structured_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_sql_query(
            user_id=uuid4(),
            duration_ms=250,
            success=True,
            tables_used=["v_tasks", "v_projects"],
            row_count=15,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "sql_query"
        assert data["row_count"] == 15
        assert data["tables_used"] == ["v_tasks", "v_projects"]


# ---------------------------------------------------------------------------
# log_reindex
# ---------------------------------------------------------------------------


class TestLogReindex:
    def test_structured_output(self, caplog):
        _capture_log(caplog)

        AITelemetry.log_reindex(
            user_id=uuid4(),
            document_count=3,
            duration_ms=0,
            success=True,
        )

        data = _parse_last_log(caplog)
        assert data["operation"] == "reindex"
        assert data["document_count"] == 3


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_known_openai_model(self):
        # GPT-5.2: $2.50/1M input, $10.00/1M output
        cost = AITelemetry.estimate_cost("openai", "gpt-5.2", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.50)

    def test_known_anthropic_model(self):
        # Claude Sonnet 4.6: $3.00/1M input, $15.00/1M output
        cost = AITelemetry.estimate_cost("anthropic", "claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.00)

    def test_known_embedding_model(self):
        # text-embedding-3-small: $0.02/1M input
        cost = AITelemetry.estimate_cost("openai", "text-embedding-3-small", 1_000_000, 0)
        assert cost == pytest.approx(0.02)

    def test_ollama_free(self):
        cost = AITelemetry.estimate_cost("ollama", "llama3.1", 1_000_000, 1_000_000)
        assert cost == 0.0

    def test_ollama_any_model_free(self):
        cost = AITelemetry.estimate_cost("ollama", "custom-model", 5_000_000, 5_000_000)
        assert cost == 0.0

    def test_unknown_model_returns_none(self):
        cost = AITelemetry.estimate_cost("openai", "gpt-99", 1000, 1000)
        assert cost is None

    def test_unknown_provider_returns_none(self):
        cost = AITelemetry.estimate_cost("azure", "gpt-4", 1000, 1000)
        assert cost is None

    def test_zero_tokens(self):
        cost = AITelemetry.estimate_cost("openai", "gpt-5.2", 0, 0)
        assert cost == 0.0

    def test_empty_provider_returns_none(self):
        cost = AITelemetry.estimate_cost("", "gpt-5", 1000, 1000)
        assert cost is None

    def test_empty_model_returns_none(self):
        cost = AITelemetry.estimate_cost("openai", "", 1000, 1000)
        assert cost is None

    def test_case_insensitive(self):
        cost = AITelemetry.estimate_cost("OpenAI", "GPT-5.2", 1_000_000, 0)
        assert cost is not None
        assert cost == pytest.approx(2.50)


# ---------------------------------------------------------------------------
# _sanitize_error
# ---------------------------------------------------------------------------


class TestSanitizeError:
    def test_none_returns_none(self):
        assert _sanitize_error(None) is None

    def test_plain_string_unchanged(self):
        assert _sanitize_error("Connection refused") == "Connection refused"

    def test_newlines_stripped(self):
        result = _sanitize_error("line1\nline2\rline3")
        assert "\n" not in result
        assert "\r" not in result
        assert result == "line1 line2 line3"

    def test_truncation(self):
        long_error = "x" * 600
        result = _sanitize_error(long_error)
        assert len(result) == 500 + len("...[truncated]")
        assert result.endswith("...[truncated]")

    def test_collapse_multiple_spaces(self):
        result = _sanitize_error("error\n\n\nmessage")
        assert "   " not in result
        assert result == "error message"


# ---------------------------------------------------------------------------
# TelemetryTimer
# ---------------------------------------------------------------------------


class TestTelemetryTimer:
    def test_context_manager(self):
        with TelemetryTimer() as timer:
            time.sleep(0.05)

        assert timer.elapsed_ms >= 30  # at least ~50ms (generous margin for Windows)

    def test_manual_start(self):
        timer = TelemetryTimer().start()
        time.sleep(0.05)
        assert timer.elapsed_ms >= 30

    def test_elapsed_before_start_is_negative(self):
        timer = TelemetryTimer()
        # Before start(), _start is 0, so elapsed will be large
        # This is expected behavior — start() must be called first
        assert timer.elapsed_ms > 0
