"""Authentication API endpoints.

Provides endpoints for user registration, login, logout, and profile access.
Uses JWT-based authentication for session management.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..schemas.user import (
    ForgotPasswordRequest,
    Login2FAResponse,
    MessageResponse,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserCreate,
    UserResponse,
    VerifyEmailRequest,
    VerifyLoginRequest,
)
from ..services.auth_service import (
    Token,
    authenticate_user,
    blacklist_token,
    create_access_token,
    create_user,
    decode_access_token,
    generate_and_send_login_code,
    get_current_user,
    request_password_reset,
    resend_verification_code,
    reset_password,
    verify_email_code,
    verify_login_code,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email and password. A verification code is sent to the email.",
    responses={
        201: {"description": "User created, verification code sent"},
        400: {"description": "Email already registered or validation error"},
    },
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Register a new user.

    - **email**: Valid email address (unique)
    - **password**: Minimum 8 characters
    - **display_name**: Optional display name

    Returns a message and the email address. A verification code is sent to the email.
    """
    await create_user(db, user_data)
    return RegisterResponse(
        message="Verification code sent to your email",
        email=user_data.email,
    )


@router.post(
    "/login",
    response_model=Login2FAResponse,
    summary="Login with email and password",
    description="Authenticate with email and password. On success, sends a 2FA code to the user's email. Use POST /auth/verify-login to complete login.",
    responses={
        200: {"description": "Credentials valid, 2FA code sent"},
        401: {"description": "Invalid credentials"},
        403: {"description": "Email not verified"},
    },
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> Login2FAResponse:
    """
    Login with email and password.

    Uses OAuth2 password flow with form data:
    - **username**: Email address (OAuth2 spec uses 'username')
    - **password**: User's password

    On valid credentials, generates a 6-digit code sent to the user's
    email. Call POST /auth/verify-login with the code to receive the JWT.
    Calling login again with valid credentials regenerates and resends a new code.
    """
    user = await authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate and send 2FA code
    await generate_and_send_login_code(db, user)

    return Login2FAResponse(email=user.email)


@router.post(
    "/verify-login",
    response_model=Token,
    summary="Verify login 2FA code",
    description="Verify the 6-digit login code sent to the user's email. Returns JWT token on success.",
    responses={
        200: {"description": "Code verified, JWT token returned"},
        400: {"description": "Invalid code, expired, or too many attempts"},
    },
)
async def verify_login(
    data: VerifyLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Verify login 2FA code and return JWT token."""
    user = await verify_login_code(db, data.email, data.code)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return Token(access_token=access_token)


@router.post(
    "/verify-email",
    response_model=Token,
    summary="Verify email with code",
    description="Verify email address with the 6-digit code. Returns JWT token on success (auto-login).",
    responses={
        200: {"description": "Email verified, JWT token returned"},
        400: {"description": "Invalid code, expired, or already verified"},
    },
)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Verify email and return JWT token for auto-login."""
    user = await verify_email_code(db, data.email, data.code)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return Token(access_token=access_token)


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend verification code",
    description="Resend verification code to email. Subject to 60-second cooldown.",
    responses={
        200: {"description": "Verification code resent"},
        429: {"description": "Cooldown period active"},
    },
)
async def resend_verification(
    data: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Resend verification code to the user's email."""
    await resend_verification_code(db, data.email)
    return MessageResponse(message="If the email is registered and unverified, a new code has been sent")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset",
    description="Send a password reset code to the email. Always returns 200 to prevent email enumeration.",
    responses={
        200: {"description": "Reset code sent (if email exists)"},
    },
)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request a password reset code."""
    await request_password_reset(db, data.email)
    return MessageResponse(message="If the email exists, a reset code has been sent")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password with code",
    description="Reset password using the 6-digit code from email.",
    responses={
        200: {"description": "Password reset successful"},
        400: {"description": "Invalid code, expired, or user not found"},
    },
)
async def reset_password_endpoint(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Reset password with verification code."""
    await reset_password(db, data.email, data.code, data.new_password)
    return MessageResponse(message="Password reset successful. Please log in with your new password.")


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout current user",
    description="Invalidate the current session. Client should discard the token.",
    responses={
        200: {"description": "Successfully logged out"},
        401: {"description": "Not authenticated"},
    },
)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Logout the current user.

    Blacklists the JWT token in Redis so it cannot be reused.
    The client should also discard the stored access token.
    """
    # Extract raw token from Authorization header and blacklist its JTI
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
        token_data = decode_access_token(raw_token)
        if token_data and token_data.jti and token_data.exp:
            await blacklist_token(token_data.jti, token_data.exp)

    return MessageResponse(message="Successfully logged out")


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
