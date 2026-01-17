"""Unit tests for MinIO service."""

from datetime import timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from minio.error import S3Error

from app.services.minio_service import (
    MinIOService,
    MinIOServiceError,
    get_minio_service,
    minio_service,
)


class TestMinIOServiceInit:
    """Tests for MinIO service initialization."""

    def test_service_instance_exists(self):
        """Test that global service instance exists."""
        assert minio_service is not None
        assert isinstance(minio_service, MinIOService)

    def test_get_minio_service_dependency(self):
        """Test get_minio_service returns the singleton."""
        service = get_minio_service()
        assert service is minio_service

    def test_client_lazy_initialization(self):
        """Test that client is lazily initialized."""
        service = MinIOService()
        assert service._client is None
        assert service._initialized is False


class TestMinIOServiceClient:
    """Tests for MinIO client property."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_client_creation_success(self, mock_settings, mock_minio_class):
        """Test successful client creation."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access_key"
        mock_settings.minio_secret_key = "secret_key"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        client = service.client

        assert client is mock_client
        mock_minio_class.assert_called_once_with(
            endpoint="localhost:9000",
            access_key="access_key",
            secret_key="secret_key",
            secure=False,
        )

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_client_creation_failure(self, mock_settings, mock_minio_class):
        """Test client creation failure raises MinIOServiceError."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access_key"
        mock_settings.minio_secret_key = "secret_key"
        mock_settings.minio_secure = False

        mock_minio_class.side_effect = Exception("Connection failed")

        service = MinIOService()

        with pytest.raises(MinIOServiceError) as exc_info:
            _ = service.client

        assert "Failed to create MinIO client" in str(exc_info.value)


class TestMinIOServiceBuckets:
    """Tests for bucket operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_ensure_buckets_exist_creates_missing(self, mock_settings, mock_minio_class):
        """Test that missing buckets are created."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = False
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        service.ensure_buckets_exist()

        # Should check and create both buckets
        assert mock_client.bucket_exists.call_count == 2
        assert mock_client.make_bucket.call_count == 2
        assert service._initialized is True

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_ensure_buckets_exist_skips_existing(self, mock_settings, mock_minio_class):
        """Test that existing buckets are not recreated."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        service.ensure_buckets_exist()

        assert mock_client.bucket_exists.call_count == 2
        assert mock_client.make_bucket.call_count == 0

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_ensure_buckets_exist_once(self, mock_settings, mock_minio_class):
        """Test that bucket creation only happens once."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        service.ensure_buckets_exist()
        service.ensure_buckets_exist()  # Second call

        # Should only run once
        assert mock_client.bucket_exists.call_count == 2  # Not 4


class TestMinIOServiceUpload:
    """Tests for file upload operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_upload_file_success(self, mock_settings, mock_minio_class):
        """Test successful file upload."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        data = BytesIO(b"test content")

        result = service.upload_file(
            bucket="pm-attachments",
            object_name="test/file.txt",
            data=data,
            length=12,
            content_type="text/plain",
        )

        assert result == "test/file.txt"
        mock_client.put_object.assert_called_once()

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_upload_bytes_success(self, mock_settings, mock_minio_class):
        """Test successful bytes upload."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        data = b"test content"

        result = service.upload_bytes(
            bucket="pm-attachments",
            object_name="test/file.txt",
            data=data,
            content_type="text/plain",
        )

        assert result == "test/file.txt"
        mock_client.put_object.assert_called_once()

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_upload_file_failure(self, mock_settings, mock_minio_class):
        """Test upload failure raises MinIOServiceError."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_client.put_object.side_effect = S3Error(
            "Error", "Error", "Error", "Error", "Error", "Error"
        )
        mock_minio_class.return_value = mock_client

        service = MinIOService()

        with pytest.raises(MinIOServiceError) as exc_info:
            service.upload_file(
                bucket="pm-attachments",
                object_name="test/file.txt",
                data=BytesIO(b"test"),
                length=4,
            )

        assert "Failed to upload file" in str(exc_info.value)


class TestMinIOServiceDownload:
    """Tests for file download operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_download_file_success(self, mock_settings, mock_minio_class):
        """Test successful file download."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_response = MagicMock()
        mock_response.read.return_value = b"test content"

        mock_client = MagicMock()
        mock_client.get_object.return_value = mock_response
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.download_file("pm-attachments", "test/file.txt")

        assert result == b"test content"
        mock_response.close.assert_called_once()
        mock_response.release_conn.assert_called_once()

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_download_file_failure(self, mock_settings, mock_minio_class):
        """Test download failure raises MinIOServiceError."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.get_object.side_effect = S3Error(
            "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey"
        )
        mock_minio_class.return_value = mock_client

        service = MinIOService()

        with pytest.raises(MinIOServiceError) as exc_info:
            service.download_file("pm-attachments", "nonexistent.txt")

        assert "Failed to download file" in str(exc_info.value)


