"""Authentication service with JWT token generation and user management."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..schemas.user import UserCreate
from ..utils.security import get_password_hash, verify_password

# OAuth2 scheme for token-based authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Token(BaseModel):
    """Token response schema."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data schema."""

    user_id: Optional[str] = None
    email: Optional[str] = None


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
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )

    to_encode.update({"exp": expire})

    # Encode the JWT token
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return encoded_jwt


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

        if user_id is None:
            return None

        return TokenData(user_id=user_id, email=email)
    except JWTError:
        return None


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Get a user by their email address.

    Args:
        db: Database session
        email: Email address to search for

    Returns:
        User object if found, None otherwise
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: UUID) -> Optional[User]:
    """
    Get a user by their ID.

    Args:
        db: Database session
        user_id: User UUID to search for

    Returns:
        User object if found, None otherwise
    """
    return db.query(User).filter(User.id == user_id).first()


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user with email and password.

    Args:
        db: Database session
        email: User's email address
        password: Plain text password to verify

    Returns:
        User object if authentication successful, None otherwise
    """
    user = get_user_by_email(db, email)

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


def create_user(db: Session, user_data: UserCreate) -> User:
    """
    Create a new user in the database.

    Args:
        db: Database session
        user_data: User creation data including password

    Returns:
        Created User object

    Raises:
        HTTPException: If email already exists
    """
    # Check if user already exists
    existing_user = get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Hash the password
    hashed_password = get_password_hash(user_data.password)

    # Create user instance
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        display_name=user_data.display_name,
    )

    # Add to database
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from the JWT token.

    This is a FastAPI dependency that extracts and validates
    the JWT token from the Authorization header.

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

    # Get the user from database
    try:
        user_id = UUID(token_data.user_id)
    except ValueError:
        raise credentials_exception

    user = get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current active user (can be extended with is_active check).

    Args:
        current_user: Current authenticated user

    Returns:
        Active User object

    Raises:
        HTTPException: If user is inactive (future enhancement)
    """
    # Future: Check if user.is_active is True
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
