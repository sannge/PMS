"""Authentication API endpoints.

Provides endpoints for user registration, login, logout, and profile access.
Uses JWT-based authentication for session management.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..schemas.user import UserCreate, UserResponse
from ..services.auth_service import (
    Token,
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email and password.",
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "Email already registered or validation error"},
    },
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user.

    - **email**: Valid email address (unique)
    - **password**: Minimum 8 characters
    - **display_name**: Optional display name

    Returns the created user data (excluding password).
    """
    # create_user handles duplicate email check and raises HTTPException
    user = await create_user(db, user_data)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Login and get access token",
    description="Authenticate with email and password to receive a JWT access token.",
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"},
    },
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Login with email and password.

    Uses OAuth2 password flow with form data:
    - **username**: Email address (OAuth2 spec uses 'username')
    - **password**: User's password

    Returns JWT access token for authenticating subsequent requests.
    """
    user = await authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with user ID and email in payload
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
        }
    )

    return Token(access_token=access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout current user",
    description="Invalidate the current session. Client should discard the token.",
    responses={
        200: {"description": "Successfully logged out"},
        401: {"description": "Not authenticated"},
    },
)
async def logout(
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Logout the current user.

    Since JWT tokens are stateless, this endpoint serves as a confirmation
    that the user intends to logout. The client should:
    1. Discard the stored access token
    2. Redirect to login page

    For enhanced security, token blacklisting can be implemented in the future.
    """
    return {
        "message": "Successfully logged out",
        "user_id": str(current_user.id),
    }


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Get the profile of the currently authenticated user.",
    responses={
        200: {"description": "User profile retrieved successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get the current authenticated user's profile.

    Requires a valid JWT token in the Authorization header.
    Returns the user's public profile data.
    """
    return current_user
