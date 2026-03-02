"""Unit tests for email service."""

import re
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_service import (
    generate_verification_code,
    send_email,
    send_password_reset_email,
    send_verification_email,
)


class TestGenerateVerificationCode:
    """Tests for verification code generation."""

    def test_code_is_6_digits(self):
        """Code should be exactly 6 digits."""
        code = generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_code_pads_with_zeros(self):
        """Code should be zero-padded (e.g., '000123')."""
        # Generate many codes to check padding
        codes = [generate_verification_code() for _ in range(100)]
        for code in codes:
            assert len(code) == 6

    def test_codes_are_not_all_same(self):
        """Generated codes should have some randomness."""
        codes = {generate_verification_code() for _ in range(50)}
        # With 50 codes from 1M possible values, they should all be unique
        assert len(codes) > 1


class TestSendEmail:
    """Tests for email sending."""

    @pytest.mark.asyncio
    async def test_dev_mode_logs_instead_of_sending(self):
        """When SMTP disabled, email should be logged, not sent."""
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.smtp_enabled = False
            mock_settings.smtp_host = ""

            result = await send_email(
                "test@example.com",
                "Test Subject",
                "<p>Test body</p>",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_smtp_send_success(self):
        """SMTP send should return True on success."""
        with (
            patch("app.services.email_service.settings") as mock_settings,
            patch("app.services.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send,
        ):
            mock_settings.smtp_enabled = True
            mock_settings.smtp_host = "smtp.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_username = "user"
            mock_settings.smtp_password = "pass"
            mock_settings.use_tls = False
            mock_settings.start_tls = True
            mock_settings.smtp_validate_certs = True
            mock_settings.smtp_timeout = 30
            mock_settings.smtp_from_email = "noreply@test.com"
            mock_settings.smtp_from_name = "Test App"

            result = await send_email(
                "test@example.com",
                "Test Subject",
                "<p>Test body</p>",
            )

            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_smtp_send_failure(self):
        """SMTP failure should return False."""
        with (
            patch("app.services.email_service.settings") as mock_settings,
            patch("app.services.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send,
        ):
            mock_settings.smtp_enabled = True
            mock_settings.smtp_host = "smtp.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_username = "user"
            mock_settings.smtp_password = "pass"
            mock_settings.use_tls = False
            mock_settings.start_tls = True
            mock_settings.smtp_validate_certs = True
            mock_settings.smtp_timeout = 30
            mock_settings.smtp_from_email = "noreply@test.com"
            mock_settings.smtp_from_name = "Test App"

            mock_send.side_effect = Exception("Connection refused")

            result = await send_email(
                "test@example.com",
                "Test Subject",
                "<p>Test body</p>",
            )

            assert result is False


class TestSendVerificationEmail:
    """Tests for verification email."""

    @pytest.mark.asyncio
    async def test_dev_mode_logs_code(self):
        """Dev mode should log the verification code."""
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.smtp_enabled = False
            mock_settings.smtp_host = ""
            mock_settings.email_verification_code_expiry_minutes = 15

            result = await send_verification_email("test@example.com", "123456")
            assert result is True


class TestSendPasswordResetEmail:
    """Tests for password reset email."""

    @pytest.mark.asyncio
    async def test_dev_mode_logs_code(self):
        """Dev mode should log the reset code."""
        with patch("app.services.email_service.settings") as mock_settings:
            mock_settings.smtp_enabled = False
            mock_settings.smtp_host = ""
            mock_settings.email_verification_code_expiry_minutes = 15

            result = await send_password_reset_email("test@example.com", "654321")
            assert result is True
