"""Router-level integration tests for document, folder, and lock endpoints.

Tests cover:
- Documents: create (authorized + unauthorized), list with pagination, update, soft-delete, restore
- Folders: create (authorized + unauthorized), list tree
- Locks: acquire, release, heartbeat (mocked Redis)

Uses the same async test patterns as conftest.py: savepoint-scoped transactions,
AsyncClient with DI override, and auth_headers fixtures.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_member import ApplicationMember
from app.models.document import Document
from app.models.document_folder import DocumentFolder
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def app_with_member(db_session: AsyncSession, test_user: User, test_application: Application) -> Application:
    """Ensure test_user is an ApplicationMember (for permission checks)."""
    member = ApplicationMember(
        application_id=test_application.id,
        user_id=test_user.id,
        role="owner",
    )
    db_session.add(member)
    await db_session.flush()
    return test_application


@pytest.fixture(autouse=True)
def mock_redis_for_auth():
    """Mock redis_service so token blacklist checks pass (fail-closed without Redis)."""
    mock = AsyncMock()
    mock.is_connected = True
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.client = AsyncMock()
    with patch("app.services.redis_service.redis_service", mock):
        yield mock


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket broadcast to prevent side effects."""
    with patch("app.routers.documents.manager") as m:
        m.broadcast_to_room = AsyncMock()
        yield m


@pytest.fixture
def mock_ws_manager_folders():
    """Mock WebSocket broadcast for folder routes."""
    with patch("app.routers.document_folders.manager") as m:
        m.broadcast_to_room = AsyncMock()
        yield m


