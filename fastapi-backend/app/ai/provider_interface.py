"""Abstract base classes for AI provider adapters."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class LLMProviderError(Exception):
    """Raised when an AI provider API call fails.

    Wraps provider-specific exceptions (``openai.APIError``,
    ``anthropic.APIError``, ``httpx.HTTPError``) into a unified error type.
    """

    def __init__(self, message: str, provider: str, original: Exception | None = None) -> None:
        self.provider = provider
        self.original = original
        super().__init__(message)


class LLMProvider(ABC):
    """Abstract interface for large language model providers.

    All provider adapters (OpenAI, Anthropic, Ollama) implement this
    interface so the rest of the application can use any provider
    interchangeably.
    """

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a single chat completion response.

        Args:
            messages: Conversation history in normalized format.
            model: Model identifier (e.g. ``gpt-4o``, ``claude-sonnet-4-20250514``).
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum tokens in the response.
            **kwargs: Provider-specific parameters.

        Returns:
            The assistant's response text.
        """
        ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response token by token.

        Args:
            messages: Conversation history in normalized format.
            model: Model identifier.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            **kwargs: Provider-specific parameters.

        Yields:
            Streamed text chunks.
        """
        ...

    @abstractmethod
    async def generate_embedding(
        self,
        text: str,
        model: str,
    ) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: Input text to embed.
            model: Embedding model identifier.

        Returns:
            Embedding vector as a list of floats.
        """
        ...

    @abstractmethod
    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]:
        """Generate embedding vectors for multiple texts.

        Args:
            texts: List of input texts.
            model: Embedding model identifier.

        Returns:
            List of embedding vectors, one per input text.
        """
        ...


class VisionProvider(ABC):
    """Abstract interface for vision-capable AI providers."""

    @abstractmethod
    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str,
    ) -> str:
        """Describe or analyze an image.

        Args:
            image_bytes: Raw image bytes.
            prompt: User prompt describing what to analyze.
            model: Vision model identifier.

        Returns:
            Model's description/analysis of the image.
        """
        ...
