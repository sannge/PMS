"""Integration tests for email verification flow."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.email_service import generate_verification_code
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
class TestEmailVerification:
    """Tests for email verification endpoints."""

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_register_sends_verification_code(self, client: AsyncClient):
        """Registration should return message about verification code."""
        response = await client.post(
            "/auth/register",
            json={
                "email": "verify_test@example.com",
                "password": "SecurePass123!",
                "display_name": "Verify Test",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "verify_test@example.com"
        assert "verification" in data["message"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_valid_code(self, client: AsyncClient, db_session: AsyncSession):
        """Verify with correct code should return JWT token."""
        code = "123456"
        user = User(
            id=uuid4(),
            email="verify_valid@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Valid",
            email_verified=False,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_valid@example.com", "code": code},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_wrong_code(self, client: AsyncClient, db_session: AsyncSession):
        """Verify with wrong code should return 400."""
        user = User(
            id=uuid4(),
            email="verify_wrong@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Wrong",
            email_verified=False,
            verification_code=_hash_code("123456"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_wrong@example.com", "code": "999999"},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_expired_code(self, client: AsyncClient, db_session: AsyncSession):
        """Verify with expired code should return 400."""
        user = User(
            id=uuid4(),
            email="verify_expired@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Expired",
            email_verified=False,
            verification_code=_hash_code("123456"),
            verification_code_expires_at=utc_now() - timedelta(minutes=1),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_expired@example.com", "code": "123456"},
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_already_verified_is_idempotent(self, client: AsyncClient, test_user: User):
        """Verify for already-verified user should succeed idempotently (return token)."""
        response = await client.post(
            "/auth/verify-email",
            json={"email": test_user.email, "code": "123456"},
        )

        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_unverified_returns_403(self, client: AsyncClient, db_session: AsyncSession):
        """Login with unverified email should return 403."""
        user = User(
            id=uuid4(),
            email="unverified_login@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Unverified",
            email_verified=False,
            verification_code=_hash_code("123456"),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/login",
            data={
                "username": "unverified_login@example.com",
                "password": "TestPass123!",
            },
        )

        assert response.status_code == 403
        assert "not verified" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_login_after_verification(self, client: AsyncClient, db_session: AsyncSession):
        """Login should succeed after email verification."""
        code = "123456"
        user = User(
            id=uuid4(),
            email="verify_then_login@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Login",
            email_verified=False,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        # Verify first
        verify_response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_then_login@example.com", "code": code},
        )
        assert verify_response.status_code == 200

        # Now login should work
        login_response = await client.post(
            "/auth/login",
            data={
                "username": "verify_then_login@example.com",
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_resend_verification(self, client: AsyncClient, db_session: AsyncSession):
        """Resend verification should succeed when cooldown has passed."""
        user = User(
            id=uuid4(),
            email="resend_test@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Resend Test",
            email_verified=False,
            verification_code=_hash_code("123456"),
            # Set expires_at far enough in the past so cooldown has passed
            verification_code_expires_at=utc_now() - timedelta(minutes=10),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/resend-verification",
            json={"email": "resend_test@example.com"},
        )

        assert response.status_code == 200

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_resend_verification_cooldown(self, client: AsyncClient, db_session: AsyncSession):
        """Resend verification during cooldown should return 429."""
        user = User(
            id=uuid4(),
            email="resend_cool@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Resend Cooldown",
            email_verified=False,
            verification_code=_hash_code("123456"),
            # Just sent (expires in 15 min = sent just now)
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/resend-verification",
            json={"email": "resend_cool@example.com"},
        )

        assert response.status_code == 429

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verification_code_cannot_be_reused(self, client: AsyncClient, db_session: AsyncSession):
        """Verification code should be invalidated after successful use."""
        code = "123456"
        user = User(
            id=uuid4(),
            email="verify_reuse@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="Verify Reuse",
            email_verified=False,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        # First use - should succeed
        r1 = await client.post("/auth/verify-email", json={"email": "verify_reuse@example.com", "code": code})
        assert r1.status_code == 200
        assert "access_token" in r1.json()

        # Second use - already verified, idempotent success
        r2 = await client.post("/auth/verify-email", json={"email": "verify_reuse@example.com", "code": code})
        assert r2.status_code == 200
        assert "access_token" in r2.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_no_code_on_record(self, client: AsyncClient, db_session: AsyncSession):
        """Verify when user has no verification code stored should suggest resend."""
        user = User(
            id=uuid4(),
            email="verify_nocode@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="No Code",
            email_verified=False,
            verification_code=None,
            verification_code_expires_at=None,
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_nocode@example.com", "code": "123456"},
        )
        assert response.status_code == 400
        assert "request a new one" in response.json()["detail"].lower()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_nonexistent_email(self, client: AsyncClient):
        """Verify for nonexistent email should return 400."""
        response = await client.post(
            "/auth/verify-email",
            json={"email": "ghost@example.com", "code": "123456"},
        )
        assert response.status_code == 400

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_db_state_after_success(self, client: AsyncClient, db_session: AsyncSession):
        """After successful verification, DB should show verified and code cleared."""
        code = "654321"
        user = User(
            id=uuid4(),
            email="verify_dbstate@example.com",
            password_hash=get_test_password_hash("TestPass123!"),
            display_name="DB State",
            email_verified=False,
            verification_code=_hash_code(code),
            verification_code_expires_at=utc_now() + timedelta(minutes=15),
        )
        db_session.add(user)
        await db_session.commit()

        response = await client.post(
            "/auth/verify-email",
            json={"email": "verify_dbstate@example.com", "code": code},
        )
        assert response.status_code == 200

        await db_session.refresh(user)
        assert user.email_verified is True
        assert user.verification_code is None
        assert user.verification_code_expires_at is None

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_resend_verification_unknown_email(self, client: AsyncClient):
        """Resend verification for unknown email should return 200 (anti-enumeration)."""
        response = await client.post(
            "/auth/resend-verification",
            json={"email": "nonexistent@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_resend_verification_already_verified(self, client: AsyncClient, test_user: User):
        """Resend verification for already-verified user should return 200 (anti-enumeration)."""
        response = await client.post(
            "/auth/resend-verification",
            json={"email": test_user.email},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_code_wrong_length(self, client: AsyncClient):
        """Verification with wrong code length should return 422."""
        response = await client.post(
            "/auth/verify-email",
            json={"email": "test@example.com", "code": "12345"},
        )
        assert response.status_code == 422

    @pytest.mark.skipif(not _bcrypt_available, reason="bcrypt not properly configured")
    async def test_verify_code_non_numeric(self, client: AsyncClient):
        """Verification with non-numeric code should return 422 (pattern validation)."""
        response = await client.post(
            "/auth/verify-email",
            json={"email": "test@example.com", "code": "abcdef"},
        )
        # Pattern r"^\d{6}$" rejects non-numeric codes at schema level
        assert response.status_code == 422