@pytest.fixture
def mock_search_index():
    """Mock search service to prevent Meilisearch calls."""
    with (
        patch("app.routers.documents.build_search_doc_data", return_value={}),
        patch("app.routers.documents.index_document_from_data", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
def mock_minio():
    """Mock MinIO service dependency for content update endpoints."""
    mock = MagicMock()
    mock.delete_file.return_value = None
    with patch("app.routers.documents.get_minio_service", return_value=mock):
        yield mock


# ---------------------------------------------------------------------------
# Documents: Create
# ---------------------------------------------------------------------------


class TestCreateDocument:
    @pytest.mark.asyncio
    async def test_create_document_authorized(self, client, auth_headers, app_with_member, mock_ws_manager):
        """Authenticated user with permission can create a document."""
        response = await client.post(
            "/api/documents",
            json={
                "title": "Test Doc",
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Doc"
        assert data["application_id"] == str(app_with_member.id)

    @pytest.mark.asyncio
    async def test_create_document_unauthorized_no_token(self, client, app_with_member):
        """Request without auth token should return 401."""
        response = await client.post(
            "/api/documents",
            json={
                "title": "No Auth",
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_document_forbidden(self, client, auth_headers_2, app_with_member):
        """User who is not a member should get 403."""
        response = await client.post(
            "/api/documents",
            json={
                "title": "Forbidden Doc",
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers_2,
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Documents: List with pagination
# ---------------------------------------------------------------------------


class TestListDocuments:
    @pytest.mark.asyncio
    async def test_list_documents(self, client, auth_headers, app_with_member, db_session, test_user, mock_ws_manager):
        """List documents returns items and supports pagination."""
        # Create a few documents
        for i in range(3):
            doc = Document(
                title=f"Doc {i}",
                application_id=app_with_member.id,
                created_by=test_user.id,
            )
            db_session.add(doc)
        await db_session.flush()

        response = await client.get(
            "/api/documents",
            params={
                "scope": "application",
                "scope_id": str(app_with_member.id),
                "limit": 2,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_list_documents_empty(self, client, auth_headers, app_with_member):
        """List documents for scope with no docs returns empty list."""
        response = await client.get(
            "/api/documents",
            params={
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["next_cursor"] is None


# ---------------------------------------------------------------------------
# Documents: Update
# ---------------------------------------------------------------------------


class TestUpdateDocument:
    @pytest.mark.asyncio
    async def test_update_document(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_ws_manager, mock_minio
    ):
        """Authenticated owner can update document title."""
        doc = Document(
            title="Original Title",
            application_id=app_with_member.id,
            created_by=test_user.id,
            row_version=1,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        response = await client.put(
            f"/api/documents/{doc_id}",
            json={
                "title": "Updated Title",
                "row_version": 1,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"
        assert response.json()["row_version"] == 2


# ---------------------------------------------------------------------------
# Documents: Soft-delete and restore
# ---------------------------------------------------------------------------


class TestDeleteAndRestore:
    @pytest.mark.asyncio
    async def test_soft_delete_document(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_ws_manager
    ):
        """Soft-deleting a document sets deleted_at and returns 204."""
        doc = Document(
            title="To Delete",
            application_id=app_with_member.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        response = await client.delete(
            f"/api/documents/{doc_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify it no longer appears in active list
        list_resp = await client.get(
            "/api/documents",
            params={
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        items = list_resp.json()["items"]
        assert not any(item["id"] == str(doc_id) for item in items)

    @pytest.mark.asyncio
    async def test_restore_document(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_ws_manager
    ):
        """Restoring a soft-deleted document clears deleted_at."""
        from app.utils.timezone import utc_now

        doc = Document(
            title="To Restore",
            application_id=app_with_member.id,
            created_by=test_user.id,
            deleted_at=utc_now(),
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        response = await client.post(
            f"/api/documents/{doc_id}/restore",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted_at"] is None


# ---------------------------------------------------------------------------
# Folders: Create
# ---------------------------------------------------------------------------


class TestCreateFolder:
    @pytest.mark.asyncio
    async def test_create_folder_authorized(self, client, auth_headers, app_with_member, mock_ws_manager_folders):
        """Authenticated user with permission can create a folder."""
        response = await client.post(
            "/api/document-folders",
            json={
                "name": "Architecture",
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Architecture"
        assert data["depth"] == 0

    @pytest.mark.asyncio
    async def test_create_folder_unauthorized(self, client, app_with_member):
        """Request without auth token should return 401."""
        response = await client.post(
            "/api/document-folders",
            json={
                "name": "No Auth Folder",
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Folders: List tree
# ---------------------------------------------------------------------------


class TestFolderTree:
    @pytest.mark.asyncio
    async def test_list_folder_tree(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_ws_manager_folders
    ):
        """Folder tree returns nested structure."""
        root_folder = DocumentFolder(
            name="Root",
            application_id=app_with_member.id,
            depth=0,
            materialized_path="/",
            created_by=test_user.id,
        )
        db_session.add(root_folder)
        await db_session.flush()
        root_folder.materialized_path = f"/{root_folder.id}/"
        await db_session.flush()

        response = await client.get(
            "/api/document-folders/tree",
            params={
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Root"

    @pytest.mark.asyncio
    async def test_empty_folder_tree(self, client, auth_headers, app_with_member):
        """Empty scope returns empty tree."""
        response = await client.get(
            "/api/document-folders/tree",
            params={
                "scope": "application",
                "scope_id": str(app_with_member.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Locks: acquire, release, heartbeat (mocked Redis)
# ---------------------------------------------------------------------------


class TestDocumentLocks:
    @pytest.fixture
    def mock_redis_locks(self):
        """Mock redis_service for lock operations."""
        with patch("app.services.document_lock_service.redis_service") as mock_rs:
            mock_rs.client = AsyncMock()
            mock_rs.scan_keys = AsyncMock(return_value=[])
            yield mock_rs

    @pytest.fixture
    def mock_lock_broadcast(self):
        """Mock WebSocket lock change handler."""
        with patch("app.routers.document_locks.handle_document_lock_change", new_callable=AsyncMock):
            yield

    @pytest.mark.asyncio
    async def test_acquire_lock(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_redis_locks, mock_lock_broadcast
    ):
        """Acquiring a lock on an owned document returns locked=True."""
        doc = Document(
            title="Lockable Doc",
            application_id=app_with_member.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        # Mock: lock acquired
        mock_redis_locks.client.eval.return_value = json.dumps({"status": "acquired"})

        response = await client.post(
            f"/api/documents/{doc_id}/lock",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["locked"] is True

    @pytest.mark.asyncio
    async def test_release_lock(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_redis_locks, mock_lock_broadcast
    ):
        """Releasing a lock returns locked=False."""
        doc = Document(
            title="Releasable Doc",
            application_id=app_with_member.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        # Mock: release succeeded
        mock_redis_locks.client.eval.return_value = 1

        response = await client.delete(
            f"/api/documents/{doc_id}/lock",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["locked"] is False

    @pytest.mark.asyncio
    async def test_lock_heartbeat(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_redis_locks, mock_lock_broadcast
    ):
        """Heartbeat extends lock TTL."""
        doc = Document(
            title="Heartbeat Doc",
            application_id=app_with_member.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        # Mock: heartbeat extended
        mock_redis_locks.client.eval.return_value = 1

        response = await client.post(
            f"/api/documents/{doc_id}/lock/heartbeat",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["extended"] is True

    @pytest.mark.asyncio
    async def test_heartbeat_not_owner(
        self, client, auth_headers, app_with_member, db_session, test_user, mock_redis_locks, mock_lock_broadcast
    ):
        """Heartbeat by non-owner returns 409."""
        doc = Document(
            title="Not My Lock Doc",
            application_id=app_with_member.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        doc_id = doc.id

        # Mock: heartbeat failed (not owner)
        mock_redis_locks.client.eval.return_value = 0

        response = await client.post(
            f"/api/documents/{doc_id}/lock/heartbeat",
            headers=auth_headers,
        )
        assert response.status_code == 409
