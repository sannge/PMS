"""Business logic services."""

from .auth_service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
    get_user_by_email,
    verify_password,
)
from .user_cache_service import (
    CachedUser,
    clear_all_caches,
    clear_app_role_cache,
    clear_project_role_cache,
    clear_user_cache,
    get_cache_stats,
    get_cached_app_role,
    get_cached_project_role,
    get_cached_user,
    has_cached_project_role,
    invalidate_all_app_roles_for_app,
    invalidate_all_app_roles_for_user,
    invalidate_all_project_roles_for_project,
    invalidate_all_project_roles_for_user,
    invalidate_app_role,
    invalidate_project_role,
    invalidate_user,
    set_cached_app_role,
    set_cached_project_role,
    set_cached_user,
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
from .archive_service import (
    ArchiveService,
    archive_service,
)

__all__ = [
    # Auth service
    "authenticate_user",
    "create_access_token",
    "create_user",
    "get_current_user",
    "get_user_by_email",
    "verify_password",
    # User cache service
    "CachedUser",
    "clear_all_caches",
    "clear_app_role_cache",
    "clear_project_role_cache",
    "clear_user_cache",
    "get_cache_stats",
    "get_cached_app_role",
    "get_cached_project_role",
    "get_cached_user",
    "has_cached_project_role",
    "invalidate_all_app_roles_for_app",
    "invalidate_all_app_roles_for_user",
    "invalidate_all_project_roles_for_project",
    "invalidate_all_project_roles_for_user",
    "invalidate_app_role",
    "invalidate_project_role",
    "invalidate_user",
    "set_cached_app_role",
    "set_cached_project_role",
    "set_cached_user",
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
    # Archive service
    "ArchiveService",
    "archive_service",
]
