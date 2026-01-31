"""Unit tests for Notes CRUD API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.note import Note
from app.models.user import User


@pytest.mark.asyncio
class TestListNotes:
    """Tests for listing notes."""

    async def test_list_notes_empty(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test listing notes when none exist."""
        response = await client.get(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_notes_with_data(
        self, client: AsyncClient, auth_headers: dict, test_application: Application, test_note: Note
    ):
        """Test listing notes with existing data."""
        response = await client.get(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == test_note.title
        assert "children_count" in data[0]

    async def test_list_notes_pagination(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_application: Application, test_user: User
    ):
        """Test pagination of notes list."""
        # Create multiple notes
        for i in range(5):
            note = Note(
                title=f"Note {i}",
                application_id=test_application.id,
                created_by=test_user.id,
                tab_order=i,
            )
            db_session.add(note)
        await db_session.commit()

        # Test skip and limit
        response = await client.get(
            f"/api/applications/{test_application.id}/notes?skip=2&limit=2",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_notes_search(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_application: Application, test_user: User
    ):
        """Test searching notes by title."""
        for title in ["Meeting Notes", "Design Ideas", "Project Planning"]:
            note = Note(title=title, application_id=test_application.id, created_by=test_user.id)
            db_session.add(note)
        await db_session.commit()

        response = await client.get(
            f"/api/applications/{test_application.id}/notes?search=Notes",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "Notes" in data[0]["title"]

    async def test_list_notes_root_only(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_application: Application, test_user: User
    ):
        """Test filtering only root-level notes."""
        # Create a parent note
        parent = Note(title="Parent", application_id=test_application.id, created_by=test_user.id)
        db_session.add(parent)
        await db_session.commit()

        # Create a child note
        child = Note(
            title="Child",
            application_id=test_application.id,
            parent_id=parent.id,
            created_by=test_user.id,
        )
        db_session.add(child)
        await db_session.commit()

        # Get only root notes
        response = await client.get(
            f"/api/applications/{test_application.id}/notes?root_only=true",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Parent"

    async def test_list_notes_nonexistent_application(self, client: AsyncClient, auth_headers: dict):
        """Test listing notes for nonexistent application."""
        response = await client.get(
            f"/api/applications/{uuid4()}/notes",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_list_notes_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_application: Application
    ):
        """Test listing notes for application owned by another user."""
        response = await client.get(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers_2,
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestGetNoteTree:
    """Tests for getting hierarchical note tree."""

    async def test_get_note_tree_empty(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test getting note tree when empty."""
        response = await client.get(
            f"/api/applications/{test_application.id}/notes/tree",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_note_tree_with_hierarchy(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_application: Application, test_user: User
    ):
        """Test getting note tree with parent-child relationships."""
        # Create parent note
        parent = Note(
            title="Parent Note",
            application_id=test_application.id,
            created_by=test_user.id,
            tab_order=0,
        )
        db_session.add(parent)
        await db_session.commit()

        # Create child notes
        child1 = Note(
            title="Child 1",
            application_id=test_application.id,
            parent_id=parent.id,
            created_by=test_user.id,
            tab_order=0,
        )
        child2 = Note(
            title="Child 2",
            application_id=test_application.id,
            parent_id=parent.id,
            created_by=test_user.id,
            tab_order=1,
        )
        db_session.add(child1)
        db_session.add(child2)
        await db_session.commit()

        response = await client.get(
            f"/api/applications/{test_application.id}/notes/tree",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1  # Only parent at root
        assert data[0]["title"] == "Parent Note"
        assert "children" in data[0]
        assert len(data[0]["children"]) == 2


@pytest.mark.asyncio
class TestCreateNote:
    """Tests for creating notes."""

    async def test_create_note_success(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test successful note creation."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={
                "application_id": str(test_application.id),
                "title": "New Note",
                "content": "<p>Note content</p>",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Note"
        assert data["content"] == "<p>Note content</p>"
        assert "id" in data

    async def test_create_note_minimal(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a note with minimal data."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={
                "application_id": str(test_application.id),
                "title": "Minimal Note",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Note"
        assert data["tab_order"] >= 0

    async def test_create_note_with_parent(
        self, client: AsyncClient, auth_headers: dict, test_application: Application, test_note: Note
    ):
        """Test creating a child note."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={
                "application_id": str(test_application.id),
                "title": "Child Note",
                "parent_id": str(test_note.id),
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["parent_id"] == str(test_note.id)

    async def test_create_note_missing_title(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a note without title fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={"application_id": str(test_application.id)},
        )

        assert response.status_code == 422

    async def test_create_note_application_id_mismatch(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a note with mismatched application ID fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={
                "application_id": str(uuid4()),  # Different ID
                "title": "Note",
            },
        )

        assert response.status_code == 400

    async def test_create_note_invalid_parent(
        self, client: AsyncClient, auth_headers: dict, test_application: Application
    ):
        """Test creating a note with invalid parent fails."""
        response = await client.post(
            f"/api/applications/{test_application.id}/notes",
            headers=auth_headers,
            json={
                "application_id": str(test_application.id),
                "title": "Note",
                "parent_id": str(uuid4()),  # Nonexistent parent
            },
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestGetNote:
    """Tests for getting a single note."""

    async def test_get_note_success(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test getting a note by ID."""
        response = await client.get(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_note.id)
        assert data["title"] == test_note.title
        assert "children_count" in data

    async def test_get_note_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting a nonexistent note."""
        response = await client.get(
            f"/api/notes/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_note_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_note: Note
    ):
        """Test getting note owned by another user."""
        response = await client.get(
            f"/api/notes/{test_note.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403


@pytest.mark.asyncio
class TestGetNoteChildren:
    """Tests for getting note children."""

    async def test_get_note_children_empty(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test getting children when none exist."""
        response = await client.get(
            f"/api/notes/{test_note.id}/children",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_note_children_with_data(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_note: Note, test_user: User, test_application: Application
    ):
        """Test getting children with existing data."""
        # Create child notes
        for i in range(3):
            child = Note(
                title=f"Child {i}",
                application_id=test_application.id,
                parent_id=test_note.id,
                created_by=test_user.id,
                tab_order=i,
            )
            db_session.add(child)
        await db_session.commit()

        response = await client.get(
            f"/api/notes/{test_note.id}/children",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


@pytest.mark.asyncio
class TestUpdateNote:
    """Tests for updating notes."""

    async def test_update_note_success(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test successful note update."""
        response = await client.put(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
            json={
                "title": "Updated Note Title",
                "content": "<p>Updated content</p>",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Note Title"
        assert data["content"] == "<p>Updated content</p>"

    async def test_update_note_partial(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test partial note update."""
        response = await client.put(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
            json={"title": "Only Title Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Only Title Updated"
        assert data["content"] == test_note.content

    async def test_update_note_empty_body(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test updating note with empty body fails."""
        response = await client.put(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 400

    async def test_update_note_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test updating nonexistent note."""
        response = await client.put(
            f"/api/notes/{uuid4()}",
            headers=auth_headers,
            json={"title": "Updated"},
        )

        assert response.status_code == 404

    async def test_update_note_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_note: Note
    ):
        """Test updating note owned by another user."""
        response = await client.put(
            f"/api/notes/{test_note.id}",
            headers=auth_headers_2,
            json={"title": "Hacked"},
        )

        assert response.status_code == 403

    async def test_update_note_self_parent_fails(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test setting note as its own parent fails."""
        response = await client.put(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
            json={"parent_id": str(test_note.id)},
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestReorderNote:
    """Tests for reordering notes."""

    async def test_reorder_note_success(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test successful note reorder."""
        response = await client.put(
            f"/api/notes/{test_note.id}/reorder?new_order=5",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tab_order"] == 5

    async def test_reorder_note_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test reordering nonexistent note."""
        response = await client.put(
            f"/api/notes/{uuid4()}/reorder?new_order=5",
            headers=auth_headers,
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestDeleteNote:
    """Tests for deleting notes."""

    async def test_delete_note_success(
        self, client: AsyncClient, auth_headers: dict, test_note: Note
    ):
        """Test successful note deletion."""
        response = await client.delete(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        response = await client.get(
            f"/api/notes/{test_note.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_delete_note_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting nonexistent note."""
        response = await client.delete(
            f"/api/notes/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_note_wrong_owner(
        self, client: AsyncClient, auth_headers_2: dict, test_note: Note
    ):
        """Test deleting note owned by another user."""
        response = await client.delete(
            f"/api/notes/{test_note.id}",
            headers=auth_headers_2,
        )

        assert response.status_code == 403

    async def test_delete_note_cascade_children(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_note: Note, test_user: User, test_application: Application
    ):
        """Test deleting note with cascade deletes children."""
        # Create child note
        child = Note(
            title="Child",
            application_id=test_application.id,
            parent_id=test_note.id,
            created_by=test_user.id,
        )
        db_session.add(child)
        await db_session.commit()
        child_id = child.id

        # Delete parent with cascade (default)
        response = await client.delete(
            f"/api/notes/{test_note.id}?cascade=true",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify child is also deleted
        result = await db_session.execute(select(Note).filter(Note.id == child_id))
        child = result.scalar_one_or_none()
        assert child is None

    async def test_delete_note_orphan_children(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        test_note: Note, test_user: User, test_application: Application
    ):
        """Test deleting note without cascade orphans children."""
        # Create child note
        child = Note(
            title="Child",
            application_id=test_application.id,
            parent_id=test_note.id,
            created_by=test_user.id,
        )
        db_session.add(child)
        await db_session.commit()
        child_id = child.id

        # Delete parent without cascade
        response = await client.delete(
            f"/api/notes/{test_note.id}?cascade=false",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify child still exists but is orphaned
        await db_session.expire_all()
        result = await db_session.execute(select(Note).filter(Note.id == child_id))
        child = result.scalar_one_or_none()
        assert child is not None
        assert child.parent_id is None
