"""Pydantic schemas for AI SQL query endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SQLQueryRequest(BaseModel):
    """Request to execute a natural language query."""

    question: str = Field(..., min_length=3, max_length=1000)
    application_id: UUID | None = None
    project_id: UUID | None = None


class SQLQueryResponse(BaseModel):
    """Response from SQL query execution."""

    model_config = ConfigDict(from_attributes=True)

    question: str
    sql: str
    explanation: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    generation_ms: int
    execution_ms: int


class SQLValidateRequest(BaseModel):
    """Request to validate SQL without executing."""

    sql: str = Field(..., min_length=5, max_length=5000)


class SQLValidateResponse(BaseModel):
    """Validation result."""

    is_valid: bool
    error: str | None = None
    tables_used: list[str] | None = None


class ExportResult(BaseModel):
    """Excel export result."""

    filename: str
    download_url: str
    row_count: int


class ToolResult(BaseModel):
    """Generic agent tool result."""

    success: bool
    data: str | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None