class TestMinIOServiceDelete:
    """Tests for file deletion operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_delete_file_success(self, mock_settings, mock_minio_class):
        """Test successful file deletion."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.delete_file("pm-attachments", "test/file.txt")

        assert result is True
        mock_client.remove_object.assert_called_once_with("pm-attachments", "test/file.txt")


class TestMinIOServiceUrls:
    """Tests for URL generation."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_get_presigned_download_url(self, mock_settings, mock_minio_class):
        """Test presigned download URL generation."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.presigned_get_object.return_value = "http://example.com/download"
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.get_presigned_download_url("pm-attachments", "test/file.txt")

        assert result == "http://example.com/download"
        mock_client.presigned_get_object.assert_called_once()

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_get_presigned_upload_url(self, mock_settings, mock_minio_class):
        """Test presigned upload URL generation."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.presigned_put_object.return_value = "http://example.com/upload"
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.get_presigned_upload_url(
            "pm-attachments",
            "test/file.txt",
            expiry=timedelta(hours=2),
        )

        assert result == "http://example.com/upload"
        mock_client.presigned_put_object.assert_called_once()


class TestMinIOServiceInfo:
    """Tests for file info operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_file_exists_true(self, mock_settings, mock_minio_class):
        """Test file exists returns true."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.file_exists("pm-attachments", "test/file.txt")

        assert result is True
        mock_client.stat_object.assert_called_once()

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_file_exists_false(self, mock_settings, mock_minio_class):
        """Test file exists returns false for nonexistent file."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_client = MagicMock()
        mock_client.stat_object.side_effect = S3Error(
            "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey", "NoSuchKey"
        )
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.file_exists("pm-attachments", "nonexistent.txt")

        assert result is False

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_get_file_info_success(self, mock_settings, mock_minio_class):
        """Test getting file info."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_stat = MagicMock()
        mock_stat.size = 1024
        mock_stat.content_type = "text/plain"
        mock_stat.last_modified = "2024-01-01"
        mock_stat.etag = "abc123"

        mock_client = MagicMock()
        mock_client.stat_object.return_value = mock_stat
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.get_file_info("pm-attachments", "test/file.txt")

        assert result["size"] == 1024
        assert result["content_type"] == "text/plain"
        assert result["etag"] == "abc123"


class TestMinIOServiceHelpers:
    """Tests for helper methods."""

    def test_generate_object_name(self):
        """Test object name generation."""
        service = MinIOService()
        result = service.generate_object_name("task", "12345", "document.pdf")

        assert result.startswith("task/12345/")
        assert result.endswith("_document.pdf")
        assert len(result.split("/")) == 3

    def test_generate_object_name_cleans_filename(self):
        """Test that object name generation cleans filenames."""
        service = MinIOService()
        result = service.generate_object_name("task", "12345", "path/to/file.pdf")

        assert "path_to_file.pdf" in result
        assert "//" not in result

    def test_get_bucket_for_content_type_image(self):
        """Test bucket selection for images."""
        service = MinIOService()

        assert service.get_bucket_for_content_type("image/png") == "pm-images"
        assert service.get_bucket_for_content_type("image/jpeg") == "pm-images"
        assert service.get_bucket_for_content_type("image/gif") == "pm-images"

    def test_get_bucket_for_content_type_other(self):
        """Test bucket selection for non-images."""
        service = MinIOService()

        assert service.get_bucket_for_content_type("application/pdf") == "pm-attachments"
        assert service.get_bucket_for_content_type("text/plain") == "pm-attachments"
        assert service.get_bucket_for_content_type(None) == "pm-attachments"


class TestMinIOServiceList:
    """Tests for list operations."""

    @patch("app.services.minio_service.Minio")
    @patch("app.services.minio_service.settings")
    def test_list_objects_success(self, mock_settings, mock_minio_class):
        """Test listing objects."""
        mock_settings.minio_endpoint = "localhost:9000"
        mock_settings.minio_access_key = "access"
        mock_settings.minio_secret_key = "secret"
        mock_settings.minio_secure = False

        mock_obj = MagicMock()
        mock_obj.object_name = "test/file.txt"
        mock_obj.size = 1024
        mock_obj.last_modified = "2024-01-01"
        mock_obj.etag = "abc123"
        mock_obj.is_dir = False

        mock_client = MagicMock()
        mock_client.list_objects.return_value = [mock_obj]
        mock_minio_class.return_value = mock_client

        service = MinIOService()
        result = service.list_objects("pm-attachments", prefix="test/")

        assert len(result) == 1
        assert result[0]["name"] == "test/file.txt"
        assert result[0]["size"] == 1024
