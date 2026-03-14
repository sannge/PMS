"""Unit tests for document_service.py business logic helpers.

Tests cover:
- validate_scope: valid scopes (application, project, personal), invalid scope, missing entity
- set_scope_fks: all 3 scope types correctly set FKs
- get_scope_filter: returns correct filter expressions
- encode_cursor / decode_cursor: round-trip, invalid input
- encode_title_cursor / decode_title_cursor: round-trip, old format
- compute_materialized_path: root folder, nested 2+ levels
- validate_folder_depth: root, within limit, exceeds limit, parent not found
- validate_tag_scope: compatible/incompatible scope combos
- check_name_uniqueness: unique name, duplicate name
- convert_tiptap_to_markdown: delegation
- convert_tiptap_to_plain_text: delegation
- extract_attachment_ids: basic doc, canvas, empty
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.services.document_service import (
    check_name_uniqueness,
    compute_materialized_path,
    convert_tiptap_to_markdown,
    convert_tiptap_to_plain_text,
    decode_cursor,
    decode_title_cursor,
    encode_cursor,
    encode_title_cursor,
    extract_attachment_ids,
    get_scope_filter,
    set_scope_fks,
    validate_folder_depth,
    validate_scope,
    validate_tag_scope,
)


# ---------------------------------------------------------------------------
# validate_scope
# ---------------------------------------------------------------------------


class TestValidateScope:
    @pytest.mark.asyncio
    async def test_application_scope_exists(self, db_session, test_application):
        """Application scope with existing entity should pass."""
        # Should not raise
        await validate_scope("application", test_application.id, db_session)

    @pytest.mark.asyncio
    async def test_project_scope_exists(self, db_session, test_project):
        """Project scope with existing entity should pass."""
        await validate_scope("project", test_project.id, db_session)

    @pytest.mark.asyncio
    async def test_personal_scope_exists(self, db_session, test_user):
        """Personal scope with existing user should pass."""
        await validate_scope("personal", test_user.id, db_session)

    @pytest.mark.asyncio
    async def test_invalid_scope_type_raises_400(self, db_session):
        """Invalid scope type should raise 400."""
        with pytest.raises(HTTPException) as exc:
            await validate_scope("workspace", uuid4(), db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_entity_raises_404(self, db_session):
        """Non-existent entity should raise 404."""
        with pytest.raises(HTTPException) as exc:
            await validate_scope("application", uuid4(), db_session)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# set_scope_fks
# ---------------------------------------------------------------------------


class TestSetScopeFks:
    def test_application_scope(self):
        obj = SimpleNamespace(application_id=None, project_id=None, user_id=None)
        uid = uuid4()
        set_scope_fks(obj, "application", uid)
        assert obj.application_id == uid
        assert obj.project_id is None
        assert obj.user_id is None

    def test_project_scope(self):
        obj = SimpleNamespace(application_id=None, project_id=None, user_id=None)
        uid = uuid4()
        set_scope_fks(obj, "project", uid)
        assert obj.project_id == uid
        assert obj.application_id is None

    def test_personal_scope(self):
        obj = SimpleNamespace(application_id=None, project_id=None, user_id=None)
        uid = uuid4()
        set_scope_fks(obj, "personal", uid)
        assert obj.user_id == uid
        assert obj.application_id is None


# ---------------------------------------------------------------------------
# get_scope_filter
# ---------------------------------------------------------------------------


class TestGetScopeFilter:
    def test_application_scope_filter(self):
        from app.models.document import Document
        uid = uuid4()
        expr = get_scope_filter(Document, "application", uid)
        # Check that it generates a binary expression (BinaryExpression or BooleanClauseList)
        assert expr is not None

    def test_invalid_scope_raises_value_error(self):
        from app.models.document import Document
        with pytest.raises(ValueError, match="Invalid scope"):
            get_scope_filter(Document, "workspace", uuid4())


# ---------------------------------------------------------------------------
# encode_cursor / decode_cursor
# ---------------------------------------------------------------------------


class TestCursor:
    def test_round_trip(self):
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        uid = uuid4()
        cursor = encode_cursor(now, uid)
        decoded_at, decoded_id = decode_cursor(cursor)
        assert decoded_at == now
        assert decoded_id == uid

    def test_decode_invalid_cursor_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            decode_cursor("not-valid-base64!!")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# encode_title_cursor / decode_title_cursor
# ---------------------------------------------------------------------------


class TestTitleCursor:
    def test_round_trip(self):
        title = "My Document"
        uid = uuid4()
        cursor = encode_title_cursor(title, uid)
        decoded_title, decoded_id = decode_title_cursor(cursor)
        assert decoded_title == title
        assert decoded_id == uid

    def test_decode_old_format_raises_400(self):
        """Old created_at-based cursor (no 'title' key) should raise 400."""
        import base64
        old_payload = json.dumps({
            "created_at": "2026-01-01T00:00:00+00:00",
            "id": str(uuid4()),
        })
        old_cursor = base64.urlsafe_b64encode(old_payload.encode()).decode()
        with pytest.raises(HTTPException) as exc:
            decode_title_cursor(old_cursor)
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# compute_materialized_path
# ---------------------------------------------------------------------------


class TestComputeMaterializedPath:
    def test_root_folder(self):
        uid = uuid4()
        path = compute_materialized_path(None, uid)
        assert path == f"/{uid}/"

    def test_root_folder_slash_parent(self):
        uid = uuid4()
        path = compute_materialized_path("/", uid)
        assert path == f"/{uid}/"

    def test_nested_folder(self):
        parent_id = uuid4()
        child_id = uuid4()
        parent_path = f"/{parent_id}/"
        path = compute_materialized_path(parent_path, child_id)
        assert path == f"/{parent_id}/{child_id}/"

    def test_deeply_nested(self):
        """Three levels deep."""
        id_a = uuid4()
        id_b = uuid4()
        id_c = uuid4()
        path_a = f"/{id_a}/"
        path_b = compute_materialized_path(path_a, id_b)
        path_c = compute_materialized_path(path_b, id_c)
        assert path_c == f"/{id_a}/{id_b}/{id_c}/"


# ---------------------------------------------------------------------------
# validate_folder_depth
# ---------------------------------------------------------------------------


class TestValidateFolderDepth:
    @pytest.mark.asyncio
    async def test_root_level_returns_zero(self, db_session):
        """parent_id=None -> depth 0, path None."""
        depth, path = await validate_folder_depth(db_session, None)
        assert depth == 0
        assert path is None

    @pytest.mark.asyncio
    async def test_within_limit(self, db_session, test_application):
        """Parent at depth 2 -> child at depth 3 (within limit of 5)."""
        from app.models.document_folder import DocumentFolder
        folder = DocumentFolder(
            id=uuid4(),
            name="Parent",
            depth=2,
            materialized_path="/a/b/c/",
            application_id=test_application.id,
            created_by=test_application.owner_id,
        )
        db_session.add(folder)
        await db_session.flush()

        depth, path = await validate_folder_depth(db_session, folder.id)
        assert depth == 3
        assert path == "/a/b/c/"

    @pytest.mark.asyncio
    async def test_exceeds_limit_raises_400(self, db_session, test_application):
        """Parent at depth 5 -> child would be depth 6 -> raises 400."""
        from app.models.document_folder import DocumentFolder
        folder = DocumentFolder(
            id=uuid4(),
            name="Deep Folder",
            depth=5,
            materialized_path="/a/b/c/d/e/f/",
            application_id=test_application.id,
            created_by=test_application.owner_id,
        )
        db_session.add(folder)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await validate_folder_depth(db_session, folder.id)
        assert exc.value.status_code == 400
        assert "depth" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_parent_not_found_raises_404(self, db_session):
        """Non-existent parent_id -> raises 404."""
        with pytest.raises(HTTPException) as exc:
            await validate_folder_depth(db_session, uuid4())
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# validate_tag_scope
# ---------------------------------------------------------------------------


class TestValidateTagScope:
    @pytest.mark.asyncio
    async def test_application_doc_same_app_tag(self, db_session):
        """Application-scoped doc + tag with same application_id -> True."""
        app_id = uuid4()
        doc = SimpleNamespace(application_id=app_id, project_id=None, user_id=None)
        tag = SimpleNamespace(application_id=app_id, user_id=None)
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is True

    @pytest.mark.asyncio
    async def test_application_doc_different_app_tag(self, db_session):
        """Application-scoped doc + tag with different application_id -> False."""
        doc = SimpleNamespace(application_id=uuid4(), project_id=None, user_id=None)
        tag = SimpleNamespace(application_id=uuid4(), user_id=None)
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is False

    @pytest.mark.asyncio
    async def test_project_doc_matching_app_tag(self, db_session, test_project, test_application):
        """Project-scoped doc + tag with parent application_id -> True."""
        doc = SimpleNamespace(
            application_id=None,
            project_id=test_project.id,
            user_id=None,
        )
        tag = SimpleNamespace(application_id=test_application.id, user_id=None)
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is True

    @pytest.mark.asyncio
    async def test_personal_doc_same_user_tag(self, db_session):
        """Personal doc + tag with same user_id -> True."""
        uid = uuid4()
        doc = SimpleNamespace(application_id=None, project_id=None, user_id=uid)
        tag = SimpleNamespace(application_id=None, user_id=uid)
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is True

    @pytest.mark.asyncio
    async def test_personal_doc_different_user_tag(self, db_session):
        """Personal doc + tag with different user_id -> False."""
        doc = SimpleNamespace(application_id=None, project_id=None, user_id=uuid4())
        tag = SimpleNamespace(application_id=None, user_id=uuid4())
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_scope_returns_false(self, db_session):
        """Document with no scope FKs -> False."""
        doc = SimpleNamespace(application_id=None, project_id=None, user_id=None)
        tag = SimpleNamespace(application_id=uuid4(), user_id=None)
        result = await validate_tag_scope(db_session, doc, tag)
        assert result is False


# ---------------------------------------------------------------------------
# check_name_uniqueness
# ---------------------------------------------------------------------------


class TestCheckNameUniqueness:
    @pytest.mark.asyncio
    async def test_unique_name_passes(self, db_session, test_application, test_user):
        """No duplicates -> should not raise."""
        await check_name_uniqueness(
            db_session,
            "Unique Document",
            "application",
            test_application.id,
            None,
        )

    @pytest.mark.asyncio
    async def test_duplicate_folder_name_raises_409(self, db_session, test_application, test_user):
        """Duplicate folder name in same scope + parent -> 409."""
        from app.models.document_folder import DocumentFolder
        folder = DocumentFolder(
            id=uuid4(),
            name="Duplicate",
            application_id=test_application.id,
            depth=0,
            materialized_path="/",
            created_by=test_user.id,
        )
        db_session.add(folder)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await check_name_uniqueness(
                db_session,
                "duplicate",  # case-insensitive match
                "application",
                test_application.id,
                None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_duplicate_document_title_raises_409(self, db_session, test_application, test_user):
        """Duplicate document title in same scope + parent -> 409."""
        from app.models.document import Document
        doc = Document(
            id=uuid4(),
            title="Existing Doc",
            application_id=test_application.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc:
            await check_name_uniqueness(
                db_session,
                "Existing Doc",
                "application",
                test_application.id,
                None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_exclude_self_folder(self, db_session, test_application, test_user):
        """Excluding own folder_id should not flag as duplicate."""
        from app.models.document_folder import DocumentFolder
        folder = DocumentFolder(
            id=uuid4(),
            name="My Folder",
            application_id=test_application.id,
            depth=0,
            materialized_path="/",
            created_by=test_user.id,
        )
        db_session.add(folder)
        await db_session.flush()

        # Should not raise when excluding self
        await check_name_uniqueness(
            db_session,
            "My Folder",
            "application",
            test_application.id,
            None,
            exclude_folder_id=folder.id,
        )


# ---------------------------------------------------------------------------
# convert_tiptap_to_markdown / convert_tiptap_to_plain_text
# ---------------------------------------------------------------------------


class TestContentConversion:
    def test_markdown_empty_returns_empty(self):
        assert convert_tiptap_to_markdown(None) == ""
        assert convert_tiptap_to_markdown("") == ""

    def test_markdown_basic_doc(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]},
        ]}
        result = convert_tiptap_to_markdown(json.dumps(doc))
        assert "Hello world" in result

    def test_plain_text_empty_returns_empty(self):
        assert convert_tiptap_to_plain_text(None) == ""
        assert convert_tiptap_to_plain_text("") == ""

    def test_plain_text_basic_doc(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Plain text content"}]},
        ]}
        result = convert_tiptap_to_plain_text(json.dumps(doc))
        assert "Plain text content" in result


# ---------------------------------------------------------------------------
# extract_attachment_ids
# ---------------------------------------------------------------------------


class TestExtractAttachmentIds:
    def test_empty_content(self):
        assert extract_attachment_ids("") == set()
        assert extract_attachment_ids("null") == set()

    def test_invalid_json(self):
        assert extract_attachment_ids("not json") == set()

    def test_image_node(self):
        doc = {"type": "doc", "content": [
            {"type": "image", "attrs": {"attachmentId": "att-123"}},
        ]}
        result = extract_attachment_ids(json.dumps(doc))
        assert result == {"att-123"}

    def test_drawio_node(self):
        doc = {"type": "doc", "content": [
            {"type": "drawio", "attrs": {"attachmentId": "att-456"}},
        ]}
        result = extract_attachment_ids(json.dumps(doc))
        assert result == {"att-456"}

    def test_canvas_format(self):
        canvas = {
            "format": "canvas",
            "containers": [
                {
                    "content": {
                        "type": "doc",
                        "content": [
                            {"type": "image", "attrs": {"attachmentId": "att-789"}},
                        ],
                    },
                },
            ],
        }
        result = extract_attachment_ids(json.dumps(canvas))
        assert result == {"att-789"}

    def test_no_attachment_ids(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "No images"}]},
        ]}
        result = extract_attachment_ids(json.dumps(doc))
        assert result == set()

    def test_multiple_attachment_ids(self):
        doc = {"type": "doc", "content": [
            {"type": "image", "attrs": {"attachmentId": "a1"}},
            {"type": "paragraph", "content": [
                {"type": "text", "text": "between images"},
            ]},
            {"type": "image", "attrs": {"attachmentId": "a2"}},
            {"type": "drawio", "attrs": {"attachmentId": "a3"}},
        ]}
        result = extract_attachment_ids(json.dumps(doc))
        assert result == {"a1", "a2", "a3"}


# ---------------------------------------------------------------------------
# save_document_content
# ---------------------------------------------------------------------------


class TestSaveDocumentContent:
    """Tests for save_document_content: concurrency, permission, and 404."""

    TIPTAP_JSON = json.dumps({
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello save"}]},
        ],
    })

    @pytest_asyncio.fixture
    async def test_document(self, db_session, test_application, test_user):
        """Create a Document for save_document_content tests."""
        from app.models.document import Document as DocModel
        doc = DocModel(
            id=uuid4(),
            title="Save Test Doc",
            application_id=test_application.id,
            created_by=test_user.id,
            row_version=1,
        )
        db_session.add(doc)
        await db_session.flush()
        return doc

    @pytest.mark.asyncio
    async def test_successful_save_converts_content(
        self, db_session, test_user, test_document
    ):
        """Saving with correct row_version converts content and bumps version."""
        from app.services.document_service import save_document_content

        with patch(
            "app.services.search_service.build_search_doc_data",
            return_value={"id": "mock"},
        ):
            doc, search_data = await save_document_content(
                document_id=test_document.id,
                content_json=self.TIPTAP_JSON,
                row_version=1,
                user_id=test_user.id,
                db=db_session,
            )

        assert doc is not None
        assert doc.row_version == 2
        assert doc.content_json == self.TIPTAP_JSON
        assert "Hello save" in (doc.content_markdown or "")
        assert "Hello save" in (doc.content_plain or "")
        assert search_data is not None

    @pytest.mark.asyncio
    async def test_row_version_mismatch_raises_409(
        self, db_session, test_user, test_document
    ):
        """Passing wrong row_version should raise 409 Conflict."""
        from app.services.document_service import save_document_content

        with pytest.raises(HTTPException) as exc:
            await save_document_content(
                document_id=test_document.id,
                content_json=self.TIPTAP_JSON,
                row_version=999,  # wrong version
                user_id=test_user.id,
                db=db_session,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_document_not_found_raises_404(self, db_session, test_user):
        """Non-existent document_id should raise 404."""
        from app.services.document_service import save_document_content

        with pytest.raises(HTTPException) as exc:
            await save_document_content(
                document_id=uuid4(),
                content_json=self.TIPTAP_JSON,
                row_version=1,
                user_id=test_user.id,
                db=db_session,
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_permission_denied_raises_403(
        self, db_session, test_user, test_document
    ):
        """When check_edit_permission=True and user lacks edit, should raise 403."""
        from app.services.document_service import save_document_content

        with patch(
            "app.services.permission_service.PermissionService.check_can_edit_knowledge",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc:
                await save_document_content(
                    document_id=test_document.id,
                    content_json=self.TIPTAP_JSON,
                    row_version=1,
                    user_id=test_user.id,
                    db=db_session,
                    check_edit_permission=True,
                )
            assert exc.value.status_code == 403
