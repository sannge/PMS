"""API key encryption and rotation using Fernet symmetric encryption."""

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_provider import AiProvider

logger = logging.getLogger(__name__)


class ApiKeyEncryption:
    """Handles encryption, decryption, and rotation of AI provider API keys.

    Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
    The encryption key must be a valid base64-encoded 32-byte key,
    generated via ``Fernet.generate_key()``.
    """

    def __init__(self, encryption_key: str) -> None:
        if not encryption_key:
            raise ValueError(
                "AI encryption key is not configured. "
                "Set the AI_ENCRYPTION_KEY environment variable."
            )
        key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        self.fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt an API key and return the ciphertext as a UTF-8 string."""
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted API key and return the plaintext.

        Raises:
            InvalidToken: If the ciphertext is invalid or was encrypted
                with a different key.
        """
        return self.fernet.decrypt(ciphertext.encode()).decode()

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key suitable for AI_ENCRYPTION_KEY."""
        return Fernet.generate_key().decode()

    async def rotate_all(self, db: AsyncSession, new_key: str) -> int:
        """Re-encrypt all stored API keys with a new encryption key.

        Performs an atomic rotation: all keys are decrypted with the current
        key and re-encrypted with *new_key* in a single transaction.

        Args:
            db: Active database session (caller manages commit/rollback).
            new_key: The new Fernet key to encrypt with.

        Returns:
            Number of API keys that were rotated.

        Raises:
            InvalidToken: If any existing ciphertext cannot be decrypted
                with the current key.
        """
        new_fernet = Fernet(
            new_key.encode() if isinstance(new_key, str) else new_key
        )

        result = await db.execute(
            select(AiProvider).where(AiProvider.api_key_encrypted.isnot(None))
        )
        providers = result.scalars().all()

        rotated = 0
        for provider in providers:
            plaintext = self.decrypt(provider.api_key_encrypted)
            provider.api_key_encrypted = new_fernet.encrypt(
                plaintext.encode()
            ).decode()
            rotated += 1

        logger.info("Rotated %d API key(s) to new encryption key", rotated)
        return rotated
