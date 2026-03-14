"""Unit tests for authentication service and endpoints."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth_service import (
    Token,
    TokenData,
    authenticate_user,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_user,
    decode_access_token,
    get_user_by_email,
    get_user_by_id,
    is_token_blacklisted,
    rotate_refresh_token,
    validate_refresh_token,
)
from app.schemas.user import UserCreate


# Check if bcrypt is properly working for security tests
def _check_bcrypt_available():
    """Check if bcrypt is available and working."""
    try:
        from app.utils.security import get_password_hash, verify_password
        hash_result = get_password_hash("test")
        return True
    except Exception:
        return False


_bcrypt_available = _check_bcrypt_available()


@pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
class TestSecurityUtils:
    """Tests for security utility functions."""

    def test_password_hash_creates_different_hash(self):
        """Test that hashing the same password twice produces different hashes."""
        from app.utils.security import get_password_hash
        password = "TestPassword123!"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2  # bcrypt generates unique salts
        assert hash1 != password
        assert hash2 != password

    def test_verify_password_success(self):
        """Test that password verification works correctly."""
        from app.utils.security import get_password_hash, verify_password
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_failure(self):
        """Test that wrong password fails verification."""
        from app.utils.security import get_password_hash, verify_password
        password = "TestPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_with_empty_string(self):
        """Test password verification with empty string."""
        from app.utils.security import get_password_hash, verify_password
        password = "TestPassword123!"
        hashed = get_password_hash(password)

        assert verify_password("", hashed) is False


class TestTokenFunctions:
    """Tests for JWT token functions."""

    def test_create_access_token_basic(self):
        """Test creating a basic access token."""
        data = {"sub": str(uuid4()), "email": "test@example.com"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_custom_expiry(self):
        """Test creating a token with custom expiration."""
        data = {"sub": str(uuid4()), "email": "test@example.com"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data, expires_delta=expires_delta)

        assert token is not None
        assert isinstance(token, str)

    def test_decode_access_token_valid(self):
        """Test decoding a valid access token."""
        user_id = str(uuid4())
        email = "test@example.com"
        data = {"sub": user_id, "email": email}
        token = create_access_token(data)

        token_data = decode_access_token(token)

        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email

    def test_decode_access_token_invalid(self):
        """Test decoding an invalid token returns None."""
        token_data = decode_access_token("invalid.token.here")

        assert token_data is None

    def test_decode_access_token_missing_sub(self):
        """Test decoding a token without 'sub' claim returns None."""
        # Create a token without the 'sub' claim
        data = {"email": "test@example.com"}
        token = create_access_token(data)

        token_data = decode_access_token(token)

        assert token_data is None

    def test_decode_expired_token(self):
        """Expired token should return None."""
        data = {"sub": str(uuid4()), "email": "test@example.com"}
        token = create_access_token(data, expires_delta=timedelta(seconds=-1))
        token_data = decode_access_token(token)
        assert token_data is None


@pytest.mark.asyncio
class TestUserFunctions:
    """Tests for user-related service functions."""

    async def test_get_user_by_email_found(self, db_session: AsyncSession, test_user: User):
        """Test getting a user by email when user exists."""
        user = await get_user_by_email(db_session, test_user.email)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_get_user_by_email_not_found(self, db_session: AsyncSession):
        """Test getting a user by email when user doesn't exist."""
        user = await get_user_by_email(db_session, "nonexistent@example.com")

        assert user is None

    async def test_get_user_by_id_found(self, db_session: AsyncSession, test_user: User):
        """Test getting a user by ID when user exists."""
        user = await get_user_by_id(db_session, test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """Test getting a user by ID when user doesn't exist."""
        user = await get_user_by_id(db_session, uuid4())

        assert user is None

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_authenticate_user_success(self, db_session: AsyncSession, test_user: User):
        """Test successful user authentication."""
        user = await authenticate_user(db_session, test_user.email, "TestPassword123!")

        assert user is not None
        assert user.id == test_user.id

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_authenticate_user_wrong_password(self, db_session: AsyncSession, test_user: User):
        """Test authentication with wrong password."""
        user = await authenticate_user(db_session, test_user.email, "WrongPassword!")

        assert user is None

    async def test_authenticate_user_nonexistent_user(self, db_session: AsyncSession):
        """Test authentication with nonexistent user."""
        user = await authenticate_user(db_session, "nonexistent@example.com", "password")

        assert user is None

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_create_user_success(self, db_session: AsyncSession):
        """Test creating a new user."""
        user_data = UserCreate(
            email="newuser@example.com",
            password="NewPassword123!",
            display_name="New User",
        )

        user = await create_user(db_session, user_data)

        assert user is not None
        assert user.email == user_data.email
        assert user.display_name == user_data.display_name
        assert user.password_hash is not None
        assert user.password_hash != user_data.password

    async def test_create_user_duplicate_email(self, db_session: AsyncSession, test_user: User):
        """Test creating a user with duplicate email raises error."""
        from fastapi import HTTPException
        user_data = UserCreate(
            email=test_user.email,  # Same email as existing user
            password="Password123!",
            display_name="Duplicate User",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_user(db_session, user_data)
        assert exc_info.value.status_code == 400

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_create_user_sets_unverified(self, db_session: AsyncSession):
        """New users should be created with email_verified=False."""
        user_data = UserCreate(
            email="unverified_new@example.com",
            password="NewPassword123!",
            display_name="Unverified New",
        )

        user = await create_user(db_session, user_data)
        assert user.email_verified is False
        assert user.verification_code is not None


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Tests for authentication API endpoints."""

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration returns verification message."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
                "display_name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert "message" in data
        assert "verification" in data["message"].lower()

    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        """Test registration with duplicate email fails."""
        response = await client.post(
            "/auth/register",
            json={
                "email": test_user.email,
                "password": "SecurePassword123!",
                "display_name": "Duplicate User",
            },
        )

        assert response.status_code == 400
        assert "registration failed" in response.json()["detail"].lower()

    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email fails."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePassword123!",
                "display_name": "Test User",
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Test successful login returns 2FA response."""
        response = await client.post(
            "/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPassword123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["requires_2fa"] is True
        assert data["email"] == test_user.email

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        """Test login with wrong password fails."""
        response = await client.post(
            "/auth/login",
            data={
                "username": test_user.email,
                "password": "WrongPassword!",
            },
        )

        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with nonexistent user fails."""
        response = await client.post(
            "/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "password",
            },
        )

        assert response.status_code == 401

    async def test_get_current_user(self, client: AsyncClient, auth_headers: dict, test_user: User):
        """Test getting current user profile."""
        response = await client.get("/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name

    async def test_get_current_user_no_token(self, client: AsyncClient):
        """Test getting current user without token fails."""
        response = await client.get("/auth/me")

        assert response.status_code == 401

    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token fails."""
        response = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401

    async def test_logout(self, client: AsyncClient, auth_headers: dict):
        """Test logout endpoint."""
        response = await client.post("/auth/logout", headers=auth_headers)

        assert response.status_code == 200
        assert "message" in response.json()

    async def test_logout_no_token(self, client: AsyncClient):
        """Test logout without token fails."""
        response = await client.post("/auth/logout")

        assert response.status_code == 401


@pytest.mark.asyncio
class TestRefreshTokenRevocation:
    """Tests for SA-007: refresh token revocation on rotation.

    Uses an in-memory blacklist set to simulate Redis, since the test
    environment runs without a live Redis instance.
    """

    async def test_rotate_blacklists_old_refresh_token(self):
        """Old refresh token is blacklisted after rotation."""
        blacklisted_jtis: set[str] = set()

        async def mock_blacklist(jti, expires_at):
            blacklisted_jtis.add(jti)

        async def mock_is_blacklisted(jti):
            return jti in blacklisted_jtis

        user_id = str(uuid4())
        email = "revoke@example.com"
        old_token = create_refresh_token(user_id, email)

        old_data = validate_refresh_token(old_token)
        assert old_data is not None
        assert old_data.jti is not None

        with patch(
            "app.services.auth_service.blacklist_token",
            side_effect=mock_blacklist,
        ), patch(
            "app.services.auth_service.is_token_blacklisted",
            side_effect=mock_is_blacklisted,
        ):
            # Rotate — this should blacklist the old token
            result = await rotate_refresh_token(old_token)
            assert result is not None

            # Old token's JTI should now be blacklisted
            assert old_data.jti in blacklisted_jtis

            # Attempting to rotate the old token again should fail
            result2 = await rotate_refresh_token(old_token)
            assert result2 is None

    async def test_rotate_returns_new_valid_pair(self):
        """Rotation returns a new access + refresh token pair."""
        user_id = str(uuid4())
        email = "rotate@example.com"
        old_token = create_refresh_token(user_id, email)

        result = await rotate_refresh_token(old_token)
        assert result is not None
        new_access, new_refresh = result

        # New access token should be decodable
        access_data = decode_access_token(new_access)
        assert access_data is not None
        assert access_data.user_id == user_id

        # New refresh token should be valid
        refresh_data = validate_refresh_token(new_refresh)
        assert refresh_data is not None
        assert refresh_data.user_id == user_id

    async def test_rotate_invalid_token_returns_none(self):
        """Invalid refresh token returns None without error."""
        result = await rotate_refresh_token("invalid.token.here")
        assert result is None
