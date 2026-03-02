"""Custom exceptions for AI provider operations."""


class OAuthError(Exception):
    """Raised when an OAuth operation fails."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)


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
