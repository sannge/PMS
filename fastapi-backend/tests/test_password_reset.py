"""Integration tests for password reset flow."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.utils.timezone import utc_now
from tests.conftest import get_test_password_hash


def _hash_code(code: str) -> str:
    """Hash a code with SHA-256, matching auth_service._hash_code."""
    return hashlib.sha256(code.encode()).hexdigest()


def _check_bcrypt_available():
    try:
        from app.utils.security import get_password_hash
        get_password_hash("test")
        return True
    except Exception:
        return False


_bcrypt_available = _check_bcrypt_available()


@pytest.mark.asyncio
class TestPasswordReset:
    """Tests for password reset endpoints."""

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_forgot_password_sends_code(self, client: AsyncClient, test_user: User):
        """Forgot password for verified user should return 200."""
        response = await client.post(
            "/auth/forgot-password",
            json={"email": test_user.email},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_forgot_password_unknown_email(self, client: AsyncClient):
        """Forgot password for unknown email should still return 200 (anti-enumeration)."""
        response = await client.post(
            "/auth/forgot-password",
            json={"email": "unknown@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_forgot_password_unverified_user(self, client: AsyncClient, db_session: AsyncSession):
        """Forgot password for unverified user should return 200 (anti-enumeration)."""
        user = User(
            id=uuid4(),
            email="unverified_reset@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Unverified Reset",
            email_verified=False,
            verification_code=_hash_code("123456"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/forgot-password",
            json={"email": "unverified_reset@example.com"},
        )

        assert response.status_code == 200
        assert "message" in response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_with_valid_code(self, client: AsyncClient, db_session: AsyncSession):
        """Reset password with correct code should succeed."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="reset_valid@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="Reset Valid",
            email_verified=True,
            password_reset_code=_hash_code(code),
            password_reset_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "reset_valid@example.com",
                "code": code,
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 200

        # Verify login with new password works
        login_response = await client.post(
            "/auth/login",
            data={
                "username": "reset_valid@example.com",
                "password": "NewPassword123!",
            },
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_with_wrong_code(self, client: AsyncClient, db_session: AsyncSession):
        """Reset password with wrong code should return 400."""
        user = User(
            id=uuid4(),
            email="reset_wrong@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="Reset Wrong",
            email_verified=True,
            password_reset_code=_hash_code("654321"),
            password_reset_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "reset_wrong@example.com",
                "code": "999999",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_with_expired_code(self, client: AsyncClient, db_session: AsyncSession):
        """Reset password with expired code should return 400."""
        user = User(
            id=uuid4(),
            email="reset_expired@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="Reset Expired",
            email_verified=True,
            password_reset_code=_hash_code("654321"),
            password_reset_code_expires_at=utc_now() - timedelta(minutes=1),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "reset_expired@example.com",
                "code": "654321",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_unknown_email(self, client: AsyncClient):
        """Reset password for unknown email should return 400."""
        response = await client.post(
            "/auth/reset-password",
            json={
                "email": "unknown_reset@example.com",
                "code": "123456",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 400

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_code_cannot_be_reused(self, client: AsyncClient, db_session: AsyncSession):
        """Reset code should be invalidated after use."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="reset_reuse@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="Reset Reuse",
            email_verified=True,
            password_reset_code=_hash_code(code),
            password_reset_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        # First use - should succeed
        r1 = await client.post("/auth/reset-password", json={
            "email": "reset_reuse@example.com", "code": code, "new_password": "NewPass123!",
        })
        assert r1.status_code == 200

        # Second use - should fail (code cleared after first use)
        r2 = await client.post("/auth/reset-password", json={
            "email": "reset_reuse@example.com", "code": code, "new_password": "AnotherPass123!",
        })
        assert r2.status_code == 400

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_no_code_on_record(self, client: AsyncClient, db_session: AsyncSession):
        """Reset when user has no reset code should return 400."""
        user = User(
            id=uuid4(),
            email="reset_nocode@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="No Code",
            email_verified=True,
            password_reset_code=None,
            password_reset_code_expires_at=None,
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post("/auth/reset-password", json={
            "email": "reset_nocode@example.com", "code": "654321", "new_password": "NewPass123!",
        })
        assert response.status_code == 400
        assert "request a new one" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_reset_db_state_after_success(self, client: AsyncClient, db_session: AsyncSession):
        """After successful reset, DB should show code cleared."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="reset_dbstate@example.com",
            password_hash=get_test_password_hash("OldPassword123!"),
            display_name="DB State",
            email_verified=True,
            password_reset_code=_hash_code(code),
            password_reset_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post("/auth/reset-password", json={
            "email": "reset_dbstate@example.com", "code": code, "new_password": "NewPassword123!",
        })
        assert response.status_code == 200

        await db_session.refresh(user)
        assert user.password_reset_code is None
        assert user.password_reset_code_expires_at is None

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_forgot_password_cooldown_silently_returns(self, client: AsyncClient, db_session: AsyncSession):
        """Forgot password during cooldown should silently succeed without changing code."""
        code = "111111"
        user = User(
            id=uuid4(),
            email="reset_cooldown@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Reset Cooldown",
            email_verified=True,
            password_reset_code=_hash_code(code),
            password_reset_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()
        original_code = user.password_reset_code

        response = await client.post(
            "/auth/forgot-password",
            json={"email": "reset_cooldown@example.com"},
        )
        assert response.status_code == 200

        await db_session.refresh(user)
        assert user.password_reset_code == original_code

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_register_too_short_password(self, client: AsyncClient):
        """Registration with too-short password should return 422."""
        response = await client.post(
            "/auth/register",
            json={"email": "short@example.com", "password": "abc", "display_name": "Short"},
        )
        assert response.status_code == 422
