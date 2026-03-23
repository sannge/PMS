"""OpenAI provider adapter implementing LLMProvider and VisionProvider."""

import base64
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from .provider_interface import LLMProvider, LLMProviderError, VisionProvider

logger = logging.getLogger(__name__)


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert normalized multimodal messages to OpenAI's format.

    Normalized image blocks::

        {"type": "image", "data": "<base64>", "media_type": "image/png"}

    are converted to OpenAI's ``image_url`` content blocks::

        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    """
    converted: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_parts: list[dict[str, Any]] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image":
                    media_type = part.get("media_type", "image/png")
                    data = part["data"]
                    new_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{data}",
                            },
                        }
                    )
                else:
                    new_parts.append(part)
            converted.append({**msg, "content": new_parts})
        else:
            converted.append(msg)
    return converted


class OpenAIProvider(LLMProvider, VisionProvider):
    """OpenAI API adapter.

    Supports chat completions (streaming and non-streaming), embeddings
    (with optional dimension control), and vision via image_url content.

    Args:
        api_key: OpenAI API key.
        base_url: Optional custom API endpoint (for Azure OpenAI or proxies).
    """

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            params: dict[str, Any] = {
                "model": model,
                "messages": _convert_messages(messages),
                "temperature": temperature,
                "stream": False,
            }
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            params.update(kwargs)

            response = await self._client.chat.completions.create(**params)
            return response.choices[0].message.content or ""
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI chat completion failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        try:
            params: dict[str, Any] = {
                "model": model,
                "messages": _convert_messages(messages),
                "temperature": temperature,
                "stream": True,
            }
            if max_tokens is not None:
                params["max_tokens"] = max_tokens
            params.update(kwargs)

            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI streaming failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc

    async def generate_embedding(
        self,
        text: str,
        model: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Generate an embedding vector.

        Args:
            text: Input text.
            model: Embedding model identifier (e.g. ``text-embedding-3-small``).
            dimensions: Optional output dimensions (supported by v3 models).

        Returns:
            Embedding vector.
        """
        try:
            params: dict[str, Any] = {
                "model": model,
                "input": text,
            }
            if dimensions is not None:
                params["dimensions"] = dimensions

            response = await self._client.embeddings.create(**params)
            return response.data[0].embedding
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI embedding failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single API call.

        Args:
            texts: List of input texts.
            model: Embedding model identifier.
            dimensions: Optional output dimensions.

        Returns:
            List of embedding vectors, order matching input texts.
        """
        try:
            params: dict[str, Any] = {
                "model": model,
                "input": texts,
            }
            if dimensions is not None:
                params["dimensions"] = dimensions

            response = await self._client.embeddings.create(**params)
            # Sort by index to guarantee order matches input
            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [d.embedding for d in sorted_data]
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI batch embedding failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc

    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str,
    ) -> str:
        b64_data = base64.b64encode(image_bytes).decode()
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_data}",
                        },
                    },
                ],
            }
        ]
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
            )
            return response.choices[0].message.content or ""
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI vision failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc
