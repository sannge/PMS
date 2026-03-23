"""Authentication service with JWT token generation and user management."""

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import make_transient

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..utils.tasks import fire_and_forget
from ..schemas.user import UserCreate
from ..utils.security import get_password_hash, verify_password
from ..utils.timezone import utc_now
from .email_service import (
    generate_verification_code,
    send_login_code_email,
    send_password_reset_email,
    send_verification_email,
)
from .user_cache_service import (
    CachedUser,
    get_cached_user_with_l2,
    invalidate_user_with_l2,
    publish_user_cache_invalidation,
    set_cached_user_with_l2,
)

logger = logging.getLogger(__name__)

# OAuth2 scheme for token-based authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _hash_code(code: str) -> str:
    """Hash a verification/reset code with SHA-256 for secure storage."""
    return hashlib.sha256(code.encode()).hexdigest()


class Token(BaseModel):
    """Token response schema."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data schema."""

    user_id: Optional[str] = None
    email: Optional[str] = None
    jti: Optional[str] = None
    exp: Optional[datetime] = None


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary of claims to encode in the token
        expires_delta: Optional custom expiration time delta

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    # Set expiration time
    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=settings.jwt_access_expiration_minutes)

    # Add unique token ID for blacklist support
    to_encode.update({"exp": expire, "jti": uuid4().hex})

    # Encode the JWT token
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return encoded_jwt


def _refresh_secret() -> str:
    """Return the secret used for refresh tokens (falls back to jwt_secret)."""
    return settings.jwt_refresh_secret or settings.jwt_secret


def create_refresh_token(user_id: str, email: str) -> str:
    """Create a long-lived JWT refresh token with type claim.

    Uses a separate secret (jwt_refresh_secret) so that access tokens
    cannot be used as refresh tokens and vice versa.

    Args:
        user_id: The user's UUID as a string.
        email: The user's email.

    Returns:
        Encoded JWT refresh token string.
    """
    expire = utc_now() + timedelta(days=settings.jwt_refresh_expiration_days)
    to_encode = {
        "sub": user_id,
        "email": email,
        "type": "refresh",
        "exp": expire,
        "jti": uuid4().hex,
    }
    return jwt.encode(
        to_encode,
        _refresh_secret(),
        algorithm=settings.jwt_algorithm,
    )


