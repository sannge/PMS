"""Unit tests for document write tools (update_document, delete_document, export_document_pdf).

Tests cover:
- update_document: happy path title update, content triggers re-embed, RBAC app/personal scope
- delete_document: soft delete sets deleted_at, creator-only enforcement
- create_document: doc_type parameter accepted
- export_document_pdf: PDF bytes generated
- WRITE_TOOLS registry updated count
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.ai.agent.tools.write_tools import (
    WRITE_TOOLS,
    create_document,
    delete_document,
    export_document_pdf,
    update_document,
)
from app.ai.agent.tools.context import clear_tool_context, set_tool_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_context(**overrides):
    """Populate tool context with sensible defaults + overrides."""
    ctx = {
        "user_id": str(uuid4()),
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "db_session_factory": MagicMock(),
        "provider_registry": MagicMock(),
    }
    ctx.update(overrides)
    set_tool_context(**{k: ctx[k] for k in (
        "user_id", "accessible_app_ids", "accessible_project_ids",
        "db_session_factory", "provider_registry",
    )})
    return ctx


def _clear():
    clear_tool_context()


def _mock_db_session():
    """Create a mock AsyncSession with close/rollback/commit."""
    session = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


def _make_mock_document(
    doc_id=None,
    title="Test Document",
    created_by=None,
    application_id=None,
    project_id=None,
    user_id=None,
    deleted_at=None,
    content_markdown="# Test\nSome content",
    content_plain="Test Some content",
):
    """Create a mock Document object."""
    doc = MagicMock()
    doc.id = doc_id or uuid4()
    doc.title = title
    doc.created_by = created_by or uuid4()
    doc.application_id = application_id
    doc.project_id = project_id
    doc.user_id = user_id
    doc.deleted_at = deleted_at
    doc.content_markdown = content_markdown
    doc.content_plain = content_plain
    doc.embedding_status = "synced"
    return doc


# ---------------------------------------------------------------------------
# WRITE_TOOLS registry
# ---------------------------------------------------------------------------


class TestWriteToolsRegistryUpdated:

    def test_has_11_tools(self):
        assert len(WRITE_TOOLS) == 11

    def test_includes_new_tools(self):
        names = {t.name for t in WRITE_TOOLS}
        assert "update_document" in names
        assert "delete_document" in names
        assert "export_document_pdf" in names


# ---------------------------------------------------------------------------
# update_document
# ---------------------------------------------------------------------------


class TestUpdateDocument:

    async def test_no_fields_provided(self):
        """update_document errors when neither title nor content provided."""
        _setup_context()
        result = await update_document.ainvoke({"doc": "some-doc"})
        assert "At least one" in result
        _clear()

    async def test_title_too_long(self):
        """update_document errors when title exceeds 200 chars."""
        _setup_context()
        result = await update_document.ainvoke({
            "doc": "some-doc",
            "title": "x" * 201,
        })
        assert "200 characters" in result
        _clear()

    @patch("app.ai.agent.tools.write_tools.interrupt")
    @patch("app.ai.agent.tools.write_tools._get_tool_session")
    async def test_update_title_happy_path(self, mock_tool_session, mock_interrupt):
        """update_document updates title on user approval."""
        user_id = str(uuid4())
        user_uuid = UUID(user_id)
        app_id = uuid4()
        doc_id = uuid4()

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
        )

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            title="Old Title",
            created_by=user_uuid,
            application_id=app_id,
        )

        # Session 1: resolve + RBAC check
        resolve_session = _mock_db_session()
        resolve_result = MagicMock()
        resolve_result.scalar_one_or_none.return_value = mock_doc
        resolve_session.execute.return_value = resolve_result

        # Session 2: RBAC re-check + write (combined)
        write_doc = _make_mock_document(
            doc_id=doc_id,
            title="Old Title",
            created_by=user_uuid,
            application_id=app_id,
        )
        combined_session = _mock_db_session()
        combined_result = MagicMock()
        combined_result.scalar_one_or_none.return_value = write_doc
        combined_session.execute.return_value = combined_result

        sessions = [resolve_session, combined_session]

        from contextlib import asynccontextmanager

        call_count = [0]

        @asynccontextmanager
        async def mock_session_cm():
            sess = sessions[call_count[0]]
            call_count[0] += 1
            yield sess

        mock_tool_session.side_effect = lambda: mock_session_cm()

        # Patch _resolve_document to return the doc ID directly
        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ):
            mock_interrupt.return_value = {"approved": True}

            result = await update_document.ainvoke({
                "doc": str(doc_id),
                "title": "New Title",
            })

        assert "Updated document" in result
        assert write_doc.title == "New Title"
        _clear()

    @patch("app.ai.agent.tools.write_tools.interrupt")
    @patch("app.ai.agent.tools.write_tools._get_tool_session")
    async def test_update_content_triggers_reembed(self, mock_tool_session, mock_interrupt):
        """update_document sets embedding_status to stale when content changes."""
        user_id = str(uuid4())
        user_uuid = UUID(user_id)
        app_id = uuid4()
        doc_id = uuid4()

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
        )

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            title="My Doc",
            created_by=user_uuid,
            application_id=app_id,
        )

        session = _mock_db_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_doc
        session.execute.return_value = result_mock

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session_cm():
            yield session

        mock_tool_session.side_effect = lambda: mock_session_cm()
        mock_interrupt.return_value = {"approved": True}

        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ):
            result = await update_document.ainvoke({
                "doc": str(doc_id),
                "content": "New content here",
            })

        assert "Updated document" in result
        assert mock_doc.embedding_status == "stale"
        _clear()

    async def test_rbac_personal_scope_denied(self):
        """update_document denies when user is not the document creator (personal scope)."""
        user_id = str(uuid4())
        other_user_id = uuid4()
        doc_id = uuid4()

        _setup_context(user_id=user_id)

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            created_by=other_user_id,
            user_id=other_user_id,  # personal scope
        )

        from contextlib import asynccontextmanager

        session = _mock_db_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_doc
        session.execute.return_value = result_mock

        @asynccontextmanager
        async def mock_session_cm():
            yield session

        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ), patch(
            "app.ai.agent.tools.write_tools._get_tool_session",
            side_effect=lambda: mock_session_cm(),
        ):
            result = await update_document.ainvoke({
                "doc": str(doc_id),
                "title": "Hacked Title",
            })

        assert "Access denied" in result
        _clear()

    async def test_rbac_app_scope_allowed(self):
        """update_document allows when user has app access (application scope)."""
        app_id = uuid4()
        user_id = str(uuid4())
        doc_id = uuid4()

        _setup_context(
            user_id=user_id,
            accessible_app_ids=[str(app_id)],
        )

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            created_by=UUID(user_id),
            application_id=app_id,
        )

        from contextlib import asynccontextmanager

        session = _mock_db_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_doc
        session.execute.return_value = result_mock

        @asynccontextmanager
        async def mock_session_cm():
            yield session

        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ), patch(
            "app.ai.agent.tools.write_tools._get_tool_session",
            side_effect=lambda: mock_session_cm(),
        ), patch(
            "app.ai.agent.tools.write_tools.interrupt",
            return_value={"approved": True},
        ):
            result = await update_document.ainvoke({
                "doc": str(doc_id),
                "title": "Updated Title",
            })

        assert "Updated document" in result
        _clear()


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------


class TestDeleteDocument:

    @patch("app.ai.agent.tools.write_tools.interrupt")
    @patch("app.ai.agent.tools.write_tools._get_tool_session")
    async def test_soft_delete_sets_deleted_at(self, mock_tool_session, mock_interrupt):
        """delete_document sets deleted_at on approval."""
        user_id = str(uuid4())
        user_uuid = UUID(user_id)
        doc_id = uuid4()

        _setup_context(user_id=user_id)

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            title="To Delete",
            created_by=user_uuid,
            user_id=user_uuid,  # personal scope
        )

        session = _mock_db_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_doc
        session.execute.return_value = result_mock

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_session_cm():
            yield session

        mock_tool_session.side_effect = lambda: mock_session_cm()
        mock_interrupt.return_value = {"approved": True}

        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ), patch(
            "app.services.search_service.index_document_soft_delete",
            new_callable=AsyncMock,
        ):
            result = await delete_document.ainvoke({"doc": str(doc_id)})

        assert "Deleted document" in result
        assert mock_doc.deleted_at is not None
        _clear()

    async def test_creator_only_enforcement(self):
        """delete_document denies when user is not the creator."""
        user_id = str(uuid4())
        other_user = uuid4()
        doc_id = uuid4()

        _setup_context(user_id=user_id)

        mock_doc = _make_mock_document(
            doc_id=doc_id,
            created_by=other_user,
            user_id=other_user,
        )

        from contextlib import asynccontextmanager

        session = _mock_db_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_doc
        session.execute.return_value = result_mock

        @asynccontextmanager
        async def mock_session_cm():
            yield session

        with patch(
            "app.ai.agent.tools.write_tools._resolve_document",
            return_value=(str(doc_id), None),
        ), patch(
            "app.ai.agent.tools.write_tools._get_tool_session",
            side_effect=lambda: mock_session_cm(),
        ):
            result = await delete_document.ainvoke({"doc": str(doc_id)})

        assert "Access denied" in result
        assert "creator" in result.lower()
        _clear()


# ---------------------------------------------------------------------------
# create_document with doc_type
# ---------------------------------------------------------------------------


class TestCreateDocumentDocType:

    async def test_doc_type_parameter_accepted(self):
        """create_document accepts doc_type without error when scope is invalid."""
        _setup_context()
        # With invalid scope, it should error on scope -- but doc_type should not cause issues
        result = await create_document.ainvoke({
            "title": "Training Guide",
            "content": "Step 1: Do this",
            "scope": "invalid_scope",
            "scope_id": str(uuid4()),
            "doc_type": "training",
        })
        # Should get scope error, not a doc_type error
        assert "Scope must be" in result
        _clear()

    async def test_doc_type_defaults_to_general(self):
        """create_document works without explicit doc_type."""
        _setup_context()
        result = await create_document.ainvoke({
            "title": "Just a Doc",
            "content": "Some content",
            "scope": "invalid_scope",
            "scope_id": str(uuid4()),
        })
        assert "Scope must be" in result
        _clear()


# ---------------------------------------------------------------------------
# export_document_pdf
# ---------------------------------------------------------------------------


class TestExportDocumentPdf:

    def test_pdf_generation(self):
        """generate_pdf produces non-empty bytes."""
        from app.ai.pdf_export import generate_pdf

        pdf_bytes = generate_pdf("Test Title", "# Heading\n\nSome **bold** text.\n\n- Item 1\n- Item 2")
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        # PDF magic bytes
        assert pdf_bytes[:4] == b"%PDF"

    def test_pdf_empty_content(self):
        """generate_pdf handles empty content."""
        from app.ai.pdf_export import generate_pdf

        pdf_bytes = generate_pdf("Empty Doc", "")
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"

    def test_pdf_long_content(self):
        """generate_pdf handles content that spans multiple pages."""
        from app.ai.pdf_export import generate_pdf

        long_content = "This is a paragraph.\n\n" * 200
        pdf_bytes = generate_pdf("Long Document", long_content)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000

    def test_cleanup_deletes_expired_files(self, tmp_path):
        """_cleanup_expired_exports removes files older than TTL."""
        import os
        import time

        from app.ai.pdf_export import _cleanup_expired_exports

        old_file = tmp_path / "old.pdf"
        old_file.write_bytes(b"data")
        old_time = time.time() - 3601  # older than default 3600s TTL
        os.utime(str(old_file), (old_time, old_time))

        new_file = tmp_path / "new.pdf"
        new_file.write_bytes(b"data")

        _cleanup_expired_exports(tmp_path)
        assert not old_file.exists()
        assert new_file.exists()
