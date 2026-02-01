"""DocumentSnapshot SQLAlchemy model for future version history.

This is a placeholder model for Phase 4+ version history (DATA-06).
The table is created now as part of the data foundation so the schema
is ready when snapshot functionality is implemented.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..database import Base

if TYPE_CHECKING:
    from .document import Document
    from .user import User


class DocumentSnapshot(Base):
    """
    DocumentSnapshot model for storing point-in-time document content.

    Placeholder for future version history feature (DATA-06). The table
    schema is established now as part of the data foundation. Snapshots
    will be created automatically (auto-save intervals) and manually
    (user-triggered save points) in Phase 4+.

    Attributes:
        id: Unique identifier (UUID)
        document_id: FK to the parent document
        content_json: Snapshot of TipTap JSON at point in time
        snapshot_type: Type of snapshot (auto, manual, restore)
        created_by: FK to user who triggered the snapshot
        created_at: Timestamp when snapshot was created
    """

    __tablename__ = "DocumentSnapshots"
    __allow_unmapped__ = True

    # Primary key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # Parent document
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("Documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Snapshot content
    content_json = Column(
        Text,
        nullable=True,
    )

    # Snapshot metadata
    snapshot_type = Column(
        String(50),
        nullable=False,
        default="auto",
    )

    # Audit
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("Users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    document = relationship(
        "Document",
        lazy="joined",
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )

    def __repr__(self) -> str:
        """String representation of DocumentSnapshot."""
        return f"<DocumentSnapshot(id={self.id}, document_id={self.document_id}, type={self.snapshot_type})>"
