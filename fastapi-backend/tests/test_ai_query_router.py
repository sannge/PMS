"""Integration-style tests for AI query router (app.routers.ai_query).

Uses httpx.AsyncClient with ASGITransport against the real FastAPI app,
with dependency overrides for authentication and database.

Tests cover:
- POST /api/ai/query  (NL query -> SQL -> results)
- POST /api/ai/query/validate  (SQL validation)
- GET  /api/ai/schema  (schema text)
- GET  /api/ai/export/{filename}  (file download, 404)
- 401  on all endpoints when unauthenticated
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app as fastapi_app
from app.services.auth_service import get_current_user

# Pre-import lazy modules so @patch can resolve them
import app.ai.sql_generator  # noqa: F401
import app.ai.sql_executor  # noqa: F401
import app.ai.sql_validator  # noqa: F401
import app.ai.schema_context  # noqa: F401
import app.ai.excel_export  # noqa: F401


# ---------------------------------------------------------------------------
# Mock user and DB
# ---------------------------------------------------------------------------

_mock_user = MagicMock()
_mock_user.id = uuid4()
_mock_user.email = "test@example.com"
_mock_user.display_name = "Test User"


def _override_current_user():
    return _mock_user


async def _override_get_db():
    yield AsyncMock()


# ---------------------------------------------------------------------------
# Mock dataclasses that match the shapes used by the router
# ---------------------------------------------------------------------------


@dataclass
class MockGenerated:
    sql: str
    explanation: str
    tables_used: list[str]
    duration_ms: int


@dataclass
class MockQueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_ms: int


@dataclass
class MockValidationResult:
    is_valid: bool
    error: str | None = None
    tables_used: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _override_deps():
    """Override auth and DB dependencies for all tests in this module."""
    fastapi_app.dependency_overrides[get_current_user] = _override_current_user
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def _no_auth():
    """Remove auth override so requests are unauthenticated."""
    fastapi_app.dependency_overrides.pop(get_current_user, None)
    yield
    fastapi_app.dependency_overrides[get_current_user] = _override_current_user


# ---------------------------------------------------------------------------
# Tests: POST /api/ai/query
# ---------------------------------------------------------------------------


class TestQueryEndpoint:
    @patch("app.ai.sql_executor.execute")
    @patch("app.ai.sql_generator.generate_query")
    async def test_returns_query_response(self, mock_gen, mock_exec):
        mock_gen.return_value = MockGenerated(
            sql="SELECT name FROM v_users LIMIT 100",
            explanation="Lists all user names",
            tables_used=["v_users"],
            duration_ms=42,
        )
        mock_exec.return_value = MockQueryResult(
            columns=["name"],
            rows=[{"name": "Alice"}],
            row_count=1,
            truncated=False,
            execution_ms=8,
        )

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query",
                json={"question": "Who are all users?"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["question"] == "Who are all users?"
        assert body["sql"] == "SELECT name FROM v_users LIMIT 100"
        assert body["row_count"] == 1
        assert body["columns"] == ["name"]

    @patch(
        "app.ai.sql_generator.generate_query",
        side_effect=ValueError("LLM refused"),
    )
    async def test_generation_failure_returns_422(self, _mock_gen):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query",
                json={"question": "something impossible"},
            )

        assert resp.status_code == 422
        assert "Failed to generate SQL" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: POST /api/ai/query/validate
# ---------------------------------------------------------------------------


class TestValidateEndpoint:
    @patch("app.ai.sql_validator.validate")
    async def test_valid_sql_accepted(self, mock_validate):
        mock_validate.return_value = MockValidationResult(
            is_valid=True,
            tables_used=["v_tasks"],
        )

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query/validate",
                json={"sql": "SELECT * FROM v_tasks LIMIT 10"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_valid"] is True
        assert "v_tasks" in body["tables_used"]

    @patch("app.ai.sql_validator.validate")
    async def test_invalid_sql_rejected(self, mock_validate):
        mock_validate.return_value = MockValidationResult(
            is_valid=False,
            error="Mutation keyword blocked: DROP",
        )

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query/validate",
                json={"sql": "DROP TABLE v_tasks"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["is_valid"] is False
        assert "DROP" in body["error"]


# ---------------------------------------------------------------------------
# Tests: GET /api/ai/schema
# ---------------------------------------------------------------------------


class TestSchemaEndpoint:
    @patch("app.ai.schema_context.get_schema_prompt")
    async def test_returns_schema_text(self, mock_prompt):
        mock_prompt.return_value = "# Database Schema\nv_tasks ..."

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.get("/api/ai/schema")

        assert resp.status_code == 200
        body = resp.json()
        assert "schema" in body
        assert "v_tasks" in body["schema"]


# ---------------------------------------------------------------------------
# Tests: GET /api/ai/export/{filename}
# ---------------------------------------------------------------------------


class TestExportEndpoint:
    @patch("app.ai.excel_export.get_export_path", return_value=None)
    async def test_nonexistent_file_returns_404(self, _mock_path):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.get("/api/ai/export/nonexistent.xlsx")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: 401 without authentication
# ---------------------------------------------------------------------------


class TestAuthRequired:
    @pytest.mark.usefixtures("_no_auth")
    async def test_query_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query",
                json={"question": "list users"},
            )
        assert resp.status_code == 401

    @pytest.mark.usefixtures("_no_auth")
    async def test_validate_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.post(
                "/api/ai/query/validate",
                json={"sql": "SELECT 1 FROM v_tasks"},
            )
        assert resp.status_code == 401

    @pytest.mark.usefixtures("_no_auth")
    async def test_schema_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.get("/api/ai/schema")
        assert resp.status_code == 401

    @pytest.mark.usefixtures("_no_auth")
    async def test_export_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            resp = await client.get("/api/ai/export/test.xlsx")
        assert resp.status_code == 401
