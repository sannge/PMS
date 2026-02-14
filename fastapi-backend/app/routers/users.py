"""Users API endpoints.

Provides endpoints for user search and profile management.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..services.auth_service import get_current_user

router = APIRouter(prefix="/api/users", tags=["Users"])


# Response schema for user search (matches frontend expectations)
class UserSearchResponse(BaseModel):
    """User search result for invitation modal"""
    id: UUID
    email: str
    full_name: Optional[str] = None


@router.get(
    "/search",
    response_model=list[UserSearchResponse],
    summary="Search users by email or name",
    description="Search for users to invite to applications. Returns matching users.",
)
async def search_users(
    email: Optional[str] = Query(None, min_length=1, description="Email to search for (partial match)"),
    name: Optional[str] = Query(None, min_length=1, description="Name to search for (partial match)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserSearchResponse]:
    """
    Search for users by email or display name.

    - Searches are case-insensitive partial matches
    - Excludes the current user from results
    - Returns up to `limit` results
    """
    # Build search conditions
    conditions = []
    if email:
        conditions.append(User.email.ilike(f"%{email}%"))
    if name:
        conditions.append(User.display_name.ilike(f"%{name}%"))

    # If no search term provided, return empty
    if not conditions:
        return []

    # Build async query
    stmt = (
        select(User)
        .where(or_(*conditions))
        .where(User.id != current_user.id)
        .limit(limit)
    )

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        UserSearchResponse(
            id=user.id,
            email=user.email,
            full_name=user.display_name,  # Map display_name to full_name for frontend
        )
        for user in users
    ]
