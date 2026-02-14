"""Notification service for creating and delivering notifications.

Provides business logic for notification management, including:
- Creating notifications for various events
- Delivering notifications via WebSocket
- Managing notification read status
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import Notification
from ..models.task import Task
from ..models.user import User
from ..schemas.notification import (
    EntityType,
    NotificationCreate,
    NotificationType,
)
from ..websocket.handlers import handle_notification

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for managing notifications.

    Handles notification creation, delivery via WebSocket,
    and read status management.
    """

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        notification_data: NotificationCreate,
        deliver_realtime: bool = True,
    ) -> Notification:
        """
        Create a notification and optionally deliver it via WebSocket.

        Args:
            db: Database session
            notification_data: Notification data
            deliver_realtime: Whether to send via WebSocket immediately

        Returns:
            Notification: The created notification
        """
        # Create notification instance
        notification = Notification(
            user_id=notification_data.user_id,
            type=notification_data.type.value,
            title=notification_data.title,
            message=notification_data.message,
            entity_type=notification_data.entity_type.value if notification_data.entity_type else None,
            entity_id=notification_data.entity_id,
            is_read=False,
        )

        # Save to database
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        logger.info(
            f"Notification created: id={notification.id}, "
            f"user={notification.user_id}, type={notification.type}"
        )

        # Deliver via WebSocket if requested
        if deliver_realtime:
            await NotificationService._deliver_via_websocket(notification)

        return notification

    @staticmethod
    async def _deliver_via_websocket(notification: Notification) -> int:
        """
        Deliver a notification via WebSocket.

        Args:
            notification: The notification to deliver

        Returns:
            int: Number of connections that received the notification
        """
        notification_payload = {
            "id": str(notification.id),
            "notification_type": notification.type,
            "title": notification.title,
            "message": notification.message,
            "entity_type": notification.entity_type,
            "entity_id": str(notification.entity_id) if notification.entity_id else None,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        }

        return await handle_notification(
            user_id=notification.user_id,
            notification_data=notification_payload,
        )

    @staticmethod
    async def notify_task_assigned(
        db: AsyncSession,
        task: Task,
        assignee: User,
        assigner: User,
    ) -> Optional[Notification]:
        """
        Create notification when a task is assigned to a user.

        Args:
            db: Database session
            task: The task that was assigned
            assignee: The user being assigned
            assigner: The user who made the assignment

        Returns:
            Optional[Notification]: The created notification, or None if self-assign
        """
        # Don't notify if user assigns to themselves
        if assignee.id == assigner.id:
            return None

        notification_data = NotificationCreate(
            user_id=assignee.id,
            type=NotificationType.TASK_ASSIGNED,
            title="New task assigned to you",
            message=f"{assigner.display_name or assigner.email} assigned you to task {task.task_key}: {task.title}",
            entity_type=EntityType.TASK,
            entity_id=task.id,
        )

        return await NotificationService.create_notification(db, notification_data)

    @staticmethod
    async def notify_task_status_changed(
        db: AsyncSession,
        task: Task,
        old_status: str,
        new_status: str,
        changed_by: User,
        notify_users: list[User],
    ) -> list[Notification]:
        """
        Create notifications when a task's status changes.

        Args:
            db: Database session
            task: The task that was updated
            old_status: Previous status
            new_status: New status
            changed_by: User who made the change
            notify_users: List of users to notify

        Returns:
            list[Notification]: List of created notifications
        """
        notifications = []

        for user in notify_users:
            # Don't notify the user who made the change
            if user.id == changed_by.id:
                continue

            notification_data = NotificationCreate(
                user_id=user.id,
                type=NotificationType.STATUS_CHANGE,
                title=f"Task {task.task_key} status changed",
                message=f"{changed_by.display_name or changed_by.email} changed {task.task_key} from {old_status} to {new_status}",
                entity_type=EntityType.TASK,
                entity_id=task.id,
            )

            notification = await NotificationService.create_notification(
                db, notification_data
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    async def notify_mentioned(
        db: AsyncSession,
        mentioned_user: User,
        mentioner: User,
        entity_type: EntityType,
        entity_id: UUID,
        entity_title: str,
        context: str = "",
    ) -> Optional[Notification]:
        """
        Create notification when a user is mentioned.

        Args:
            db: Database session
            mentioned_user: The user who was mentioned
            mentioner: The user who mentioned them
            entity_type: Type of entity (task, note, comment)
            entity_id: ID of the entity
            entity_title: Title/name of the entity
            context: Optional context text

        Returns:
            Optional[Notification]: The created notification, or None if self-mention
        """
        # Don't notify if user mentions themselves
        if mentioned_user.id == mentioner.id:
            return None

        notification_data = NotificationCreate(
            user_id=mentioned_user.id,
            type=NotificationType.MENTION,
            title=f"You were mentioned in {entity_type.value}",
            message=f"{mentioner.display_name or mentioner.email} mentioned you in {entity_title}{': ' + context if context else ''}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

        return await NotificationService.create_notification(db, notification_data)

    @staticmethod
    async def notify_comment_added(
        db: AsyncSession,
        task: Task,
        commenter: User,
        notify_users: list[User],
        comment_preview: str = "",
    ) -> list[Notification]:
        """
        Create notifications when a comment is added to a task.

        Args:
            db: Database session
            task: The task that was commented on
            commenter: User who added the comment
            notify_users: List of users to notify
            comment_preview: Preview text of the comment

        Returns:
            list[Notification]: List of created notifications
        """
        notifications = []

        for user in notify_users:
            # Don't notify the commenter
            if user.id == commenter.id:
                continue

            notification_data = NotificationCreate(
                user_id=user.id,
                type=NotificationType.TASK_COMMENTED,
                title=f"New comment on {task.task_key}",
                message=f"{commenter.display_name or commenter.email} commented on {task.task_key}: {comment_preview[:100]}{'...' if len(comment_preview) > 100 else ''}",
                entity_type=EntityType.TASK,
                entity_id=task.id,
            )

            notification = await NotificationService.create_notification(
                db, notification_data
            )
            notifications.append(notification)

        return notifications

    @staticmethod
    async def notify_due_date_reminder(
        db: AsyncSession,
        task: Task,
        user: User,
        days_until_due: int,
    ) -> Notification:
        """
        Create notification for upcoming task due date.

        Args:
            db: Database session
            task: The task with upcoming due date
            user: The user to notify
            days_until_due: Number of days until due

        Returns:
            Notification: The created notification
        """
        if days_until_due == 0:
            message = f"Task {task.task_key} is due today!"
        elif days_until_due == 1:
            message = f"Task {task.task_key} is due tomorrow"
        else:
            message = f"Task {task.task_key} is due in {days_until_due} days"

        notification_data = NotificationCreate(
            user_id=user.id,
            type=NotificationType.DUE_DATE_REMINDER,
            title=f"Task due soon: {task.task_key}",
            message=message,
            entity_type=EntityType.TASK,
            entity_id=task.id,
        )

        return await NotificationService.create_notification(db, notification_data)

    @staticmethod
    async def notify_system(
        db: AsyncSession,
        user_id: UUID,
        title: str,
        message: str,
        entity_type: Optional[EntityType] = None,
        entity_id: Optional[UUID] = None,
    ) -> Notification:
        """
        Create a system notification.

        Args:
            db: Database session
            user_id: User to notify
            title: Notification title
            message: Notification message
            entity_type: Optional related entity type
            entity_id: Optional related entity ID

        Returns:
            Notification: The created notification
        """
        notification_data = NotificationCreate(
            user_id=user_id,
            type=NotificationType.SYSTEM,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        return await NotificationService.create_notification(db, notification_data)


# Convenience functions for direct use
async def create_notification(
    db: AsyncSession,
    notification_data: NotificationCreate,
    deliver_realtime: bool = True,
) -> Notification:
    """Create a notification. Convenience wrapper for NotificationService."""
    return await NotificationService.create_notification(
        db, notification_data, deliver_realtime
    )


async def notify_task_assigned(
    db: AsyncSession,
    task: Task,
    assignee: User,
    assigner: User,
) -> Optional[Notification]:
    """Notify user of task assignment. Convenience wrapper."""
    return await NotificationService.notify_task_assigned(
        db, task, assignee, assigner
    )


async def notify_task_status_changed(
    db: AsyncSession,
    task: Task,
    old_status: str,
    new_status: str,
    changed_by: User,
    notify_users: list[User],
) -> list[Notification]:
    """Notify users of task status change. Convenience wrapper."""
    return await NotificationService.notify_task_status_changed(
        db, task, old_status, new_status, changed_by, notify_users
    )


async def notify_mentioned(
    db: AsyncSession,
    mentioned_user: User,
    mentioner: User,
    entity_type: EntityType,
    entity_id: UUID,
    entity_title: str,
    context: str = "",
) -> Optional[Notification]:
    """Notify user of mention. Convenience wrapper."""
    return await NotificationService.notify_mentioned(
        db, mentioned_user, mentioner, entity_type, entity_id, entity_title, context
    )


async def notify_comment_added(
    db: AsyncSession,
    task: Task,
    commenter: User,
    notify_users: list[User],
    comment_preview: str = "",
) -> list[Notification]:
    """Notify users of new comment. Convenience wrapper."""
    return await NotificationService.notify_comment_added(
        db, task, commenter, notify_users, comment_preview
    )


async def create_mention_notification(
    db: AsyncSession,
    mentioned_user_id: UUID,
    mentioner_id: UUID,
    task_id: UUID,
    comment_id: UUID,
) -> Optional[Notification]:
    """
    Create a mention notification for a user mentioned in a comment.

    This is a simplified wrapper that fetches the required entities
    and delegates to notify_mentioned.

    Args:
        db: Database session
        mentioned_user_id: ID of the user who was mentioned
        mentioner_id: ID of the user who mentioned them
        task_id: ID of the task the comment is on
        comment_id: ID of the comment containing the mention

    Returns:
        Optional[Notification]: The created notification, or None if self-mention
    """
    # Don't notify if user mentions themselves
    if mentioned_user_id == mentioner_id:
        return None

    # Fetch required entities
    result = await db.execute(select(User).where(User.id == mentioned_user_id))
    mentioned_user = result.scalar_one_or_none()

    result = await db.execute(select(User).where(User.id == mentioner_id))
    mentioner = result.scalar_one_or_none()

    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not mentioned_user or not mentioner or not task:
        logger.warning(
            f"create_mention_notification: Missing entity - "
            f"mentioned_user={mentioned_user_id}, mentioner={mentioner_id}, task={task_id}"
        )
        return None

    return await NotificationService.notify_mentioned(
        db=db,
        mentioned_user=mentioned_user,
        mentioner=mentioner,
        entity_type=EntityType.COMMENT,
        entity_id=comment_id,
        entity_title=f"{task.task_key}: {task.title}",
    )
