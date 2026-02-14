"""MinIO service for file storage operations.

This service provides file upload, download, and management capabilities
using MinIO object storage. It handles bucket creation, presigned URLs,
and file metadata operations.
"""

import io
from datetime import timedelta
from typing import BinaryIO, Optional
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from ..config import settings


class MinIOServiceError(Exception):
    """Custom exception for MinIO service errors."""

    pass


class MinIOService:
    """
    Service for interacting with MinIO object storage.

    Provides methods for file upload, download, deletion, and URL generation.
    Automatically creates required buckets on initialization.
    """

    # Default bucket names
    ATTACHMENTS_BUCKET = "pm-attachments"
    IMAGES_BUCKET = "pm-images"

    # Default URL expiration
    DEFAULT_URL_EXPIRY = timedelta(hours=1)
    UPLOAD_URL_EXPIRY = timedelta(hours=2)

    def __init__(self):
        """Initialize MinIO client with settings from configuration."""
        self._client: Optional[Minio] = None
        self._initialized = False

    @property
    def client(self) -> Minio:
        """
        Get the MinIO client instance, creating it if necessary.

        Returns:
            Minio client instance

        Raises:
            MinIOServiceError: If client creation fails
        """
        if self._client is None:
            try:
                self._client = Minio(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure,
                )
            except Exception as e:
                raise MinIOServiceError(f"Failed to create MinIO client: {str(e)}")
        return self._client

    def ensure_buckets_exist(self) -> None:
        """
        Ensure all required buckets exist, creating them if necessary.

        Creates the following buckets:
        - pm-attachments: For general file attachments
        - pm-images: For image files

        Raises:
            MinIOServiceError: If bucket creation fails
        """
        if self._initialized:
            return

        buckets = [self.ATTACHMENTS_BUCKET, self.IMAGES_BUCKET]

        for bucket in buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
            except S3Error as e:
                raise MinIOServiceError(
                    f"Failed to create bucket '{bucket}': {str(e)}"
                )

        self._initialized = True

    def upload_file(
        self,
        bucket: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to MinIO.

        Args:
            bucket: Name of the bucket to upload to
            object_name: Object key (path) in the bucket
            data: File-like object containing the data
            length: Size of the data in bytes
            content_type: MIME type of the file

        Returns:
            The object name (key) of the uploaded file

        Raises:
            MinIOServiceError: If upload fails
        """
        self.ensure_buckets_exist()

        try:
            self.client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
            )
            return object_name
        except S3Error as e:
            raise MinIOServiceError(f"Failed to upload file: {str(e)}")

    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload bytes data to MinIO.

        Args:
            bucket: Name of the bucket to upload to
            object_name: Object key (path) in the bucket
            data: Bytes data to upload
            content_type: MIME type of the file

        Returns:
            The object name (key) of the uploaded file

        Raises:
            MinIOServiceError: If upload fails
        """
        return self.upload_file(
            bucket=bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def download_file(self, bucket: str, object_name: str) -> bytes:
        """
        Download a file from MinIO.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket

        Returns:
            The file contents as bytes

        Raises:
            MinIOServiceError: If download fails
        """
        try:
            response = self.client.get_object(bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            raise MinIOServiceError(f"Failed to download file: {str(e)}")

    def delete_file(self, bucket: str, object_name: str) -> bool:
        """
        Delete a file from MinIO.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket

        Returns:
            True if deletion was successful

        Raises:
            MinIOServiceError: If deletion fails
        """
        try:
            self.client.remove_object(bucket, object_name)
            return True
        except S3Error as e:
            raise MinIOServiceError(f"Failed to delete file: {str(e)}")

    def get_presigned_download_url(
        self,
        bucket: str,
        object_name: str,
        expiry: Optional[timedelta] = None,
    ) -> str:
        """
        Generate a presigned URL for downloading a file.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket
            expiry: URL expiration time (default: 1 hour)

        Returns:
            Presigned URL string

        Raises:
            MinIOServiceError: If URL generation fails
        """
        if expiry is None:
            expiry = self.DEFAULT_URL_EXPIRY

        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket,
                object_name=object_name,
                expires=expiry,
            )
            return url
        except S3Error as e:
            raise MinIOServiceError(f"Failed to generate download URL: {str(e)}")

    def get_presigned_upload_url(
        self,
        bucket: str,
        object_name: str,
        expiry: Optional[timedelta] = None,
    ) -> str:
        """
        Generate a presigned URL for uploading a file.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket
            expiry: URL expiration time (default: 2 hours)

        Returns:
            Presigned URL string

        Raises:
            MinIOServiceError: If URL generation fails
        """
        if expiry is None:
            expiry = self.UPLOAD_URL_EXPIRY

        try:
            url = self.client.presigned_put_object(
                bucket_name=bucket,
                object_name=object_name,
                expires=expiry,
            )
            return url
        except S3Error as e:
            raise MinIOServiceError(f"Failed to generate upload URL: {str(e)}")

    def file_exists(self, bucket: str, object_name: str) -> bool:
        """
        Check if a file exists in MinIO.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.client.stat_object(bucket, object_name)
            return True
        except S3Error:
            return False

    def get_file_info(self, bucket: str, object_name: str) -> dict:
        """
        Get metadata information about a file.

        Args:
            bucket: Name of the bucket
            object_name: Object key (path) in the bucket

        Returns:
            Dictionary containing file metadata:
            - size: File size in bytes
            - content_type: MIME type
            - last_modified: Last modification timestamp
            - etag: Entity tag (checksum)

        Raises:
            MinIOServiceError: If file doesn't exist or operation fails
        """
        try:
            stat = self.client.stat_object(bucket, object_name)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "etag": stat.etag,
            }
        except S3Error as e:
            raise MinIOServiceError(f"Failed to get file info: {str(e)}")

    def generate_object_name(
        self,
        entity_type: str,
        entity_id: str,
        filename: str,
    ) -> str:
        """
        Generate a unique object name (key) for a file.

        Creates a structured path: {entity_type}/{entity_id}/{uuid}_{filename}

        Args:
            entity_type: Type of entity (task, note, comment)
            entity_id: ID of the parent entity
            filename: Original filename

        Returns:
            Generated object name string
        """
        unique_id = str(uuid4())[:8]
        # Clean the filename to remove any path separators
        clean_filename = filename.replace("/", "_").replace("\\", "_")
        return f"{entity_type}/{entity_id}/{unique_id}_{clean_filename}"

    def get_bucket_for_content_type(self, content_type: str) -> str:
        """
        Determine the appropriate bucket based on content type.

        Args:
            content_type: MIME type of the file

        Returns:
            Bucket name (pm-images for images, pm-attachments for others)
        """
        if content_type and content_type.startswith("image/"):
            return self.IMAGES_BUCKET
        return self.ATTACHMENTS_BUCKET

    def list_objects(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        recursive: bool = True,
    ) -> list:
        """
        List objects in a bucket with optional prefix filter.

        Args:
            bucket: Name of the bucket
            prefix: Optional prefix to filter objects
            recursive: Whether to list recursively (default: True)

        Returns:
            List of dictionaries containing object information

        Raises:
            MinIOServiceError: If listing fails
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket,
                prefix=prefix,
                recursive=recursive,
            )
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag,
                    "is_dir": obj.is_dir,
                }
                for obj in objects
            ]
        except S3Error as e:
            raise MinIOServiceError(f"Failed to list objects: {str(e)}")

    def copy_object(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str,
    ) -> str:
        """
        Copy an object from one location to another.

        Args:
            source_bucket: Source bucket name
            source_object: Source object key
            dest_bucket: Destination bucket name
            dest_object: Destination object key

        Returns:
            Destination object name

        Raises:
            MinIOServiceError: If copy fails
        """
        from minio.commonconfig import CopySource

        try:
            self.client.copy_object(
                bucket_name=dest_bucket,
                object_name=dest_object,
                source=CopySource(source_bucket, source_object),
            )
            return dest_object
        except S3Error as e:
            raise MinIOServiceError(f"Failed to copy object: {str(e)}")


# Global service instance
minio_service = MinIOService()


def get_minio_service() -> MinIOService:
    """
    FastAPI dependency for getting the MinIO service instance.

    Returns:
        MinIO service instance
    """
    return minio_service
