"""Business logic services."""

from .auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    get_user_by_email,
    verify_password,
)
from .minio_service import (
    MinIOService,
    MinIOServiceError,
    get_minio_service,
    minio_service,
)
from .notification_service import (
    NotificationService,
    create_notification,
    notify_comment_added,
    notify_mentioned,
    notify_task_assigned,
    notify_task_status_changed,
)
from .status_derivation_service import (
    ProjectAggregation,
    derive_project_status,
    derive_project_status_from_model,
)
from .permission_service import (
    PermissionService,
    get_permission_service,
)

__all__ = [
    # Auth service
    "authenticate_user",
    "create_access_token",
    "create_user",
    "get_current_user",
    "get_user_by_email",
    "verify_password",
    # MinIO service
    "MinIOService",
    "MinIOServiceError",
    "get_minio_service",
    "minio_service",
    # Notification service
    "NotificationService",
    "create_notification",
    "notify_comment_added",
    "notify_mentioned",
    "notify_task_assigned",
    "notify_task_status_changed",
    # Status derivation service
    "ProjectAggregation",
    "derive_project_status",
    "derive_project_status_from_model",
    # Permission service
    "PermissionService",
    "get_permission_service",
]
