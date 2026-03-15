"""FastAPI dependency injection functions."""

from .redis_gate import require_redis

__all__ = ["require_redis"]
