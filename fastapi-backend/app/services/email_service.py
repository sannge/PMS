"""Email service for sending verification and password reset emails via SMTP."""

import asyncio
import logging
import secrets
from email.message import EmailMessage

import aiosmtplib

from ..config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds


def generate_verification_code() -> str:
    """Generate a 6-digit verification code.

    Returns a fixed '000000' when SMTP is disabled (dev mode) so codes
    are predictable without email delivery.
    """
    if not settings.smtp_enabled:
        return "000000"
    return f"{secrets.randbelow(1000000):06d}"


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Send an email via SMTP or log to console in dev mode.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML email body

    Returns:
        True if sent (or logged in dev mode), False on SMTP failure
    """
    if not settings.smtp_enabled or not settings.smtp_host:
        logger.info(
            "[DEV MODE] Email to=%s subject=%s\n%s",
            to_email,
            subject,
            html_body,
        )
        return True

    msg = EmailMessage()
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(html_body, subtype="html")

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username or None,
                password=settings.smtp_password or None,
                use_tls=settings.use_tls,
                start_tls=settings.start_tls,
                validate_certs=settings.smtp_validate_certs,
                timeout=settings.smtp_timeout,
            )
            logger.info("Email sent to %s: %s", to_email, subject)
            return True
        except Exception:
            if attempt == _MAX_RETRIES:
                logger.exception("Failed to send email to %s after %d attempts", to_email, _MAX_RETRIES)
                return False
            delay = _BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                "Email send attempt %d/%d to %s failed, retrying in %.1fs",
                attempt,
                _MAX_RETRIES,
                to_email,
                delay,
            )
            await asyncio.sleep(delay)
    return False


async def send_verification_email(to_email: str, code: str) -> bool:
    """Send email verification code."""
    subject = "Verify your email - PM Desktop"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
        <h2 style="color: #1a1a1a; margin-bottom: 8px;">Verify your email</h2>
        <p style="color: #666; margin-bottom: 24px;">Enter this code to verify your PM Desktop account:</p>
        <div style="background: #f5f5f5; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 24px;">
            <span style="font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #1a1a1a;">{code}</span>
        </div>
        <p style="color: #999; font-size: 13px;">This code expires in {settings.email_verification_code_expiry_minutes} minutes. If you didn't create an account, you can safely ignore this email.</p>
    </div>
    """

    if not settings.smtp_enabled or not settings.smtp_host:
        logger.info(
            "[DEV MODE] Verification code for %s: %s",
            to_email,
            code,
        )
        return True

    return await send_email(to_email, subject, html_body)


async def send_login_code_email(to_email: str, code: str) -> bool:
    """Send login 2FA verification code."""
    subject = "Your PM Desktop login code"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
        <h2 style="color: #1a1a1a; margin-bottom: 8px;">Your login code</h2>
        <p style="color: #666; margin-bottom: 24px;">Enter this code to complete your PM Desktop login:</p>
        <div style="background: #f5f5f5; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 24px;">
            <span style="font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #1a1a1a;">{code}</span>
        </div>
        <p style="color: #999; font-size: 13px;">This code expires in {settings.email_verification_code_expiry_minutes} minutes. If you didn't attempt to log in, you can safely ignore this email.</p>
    </div>
    """

    if not settings.smtp_enabled or not settings.smtp_host:
        logger.info(
            "[DEV MODE] Login code for %s: %s",
            to_email,
            code,
        )
        return True

    return await send_email(to_email, subject, html_body)


async def send_password_reset_email(to_email: str, code: str) -> bool:
    """Send password reset code."""
    subject = "Reset your password - PM Desktop"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
        <h2 style="color: #1a1a1a; margin-bottom: 8px;">Reset your password</h2>
        <p style="color: #666; margin-bottom: 24px;">Enter this code to reset your PM Desktop password:</p>
        <div style="background: #f5f5f5; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 24px;">
            <span style="font-size: 32px; font-weight: 700; letter-spacing: 8px; color: #1a1a1a;">{code}</span>
        </div>
        <p style="color: #999; font-size: 13px;">This code expires in {settings.password_reset_code_expiry_minutes} minutes. If you didn't request a password reset, you can safely ignore this email.</p>
    </div>
    """

    if not settings.smtp_enabled or not settings.smtp_host:
        logger.info(
            "[DEV MODE] Password reset code for %s: %s",
            to_email,
            code,
        )
        return True

    return await send_email(to_email, subject, html_body)
