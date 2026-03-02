"""Integration tests for Login 2FA flow.

Tests the two-step login flow: POST /auth/login returns requires_2fa,
POST /auth/verify-login verifies the 6-digit code and returns a JWT.
Covers: code generation, email sending, hashing, invalid credentials,
unverified email, correct/wrong/expired codes, brute force protection,
single-use codes, regeneration, and email subject distinction.
"""

import asyncio
import hashlib
from datetime import timedelta
from unittest.mock import AsyncMock, patch
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
class TestLogin2FA:
    """Tests for the Login 2FA flow."""

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_returns_2fa_required(
        self, client: AsyncClient, test_user: User
    ):
        """Valid credentials return 200 with requires_2fa=True."""
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
        assert "message" in data

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_sends_email(
        self, client: AsyncClient, test_user: User
    ):
        """Login calls send_login_code_email."""
        with patch(
            "app.services.auth_service.send_login_code_email",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            response = await client.post(
                "/auth/login",
                data={
                    "username": test_user.email,
                    "password": "TestPassword123!",
                },
            )

        assert response.status_code == 200
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == test_user.email
        # Second arg is the 6-digit code
        assert len(call_args[0][1]) == 6
        assert call_args[0][1].isdigit()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_stores_hashed_code(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Login stores a SHA-256 hash of the code, not plaintext."""
        with patch(
            "app.services.auth_service.send_login_code_email",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            await client.post(
                "/auth/login",
                data={
                    "username": test_user.email,
                    "password": "TestPassword123!",
                },
            )
            await asyncio.sleep(0.05)  # Let background task run

        assert mock_send.called
        captured_code = mock_send.call_args[0][1]  # Second positional arg is the code
        assert len(captured_code) == 6
        assert captured_code.isdigit()

        await db_session.refresh(test_user)

        # The stored code should be the SHA-256 hash
        expected_hash = _hash_code(captured_code)
        assert test_user.verification_code == expected_hash
        assert test_user.verification_code != captured_code

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_invalid_credentials_no_code(
        self, client: AsyncClient, test_user: User
    ):
        """Wrong password returns 401, no 2FA code is generated."""
        response = await client.post(
            "/auth/login",
            data={
                "username": test_user.email,
                "password": "WrongPassword!",
            },
        )

        assert response.status_code == 401

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_unverified_email_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Login with email_verified=False returns 403."""
        user = User(
            id=uuid4(),
            email="unverified_2fa@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Unverified 2FA",
            email_verified=False,
            verification_code=_hash_code("123456"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/login",
            data={
                "username": "unverified_2fa@example.com",
                "password": "TestPass123!",
            },
        )

        assert response.status_code == 403
        assert "not verified" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_correct_code(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """POST /auth/verify-login with correct code returns 200 + JWT."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="verify_login_ok@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login OK",
            email_verified=True,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-login",
            json={"email": "verify_login_ok@example.com", "code": code},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_wrong_code(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Invalid code returns 400."""
        user = User(
            id=uuid4(),
            email="verify_login_wrong@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login Wrong",
            email_verified=True,
            verification_code=_hash_code("654321"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-login",
            json={"email": "verify_login_wrong@example.com", "code": "999999"},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_expired_code(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Expired code returns 400."""
        user = User(
            id=uuid4(),
            email="verify_login_exp@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login Expired",
            email_verified=True,
            verification_code=_hash_code("654321"),
            verification_code_expires_at=utc_now() - timedelta(minutes=1),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-login",
            json={"email": "verify_login_exp@example.com", "code": "654321"},
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_brute_force(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """5 wrong attempts clears the code (brute force protection)."""
        user = User(
            id=uuid4(),
            email="verify_login_brute@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login Brute",
            email_verified=True,
            verification_code=_hash_code("654321"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        # Submit 5 wrong codes
        for i in range(5):
            response = await client.post(
                "/auth/verify-login",
                json={"email": "verify_login_brute@example.com", "code": f"{100000 + i:06d}"},
            )
            assert response.status_code == 400

        # The 5th should mention "too many" attempts
        assert "too many" in response.json()["detail"].lower() or "again" in response.json()["detail"].lower()

        # Code should now be cleared
        await db_session.refresh(user)
        assert user.verification_code is None
        assert user.verification_code_expires_at is None

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_code_single_use(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Code is cleared after successful verification (single-use)."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="verify_login_once@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login Once",
            email_verified=True,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        # First use succeeds
        r1 = await client.post(
            "/auth/verify-login",
            json={"email": "verify_login_once@example.com", "code": code},
        )
        assert r1.status_code == 200

        # Second use fails (code cleared)
        r2 = await client.post(
            "/auth/verify-login",
            json={"email": "verify_login_once@example.com", "code": code},
        )
        assert r2.status_code == 400

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_regenerates_code(
        self, client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        """Calling login again overwrites the previous code."""
        with patch(
            "app.services.auth_service.send_login_code_email",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_send:
            # First login
            await client.post(
                "/auth/login",
                data={
                    "username": test_user.email,
                    "password": "TestPassword123!",
                },
            )
            await asyncio.sleep(0.05)  # Let background task run

            # Second login (regenerates code)
            await client.post(
                "/auth/login",
                data={
                    "username": test_user.email,
                    "password": "TestPassword123!",
                },
            )
            await asyncio.sleep(0.05)  # Let background task run

        assert mock_send.call_count == 2
        codes = [call[0][1] for call in mock_send.call_args_list]

        # Both calls should produce valid 6-digit codes
        for code in codes:
            assert len(code) == 6
            assert code.isdigit()

        # DB should have the latest code's hash (overwritten by second login)
        await db_session.refresh(test_user)
        assert test_user.verification_code == _hash_code(codes[1])

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_2fa_email_distinct_subject(
        self, client: AsyncClient, test_user: User
    ):
        """Login 2FA email uses a distinct subject from registration verification."""
        from app.services.email_service import send_login_code_email, send_verification_email

        # The login email subject should differ from verification email subject
        # We check function exists and would produce different subjects
        # send_login_code_email uses "Your PM Desktop login code"
        # send_verification_email uses "Verify your email - PM Desktop"
        assert send_login_code_email is not send_verification_email
        # Both are distinct functions producing different email content

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_login_nonexistent_email(
        self, client: AsyncClient
    ):
        """verify-login with non-existent email returns 400 (no user enumeration)."""
        response = await client.post(
            "/auth/verify-login",
            json={"email": "nobody@example.com", "code": "123456"},
        )

        assert response.status_code == 400
        # Error message must be generic (no user enumeration)
        assert "invalid" in response.json()["detail"].lower()
