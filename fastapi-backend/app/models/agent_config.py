"""AgentConfiguration model for runtime AI agent settings.

Stores key-value configuration pairs with type metadata, validation
bounds, and audit tracking. Values are loaded into an in-memory cache
at startup and invalidated via Redis pub/sub on updates.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from ..database import Base


class AgentConfiguration(Base):
    """Runtime configuration key-value store for the AI agent.

    Attributes:
        key: Unique config key (e.g. "agent.max_tool_calls").
        value: String-encoded value (parsed by consumers).
        value_type: Expected type: "int", "float", "str", "bool".
        category: Grouping category (e.g. "agent", "rate_limit").
        description: Human-readable description of the setting.
        min_value: Optional minimum bound (for numeric types).
        max_value: Optional maximum bound (for numeric types).
        updated_at: Timestamp of last update.
        updated_by: UUID of the user who last changed this value.
    """

    __tablename__ = "AgentConfigurations"

    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)
    value_type = Column(String(10), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(String(500))
    min_value = Column(String(50))
    max_value = Column(String(50))
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by = Column(UUID(as_uuid=True), ForeignKey("Users.id"))

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('int', 'float', 'str', 'bool')",
            name="ck_agent_config_value_type",
        ),
    )

    def __repr__(self) -> str:
        """String representation of AgentConfiguration."""
        return f"<AgentConfiguration(key={self.key}, value={self.value})>"