def validate_refresh_token(token: str) -> Optional[TokenData]:
    """Decode and validate a refresh token.

    Verifies the ``type`` claim is ``"refresh"`` and decodes with the
    refresh-specific secret.

    Returns:
        TokenData on success, None if invalid.
    """
    try:
        payload = jwt.decode(
            token,
            _refresh_secret(),
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "refresh":
            return None
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        exp_timestamp = payload.get("exp")
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else None
        return TokenData(
            user_id=user_id,
            email=payload.get("email"),
            jti=payload.get("jti"),
            exp=exp_dt,
        )
    except JWTError:
        return None


async def rotate_refresh_token(
    old_refresh_token: str,
) -> Optional[tuple[str, str]]:
    """Blacklist the old refresh token and issue a new access + refresh pair.

    Args:
        old_refresh_token: The current refresh token to rotate.

    Returns:
        ``(new_access_token, new_refresh_token)`` on success, or None.
    """
    token_data = validate_refresh_token(old_refresh_token)
    if token_data is None or token_data.user_id is None:
        return None

    # Check blacklist
    if token_data.jti and await is_token_blacklisted(token_data.jti):
        return None

    # Blacklist the old refresh token
    if token_data.jti and token_data.exp:
        await blacklist_token(token_data.jti, token_data.exp)

    # Issue new pair
    new_access = create_access_token(data={"sub": token_data.user_id, "email": token_data.email})
    new_refresh = create_refresh_token(token_data.user_id, token_data.email or "")
    return (new_access, new_refresh)


async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """Add a token's JTI to the Redis blacklist so it is rejected on future use.

    The Redis key is set with a TTL matching the token's remaining lifetime
    so blacklist entries are automatically cleaned up after expiry.

    Args:
        jti: The unique JWT ID claim.
        expires_at: Token expiration datetime (used to compute TTL).
    """
    from .redis_service import redis_service

    if not redis_service.is_connected:
        logger.warning("Redis unavailable — token blacklist not persisted for jti=%s", jti)
        return

    ttl_seconds = int((expires_at - utc_now()).total_seconds())
    if ttl_seconds <= 0:
        return  # Already expired, no need to blacklist

    try:
        await redis_service.set(f"token_blacklist:{jti}", "1", ttl=ttl_seconds)
    except Exception:
        logger.warning("Failed to blacklist token jti=%s", jti, exc_info=True)


async def is_token_blacklisted(jti: str) -> bool:
    """Check whether a token JTI has been blacklisted.

    When redis_required=True (production multi-worker deployment):
        Fail-closed — returns True if Redis is unavailable, forcing
        re-authentication rather than allowing revoked tokens through.

    When redis_required=False (dev/single-server):
        Fail-open — returns False if Redis is unavailable to avoid
        locking out all users during development.
    """
    from .redis_service import redis_service
    from ..config import settings

    if not redis_service.is_connected:
        if settings.redis_required:
            logger.warning(
                "SECURITY: Redis unavailable — token blacklist fail-closed for jti=%s",
                jti,
            )
            return True
        else:
            logger.warning(
                "Redis unavailable — token blacklist check skipped (redis_required=False) for jti=%s",
                jti,
            )
            return False

    try:
        result = await redis_service.get(f"token_blacklist:{jti}")
        return result is not None
    except Exception:
        if settings.redis_required:
            logger.warning(
                "SECURITY: Failed to check token blacklist (fail-closed) for jti=%s",
                jti,
                exc_info=True,
            )
            return True
        else:
            logger.warning(
                "Failed to check token blacklist (fail-open, redis_required=False) for jti=%s",
                jti,
                exc_info=True,
            )
            return False


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode

    Returns:
        TokenData with user information, or None if invalid

    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        jti: str = payload.get("jti")
        exp_timestamp = payload.get("exp")

        if user_id is None:
            return None

        exp_dt = None
        if exp_timestamp is not None:
            exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

        return TokenData(user_id=user_id, email=email, jti=jti, exp=exp_dt)
    except JWTError:
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Get a user by their email address.

    Args:
        db: Database session
        email: Email address to search for

    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(select(User).where(func.lower(User.email) == func.lower(email)))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """
    Get a user by their ID.

    Args:
        db: Database session
        user_id: User UUID to search for

    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user with email and password.

    Args:
        db: Database session
        email: User's email address
        password: Plain text password to verify

    Returns:
        User object if authentication successful, None otherwise

    Raises:
        HTTPException: 403 if email is not verified
    """
    user = await get_user_by_email(db, email)

    if not user:
        # Dummy verify to prevent timing-based user enumeration
        verify_password(password, "$2b$12$LJ3m4ys3Lg3Dlw9PjXnqKeDKFJb6QXHX6TqGQnKqHqHqHqHqHqHq")
        return None

    if not verify_password(password, user.password_hash):
        return None

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email first.",
        )

    return user


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    """
    Create a new user in the database with a verification code.

    Args:
        db: Database session
        user_data: User creation data including password

    Returns:
        Created User object (email_verified=False)

    Raises:
        HTTPException: If email already exists
    """
    # Check if user already exists — generic error to prevent email enumeration
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please check your details and try again.",
        )

    # Hash the password
    hashed_password = get_password_hash(user_data.password)

    # Generate verification code
    code = generate_verification_code()
    code_expires_at = utc_now() + timedelta(minutes=settings.email_verification_code_expiry_minutes)

    # Create user instance
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        display_name=user_data.display_name,
        email_verified=False,
        verification_code=_hash_code(code),
        verification_code_expires_at=code_expires_at,
    )

    # Add to database
    try:
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please check your details and try again.",
        )

    # Send verification email (fire-and-forget, don't block response)
    fire_and_forget(send_verification_email(user_data.email, code))

    return db_user


async def verify_email_code(db: AsyncSession, email: str, code: str) -> User:
    """
    Verify a user's email with the provided code.

    Args:
        db: Database session
        email: User's email address
        code: 6-digit verification code

    Returns:
        Verified User object

    Raises:
        HTTPException: If user not found, already verified, code invalid/expired
    """
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or code",
        )

    if user.email_verified:
        # L9: Reject already-verified accounts instead of returning tokens
        # without code validation.  Prevents bypassing verification.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified.",
        )

    if not user.verification_code or not user.verification_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found. Please request a new one.",
        )

    if utc_now() > user.verification_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new one.",
        )

    # Track failed attempts - clear code after 5 failures
    if not secrets.compare_digest(_hash_code(code), user.verification_code):
        user.verification_attempts = (user.verification_attempts or 0) + 1
        if user.verification_attempts >= 5:
            user.verification_code = None
            user.verification_code_expires_at = None
            user.verification_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Please request a new code.",
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    # Mark as verified and clear code
    user.email_verified = True
    user.verification_code = None
    user.verification_code_expires_at = None
    user.verification_attempts = 0
    await db.commit()
    await db.refresh(user)

    await invalidate_user_with_l2(user.id)
    fire_and_forget(
        publish_user_cache_invalidation(user_id=str(user.id)),
        name="verify-email-user-cache-invalidation",
    )

    return user


async def resend_verification_code(db: AsyncSession, email: str) -> None:
    """
    Resend a verification code, enforcing a cooldown period.

    Args:
        db: Database session
        email: User's email address

    Raises:
        HTTPException: If user not found, already verified, or cooldown active
    """
    user = await get_user_by_email(db, email)
    if not user:
        # Don't reveal whether email exists
        return

    if user.email_verified:
        # Don't reveal verification status
        return

    # Enforce cooldown: code_expires_at - expiry_minutes = when code was sent
    if user.verification_code_expires_at:
        code_sent_at = user.verification_code_expires_at - timedelta(
            minutes=settings.email_verification_code_expiry_minutes
        )
        cooldown_ends = code_sent_at + timedelta(seconds=settings.email_verification_resend_cooldown_seconds)
        if utc_now() < cooldown_ends:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait before requesting a new code",
            )

    # Generate new code
    code = generate_verification_code()
    user.verification_code = _hash_code(code)
    user.verification_code_expires_at = utc_now() + timedelta(minutes=settings.email_verification_code_expiry_minutes)
    user.verification_attempts = 0
    await db.commit()

    fire_and_forget(send_verification_email(email, code))


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """
    Request a password reset code. Always returns success to prevent email enumeration.

    Args:
        db: Database session
        email: User's email address

    Raises:
        HTTPException: 400 if user exists but email is not verified
    """
    user = await get_user_by_email(db, email)
    if not user:
        # Don't reveal whether email exists
        return

    if not user.email_verified:
        # Don't reveal verification status
        return

    # Enforce cooldown
    if user.password_reset_code_expires_at:
        code_sent_at = user.password_reset_code_expires_at - timedelta(
            minutes=settings.password_reset_code_expiry_minutes
        )
        cooldown_ends = code_sent_at + timedelta(seconds=settings.email_verification_resend_cooldown_seconds)
        if utc_now() < cooldown_ends:
            # Silently return (don't reveal timing info)
            return

    code = generate_verification_code()
    user.password_reset_code = _hash_code(code)
    user.password_reset_code_expires_at = utc_now() + timedelta(minutes=settings.password_reset_code_expiry_minutes)
    user.reset_attempts = 0
    await db.commit()

    fire_and_forget(send_password_reset_email(email, code))


async def generate_and_send_login_code(db: AsyncSession, user: User) -> None:
    """Generate a 6-digit login 2FA code, hash it, store it, and email it.

    Reuses the verification_code/verification_code_expires_at columns on
    the User model, which are NULL after registration verification completes.
    Calling login again overwrites any previous code (acts as "resend").

    Args:
        db: Database session.
        user: The authenticated user who needs a 2FA code.
    """
    code = generate_verification_code()
    user.verification_code = _hash_code(code)
    user.verification_code_expires_at = utc_now() + timedelta(minutes=settings.email_verification_code_expiry_minutes)
    user.verification_attempts = 0
    await db.commit()

    fire_and_forget(send_login_code_email(user.email, code))


async def verify_login_code(db: AsyncSession, email: str, code: str) -> User:
    """Verify a login 2FA code.

    Validates the hashed code, checks expiry, tracks failed attempts
    (clears after 5), and clears the code columns on success.

    Args:
        db: Database session.
        email: User's email address.
        code: 6-digit verification code.

    Returns:
        The verified User object.

    Raises:
        HTTPException: If user not found, code invalid/expired, or too many attempts.
    """
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or code",
        )

    if not user.verification_code or not user.verification_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found. Please log in again.",
        )

    if utc_now() > user.verification_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please log in again.",
        )

    if not secrets.compare_digest(_hash_code(code), user.verification_code):
        user.verification_attempts = (user.verification_attempts or 0) + 1
        if user.verification_attempts >= 5:
            user.verification_code = None
            user.verification_code_expires_at = None
            user.verification_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Please log in again.",
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    # Success: clear code columns
    user.verification_code = None
    user.verification_code_expires_at = None
    user.verification_attempts = 0
    await db.commit()
    await db.refresh(user)

    return user


