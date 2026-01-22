"""Comment service for task comments and mentions.

Provides business logic for:
- Creating, updating, deleting comments
- Extracting @mentions from TipTap JSON
- Generating mention notifications
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ..models.attachment import Attachment
from ..models.comment import Comment
from ..models.mention import Mention
from ..models.task import Task
from ..models.user import User
from ..schemas.comment import CommentCreate, CommentResponse, CommentUpdate


# ============================================================================
# Mention Extraction
# ============================================================================


def extract_mentions_from_tiptap(content_json: Dict[str, Any]) -> List[str]:
    """
    Extract mentioned user IDs from TipTap JSON content.

    TipTap mentions are stored as nodes with type 'mention' and
    attrs containing 'id' (user UUID).

    Args:
        content_json: TipTap JSON document

    Returns:
        List of user ID strings found in mentions
    """
    mentioned_ids: List[str] = []

    def traverse_content(node: Dict[str, Any]) -> None:
        """Recursively traverse TipTap nodes to find mentions."""
        if not isinstance(node, dict):
            return

        # Check if this is a mention node
        if node.get("type") == "mention":
            attrs = node.get("attrs", {})
            user_id = attrs.get("id")
            if user_id and isinstance(user_id, str):
                mentioned_ids.append(user_id)

        # Traverse child content
        content = node.get("content", [])
        if isinstance(content, list):
            for child in content:
                traverse_content(child)

    traverse_content(content_json)
    return mentioned_ids


def extract_plain_text_from_tiptap(content_json: Dict[str, Any]) -> str:
    """
    Extract plain text from TipTap JSON content.

    Args:
        content_json: TipTap JSON document

    Returns:
        Plain text string with mentions replaced by @username
    """
    text_parts: List[str] = []

    def traverse_content(node: Dict[str, Any]) -> None:
        """Recursively traverse TipTap nodes to extract text."""
        if not isinstance(node, dict):
            return

        node_type = node.get("type")

        # Handle text nodes
        if node_type == "text":
            text = node.get("text", "")
            if text:
                text_parts.append(text)
            return

        # Handle mention nodes
        if node_type == "mention":
            attrs = node.get("attrs", {})
            label = attrs.get("label", attrs.get("id", "user"))
            text_parts.append(f"@{label}")
            return

        # Handle paragraph breaks
        if node_type == "paragraph":
            # Add newline before paragraph content (except first)
            if text_parts and not text_parts[-1].endswith("\n"):
                pass  # Don't add extra newlines

        # Traverse child content
        content = node.get("content", [])
        if isinstance(content, list):
            for child in content:
                traverse_content(child)

        # Add newline after paragraphs
        if node_type == "paragraph" and text_parts:
            text_parts.append("\n")

    traverse_content(content_json)
    return "".join(text_parts).strip()


# ============================================================================
# Comment CRUD Operations
# ============================================================================


def create_comment(
    db: Session,
    task_id: UUID,
    author_id: UUID,
    comment_data: CommentCreate,
) -> Tuple[Comment, List[UUID]]:
    """
    Create a new comment with mentions.

    Args:
        db: Database session
        task_id: Task ID to comment on
        author_id: ID of the comment author
        comment_data: Comment creation data

    Returns:
        Tuple of (created comment, list of mentioned user IDs)
    """
    # Parse body_json if it's a dict
    body_json_str = None
    body_text = comment_data.body_text
    mentioned_user_ids: List[UUID] = []

    if comment_data.body_json:
        body_json = comment_data.body_json
        body_json_str = json.dumps(body_json)

        # Extract plain text if not provided
        if not body_text:
            body_text = extract_plain_text_from_tiptap(body_json)

        # Extract mentions
        mention_ids = extract_mentions_from_tiptap(body_json)
        for mid in mention_ids:
            try:
                mentioned_user_ids.append(UUID(mid))
            except ValueError:
                pass  # Skip invalid UUIDs

    # Create comment
    comment = Comment(
        task_id=task_id,
        author_id=author_id,
        body_json=body_json_str,
        body_text=body_text,
        created_at=datetime.utcnow(),
    )
    db.add(comment)
    db.flush()  # Get comment ID

    # Create mention records
    for user_id in set(mentioned_user_ids):  # Deduplicate
        mention = Mention(
            comment_id=comment.id,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(mention)

    # Link attachments to this comment
    if comment_data.attachment_ids:
        db.query(Attachment).filter(
            Attachment.id.in_(comment_data.attachment_ids)
        ).update(
            {
                Attachment.comment_id: comment.id,
                Attachment.entity_type: "comment",
                Attachment.entity_id: comment.id,
            },
            synchronize_session=False,
        )

    db.commit()

    # Expire the comment to force reload of relationships including attachments
    db.expire(comment)

    return comment, list(set(mentioned_user_ids))


def update_comment(
    db: Session,
    comment_id: UUID,
    author_id: UUID,
    comment_data: CommentUpdate,
) -> Optional[Tuple[Comment, List[UUID], List[UUID]]]:
    """
    Update an existing comment.

    Args:
        db: Database session
        comment_id: Comment ID to update
        author_id: ID of the user updating (must be author)
        comment_data: Update data

    Returns:
        Tuple of (updated comment, new mention IDs, removed mention IDs)
        or None if comment not found or unauthorized
    """
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.author_id == author_id,
        Comment.is_deleted == False,
    ).first()

    if not comment:
        return None

    # Track original mentions
    original_mentions = set(m.user_id for m in comment.mentions)
    new_mentions: set[UUID] = set()

    # Update body
    if comment_data.body_json is not None:
        body_json = comment_data.body_json
        comment.body_json = json.dumps(body_json)

        # Extract plain text
        comment.body_text = extract_plain_text_from_tiptap(body_json)

        # Extract new mentions
        mention_ids = extract_mentions_from_tiptap(body_json)
        for mid in mention_ids:
            try:
                new_mentions.add(UUID(mid))
            except ValueError:
                pass

    elif comment_data.body_text is not None:
        comment.body_text = comment_data.body_text

    comment.updated_at = datetime.utcnow()

    # Update mention records
    added_mentions = new_mentions - original_mentions
    removed_mentions = original_mentions - new_mentions

    # Remove old mentions
    if removed_mentions:
        db.query(Mention).filter(
            Mention.comment_id == comment_id,
            Mention.user_id.in_(removed_mentions),
        ).delete(synchronize_session=False)

    # Add new mentions
    for user_id in added_mentions:
        mention = Mention(
            comment_id=comment.id,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.add(mention)

    db.commit()
    db.refresh(comment)

    return comment, list(added_mentions), list(removed_mentions)


def delete_comment(
    db: Session,
    comment_id: UUID,
    author_id: UUID,
    soft_delete: bool = True,
) -> Optional[Comment]:
    """
    Delete a comment (soft delete by default).

    Args:
        db: Database session
        comment_id: Comment ID to delete
        author_id: ID of the user deleting (must be author)
        soft_delete: If True, mark as deleted; if False, hard delete

    Returns:
        The deleted comment or None if not found/unauthorized
    """
    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.author_id == author_id,
        Comment.is_deleted == False,
    ).first()

    if not comment:
        return None

    if soft_delete:
        comment.is_deleted = True
        comment.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(comment)
        return comment
    else:
        db.delete(comment)
        db.commit()
        return comment


def get_comment(
    db: Session,
    comment_id: UUID,
) -> Optional[Comment]:
    """
    Get a comment by ID with author, mentions, and attachments loaded.

    Args:
        db: Database session
        comment_id: Comment ID

    Returns:
        Comment or None if not found
    """
    return db.query(Comment).options(
        joinedload(Comment.author),
        joinedload(Comment.mentions).joinedload(Mention.user),
        joinedload(Comment.attachments),
    ).filter(
        Comment.id == comment_id,
        Comment.is_deleted == False,
    ).first()


def get_comments_for_task(
    db: Session,
    task_id: UUID,
    cursor: Optional[datetime] = None,
    limit: int = 20,
) -> Tuple[List[Comment], Optional[datetime]]:
    """
    Get comments for a task with cursor-based pagination.

    Args:
        db: Database session
        task_id: Task ID to get comments for
        cursor: Datetime cursor for pagination (comments older than this)
        limit: Maximum number of comments to return

    Returns:
        Tuple of (list of comments, next cursor datetime)
    """
    query = db.query(Comment).options(
        joinedload(Comment.author),
        joinedload(Comment.mentions).joinedload(Mention.user),
        joinedload(Comment.attachments),
    ).filter(
        Comment.task_id == task_id,
        Comment.is_deleted == False,
    )

    if cursor:
        query = query.filter(Comment.created_at < cursor)

    # Order by newest first
    query = query.order_by(Comment.created_at.desc())

    comments = query.limit(limit + 1).all()

    # Determine next cursor
    next_cursor = None
    if len(comments) > limit:
        comments = comments[:limit]
        next_cursor = comments[-1].created_at

    return comments, next_cursor


def count_comments_for_task(db: Session, task_id: UUID) -> int:
    """
    Count total comments for a task.

    Args:
        db: Database session
        task_id: Task ID

    Returns:
        Comment count
    """
    return db.query(Comment).filter(
        Comment.task_id == task_id,
        Comment.is_deleted == False,
    ).count()


# ============================================================================
# Response Building
# ============================================================================


def build_comment_response(comment: Comment) -> Dict[str, Any]:
    """
    Build a comment response dictionary.

    Args:
        comment: Comment model instance

    Returns:
        Dictionary matching CommentResponse schema
    """
    # Parse body_json back to dict
    body_json = None
    if comment.body_json:
        try:
            body_json = json.loads(comment.body_json)
        except json.JSONDecodeError:
            pass

    # Build mentions list
    mentions = []
    for mention in comment.mentions:
        mention_data = {
            "id": str(mention.id),
            "user_id": str(mention.user_id),
            "user_name": mention.user.display_name if mention.user else None,
            "created_at": mention.created_at.isoformat(),
        }
        mentions.append(mention_data)

    # Build attachments list
    attachments = []
    if hasattr(comment, 'attachments') and comment.attachments:
        for attachment in comment.attachments:
            attachments.append({
                "id": str(attachment.id),
                "file_name": attachment.file_name,
                "file_type": attachment.file_type,
                "file_size": attachment.file_size,
                "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
            })

    return {
        "id": str(comment.id),
        "task_id": str(comment.task_id),
        "author_id": str(comment.author_id),
        "author_name": comment.author.display_name if comment.author else None,
        "author_avatar_url": comment.author.avatar_url if comment.author else None,
        "body_json": body_json,
        "body_text": comment.body_text,
        "is_deleted": comment.is_deleted,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
        "mentions": mentions,
        "attachments": attachments,
    }
