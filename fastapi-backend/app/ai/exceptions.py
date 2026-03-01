"""Custom exceptions for AI provider operations."""


class ProviderAuthError(Exception):
    """Raised when a provider rejects authentication.

    Attributes:
        provider: The provider type (e.g. 'openai', 'anthropic').
        message: Human-readable error message.
        recoverable: Whether the user can recover (e.g. switch to API key).
    """

    def __init__(
        self,
        provider: str,
        message: str,
        recoverable: bool = False,
    ) -> None:
        self.provider = provider
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)
