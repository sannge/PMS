"""Unit tests for FolderFile model and DocumentChunk extensions.

Tests cover:
- FolderFile scope CHECK constraint (exactly one of application_id/project_id/user_id)
- DocumentChunk source CHECK constraint (exactly one of document_id/file_id)
- Unique display_name per folder (case-insensitive, partial index excluding soft-deleted)
- Cascade delete: FolderFile deletion cascades to its chunks
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_folder import DocumentFolder
from app.models.folder_file import FolderFile
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def folder_for_files(
    db_session: AsyncSession,
    test_user: User,
    test_application: Application,
) -> DocumentFolder:
    """Create a DocumentFolder scoped to the test application."""
    folder = DocumentFolder(
        id=uuid4(),
        name="Test Folder",
        application_id=test_application.id,
        created_by=test_user.id,
        materialized_path="/",
        depth=0,
        sort_order=0,
    )
    db_session.add(folder)
    await db_session.flush()
    return folder


@pytest_asyncio.fixture
async def second_folder(
    db_session: AsyncSession,
    test_user: User,
    test_application: Application,
) -> DocumentFolder:
    """Create a second DocumentFolder scoped to the test application."""
    folder = DocumentFolder(
        id=uuid4(),
        name="Second Folder",
        application_id=test_application.id,
        created_by=test_user.id,
        materialized_path="/",
        depth=0,
        sort_order=1,
    )
    db_session.add(folder)
    await db_session.flush()
    return folder


def _make_file(
    folder: DocumentFolder,
    user: User,
    *,
    application_id=None,
    project_id=None,
    user_id=None,
    display_name: str = "test-file.pdf",
) -> FolderFile:
    """Helper to build a FolderFile with minimal required fields."""
    return FolderFile(
        id=uuid4(),
        folder_id=folder.id,
        application_id=application_id,
        project_id=project_id,
        user_id=user_id,
        original_name=display_name,
        display_name=display_name,
        mime_type="application/pdf",
        file_size=1024,
        file_extension="pdf",
        storage_bucket="pm-files",
        storage_key=f"files/{uuid4()}.pdf",
        created_by=user.id,
    )


# ---------------------------------------------------------------------------
# FolderFile scope constraint
# ---------------------------------------------------------------------------


class TestFolderFileScopeConstraint:
    """Verify the ck_folder_files_exactly_one_scope CHECK constraint."""

    @pytest.mark.asyncio
    async def test_create_with_application_scope(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Creating a FolderFile with only application_id should succeed."""
        ff = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
        )
        db_session.add(ff)
        await db_session.flush()

        assert ff.id is not None
        assert ff.application_id == test_application.id
        assert ff.project_id is None
        assert ff.user_id is None

    @pytest.mark.asyncio
    async def test_create_with_zero_scopes_fails(
        self,
        db_session: AsyncSession,
        test_user: User,
        folder_for_files: DocumentFolder,
    ):
        """Creating a FolderFile with no scope FK should fail CHECK constraint."""
        ff = _make_file(
            folder_for_files,
            test_user,
            # No scope FK set
        )
        db_session.add(ff)
        with pytest.raises(IntegrityError, match="ck_folder_files_exactly_one_scope"):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_create_with_two_scopes_fails(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Creating a FolderFile with two scope FKs should fail CHECK constraint."""
        ff = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            user_id=test_user.id,  # second scope
        )
        db_session.add(ff)
        with pytest.raises(IntegrityError, match="ck_folder_files_exactly_one_scope"):
            await db_session.flush()


# ---------------------------------------------------------------------------
# DocumentChunk source constraint
# ---------------------------------------------------------------------------


class TestDocumentChunkSourceConstraint:
    """Verify the ck_chunks_exactly_one_source CHECK constraint."""

    @pytest.mark.asyncio
    async def test_chunk_with_file_id_succeeds(
        self,
        db_session: AsyncSession,
        requires_pgvector,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Creating a DocumentChunk with file_id (no document_id) should succeed."""
        ff = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
        )
        db_session.add(ff)
        await db_session.flush()

        chunk = DocumentChunk(
            id=uuid4(),
            file_id=ff.id,
            document_id=None,
            source_type="file",
            chunk_index=0,
            chunk_text="Extracted text from file",
            chunk_type="text",
            token_count=5,
            application_id=test_application.id,
        )
        db_session.add(chunk)
        await db_session.flush()

        assert chunk.id is not None
        assert chunk.file_id == ff.id
        assert chunk.document_id is None

    @pytest.mark.asyncio
    async def test_chunk_with_both_sources_fails(
        self,
        db_session: AsyncSession,
        requires_pgvector,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Creating a chunk with both document_id and file_id should fail."""
        # Create a document for the document_id FK
        doc = Document(
            id=uuid4(),
            title="Test Doc",
            application_id=test_application.id,
            created_by=test_user.id,
        )
        db_session.add(doc)
        await db_session.flush()

        # Create a file for the file_id FK
        ff = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
        )
        db_session.add(ff)
        await db_session.flush()

        chunk = DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            file_id=ff.id,  # Both set — should fail
            source_type="document",
            chunk_index=0,
            chunk_text="Some text",
            chunk_type="text",
            token_count=2,
            application_id=test_application.id,
        )
        db_session.add(chunk)
        with pytest.raises(IntegrityError, match="ck_chunks_exactly_one_source"):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_chunk_with_neither_source_fails(
        self,
        db_session: AsyncSession,
        requires_pgvector,
    ):
        """Creating a chunk with neither document_id nor file_id should fail."""
        chunk = DocumentChunk(
            id=uuid4(),
            document_id=None,
            file_id=None,  # Neither set — should fail
            source_type="document",
            chunk_index=0,
            chunk_text="Orphan text",
            chunk_type="text",
            token_count=2,
        )
        db_session.add(chunk)
        with pytest.raises(IntegrityError, match="ck_chunks_exactly_one_source"):
            await db_session.flush()


# ---------------------------------------------------------------------------
# Unique display_name constraint
# ---------------------------------------------------------------------------


class TestUniqueDisplayName:
    """Verify the uq_folder_files_name partial unique index."""

    @pytest.mark.asyncio
    async def test_duplicate_name_same_folder_fails(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Two active files with the same display_name in one folder should fail."""
        ff1 = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        db_session.add(ff1)
        await db_session.flush()

        ff2 = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        db_session.add(ff2)
        with pytest.raises(IntegrityError, match="uq_folder_files_name"):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_duplicate_name_different_folder_succeeds(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
        second_folder: DocumentFolder,
    ):
        """Same display_name in different folders should succeed."""
        ff1 = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        ff2 = _make_file(
            second_folder,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        db_session.add(ff1)
        db_session.add(ff2)
        await db_session.flush()

        assert ff1.id != ff2.id
        assert ff1.display_name == ff2.display_name

    @pytest.mark.asyncio
    async def test_duplicate_name_with_soft_deleted_succeeds(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """A new file with the same name as a soft-deleted file should succeed."""
        from app.utils.timezone import utc_now

        ff1 = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        ff1.deleted_at = utc_now()  # Soft-deleted
        db_session.add(ff1)
        await db_session.flush()

        ff2 = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
            display_name="report.pdf",
        )
        db_session.add(ff2)
        await db_session.flush()

        assert ff2.id is not None
        assert ff2.deleted_at is None


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------


class TestCascadeDelete:
    """Verify cascade delete from FolderFile to DocumentChunks."""

    @pytest.mark.asyncio
    async def test_delete_file_cascades_to_chunks(
        self,
        db_session: AsyncSession,
        requires_pgvector,
        test_user: User,
        test_application: Application,
        folder_for_files: DocumentFolder,
    ):
        """Deleting a FolderFile should cascade-delete its chunks."""
        ff = _make_file(
            folder_for_files,
            test_user,
            application_id=test_application.id,
        )
        db_session.add(ff)
        await db_session.flush()

        # Create two chunks for this file
        for idx in range(2):
            chunk = DocumentChunk(
                id=uuid4(),
                file_id=ff.id,
                document_id=None,
                source_type="file",
                chunk_index=idx,
                chunk_text=f"Chunk {idx} text",
                chunk_type="text",
                token_count=3,
                application_id=test_application.id,
            )
            db_session.add(chunk)
        await db_session.flush()

        # Verify chunks exist
        result = await db_session.execute(
            text('SELECT COUNT(*) FROM "DocumentChunks" WHERE file_id = :fid'),
            {"fid": ff.id},
        )
        assert result.scalar() == 2

        # Delete the file
        await db_session.delete(ff)
        await db_session.flush()

        # Verify chunks are gone
        result = await db_session.execute(
            text('SELECT COUNT(*) FROM "DocumentChunks" WHERE file_id = :fid'),
            {"fid": ff.id},
        )
        assert result.scalar() == 0