async def reset_password(db: AsyncSession, email: str, code: str, new_password: str) -> None:
    """
    Reset a user's password with the provided code.

    Args:
        db: Database session
        email: User's email address
        code: 6-digit reset code
        new_password: New password to set

    Raises:
        HTTPException: If code invalid, expired, or user not found
    """
    user = await get_user_by_email(db, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or code",
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or code",
        )

    if not user.password_reset_code or not user.password_reset_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reset code found. Please request a new one.",
        )

    if utc_now() > user.password_reset_code_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset code has expired. Please request a new one.",
        )

    # Track failed attempts - clear code after 5 failures
    if not secrets.compare_digest(_hash_code(code), user.password_reset_code):
        user.reset_attempts = (user.reset_attempts or 0) + 1
        if user.reset_attempts >= 5:
            user.password_reset_code = None
            user.password_reset_code_expires_at = None
            user.reset_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Please request a new code.",
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset code",
        )

    # Update password and clear reset code
    user.password_hash = get_password_hash(new_password)
    user.password_reset_code = None
    user.password_reset_code_expires_at = None
    user.reset_attempts = 0
    await db.commit()

    await invalidate_user_with_l2(user.id)
    fire_and_forget(
        publish_user_cache_invalidation(user_id=str(user.id)),
        name="password-reset-user-cache-invalidation",
    )


def _user_from_cache(cached: CachedUser) -> User:
    """
    Create a User-like object from cache without ORM session.

    This creates a transient User instance that can be used for
    authentication checks without requiring database queries.
    The object is not bound to any session.

    WARNING: The returned User is detached from any session. Accessing
    ORM relationships (e.g. user.applications, user.members) will raise
    DetachedInstanceError. Only scalar column attributes are safe to read.

    Args:
        cached: The cached user data

    Returns:
        A User instance with essential fields populated
    """
    # Create User using normal constructor (makes it a transient ORM object)
    user = User(
        id=cached.id,
        email=cached.email,
        password_hash="",  # Empty placeholder - not used for auth checks
        display_name=cached.display_name,
        avatar_url=cached.avatar_url,
        email_verified=cached.email_verified,
        is_developer=cached.is_developer,
    )
    # Mark as transient (not associated with any session)
    make_transient(user)
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from the JWT token.

    This is a FastAPI dependency that extracts and validates
    the JWT token from the Authorization header. Uses in-memory
    cache to reduce database queries for high concurrency.

    Args:
        token: JWT token from Authorization header
        db: Database session

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode the token
    token_data = decode_access_token(token)
    if token_data is None or token_data.user_id is None:
        raise credentials_exception

    # Check token blacklist (logout support)
    if token_data.jti:
        if await is_token_blacklisted(token_data.jti):
            raise credentials_exception

    # Get the user from database
    try:
        user_id = UUID(token_data.user_id)
    except ValueError:
        raise credentials_exception

    # Check L1 + L2 cache
    cached = await get_cached_user_with_l2(user_id)
    if cached:
        return _user_from_cache(cached)

    # Cache miss - query database
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception

    # Populate L1 + L2 cache for future requests
    await set_cached_user_with_l2(user)

    return user


async def create_ws_connection_token(user_id: str) -> str:
    """Generate a short-lived opaque connection token for WebSocket auth.

    Stored in Redis with 30-second TTL. Single-use: consumed on first validation.

    Args:
        user_id: The user's UUID as a string.

    Returns:
        Opaque hex token.
    """
    from .redis_service import redis_service

    token = secrets.token_hex(32)
    key = f"ws_conn_token:{token}"
    await redis_service.set(key, user_id, ttl=30)
    return token


async def validate_ws_connection_token(token: str) -> Optional[str]:
    """Validate and consume a WebSocket connection token.

    Returns the user_id if valid, None otherwise. The token is deleted on
    first use (single-use).

    Args:
        token: The opaque connection token.

    Returns:
        user_id string if valid, None otherwise.
    """
    from .redis_service import redis_service

    if not redis_service.is_connected:
        return None

    key = f"ws_conn_token:{token}"
    try:
        # Atomic GET+DELETE via pipeline to support Redis < 6.2
        async with redis_service.client.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            results = await pipe.execute()
        user_id = results[0]
        if user_id:
            # Redis returns bytes; decode to str
            return user_id.decode() if isinstance(user_id, bytes) else user_id
    except Exception:
        logger.warning("Failed to validate WS connection token", exc_info=True)
    return None
