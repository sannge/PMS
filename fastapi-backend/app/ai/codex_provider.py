"""OpenAI Codex provider adapter for OAuth subscription connections.

Uses OAuth access tokens instead of API keys. Same API endpoints as
OpenAI, but authenticated via the user's subscription token.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from .exceptions import ProviderAuthError
from .openai_provider import _convert_messages
from .provider_interface import LLMProvider, LLMProviderError, VisionProvider

logger = logging.getLogger(__name__)


class CodexProvider(LLMProvider, VisionProvider):
    """OpenAI Codex adapter for ChatGPT Plus/Pro subscription OAuth.

    Uses the user's OAuth access token as Bearer auth instead of
    an API key. Same API endpoints as OpenAI, different auth mechanism.

    Args:
        access_token: Decrypted OAuth access token.
        base_url: Optional custom API endpoint.
    """

    def __init__(self, access_token: str, base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "api_key": access_token,  # OpenAI SDK accepts OAuth tokens as api_key
        }
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
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(
                provider="openai",
                message=(
                    "OpenAI rejected your subscription token. "
                    "Your token may have expired or been revoked. "
                    "Please reconnect your subscription or use an API key."
                ),
                recoverable=True,
            ) from exc
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI Codex chat completion failed: {exc}",
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
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(
                provider="openai",
                message=(
                    "OpenAI rejected your subscription token. "
                    "Your token may have expired or been revoked. "
                    "Please reconnect your subscription or use an API key."
                ),
                recoverable=True,
            ) from exc
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI Codex streaming failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc

    async def generate_embedding(
        self,
        text: str,
        model: str,
        dimensions: int | None = None,
    ) -> list[float]:
        raise NotImplementedError(
            "CodexProvider is for chat only. Use the global embedding provider."
        )

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        raise NotImplementedError(
            "CodexProvider is for chat only. Use the global embedding provider."
        )

    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str,
    ) -> str:
        import base64

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
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(
                provider="openai",
                message="OpenAI rejected your subscription token for vision.",
                recoverable=True,
            ) from exc
        except openai.APIError as exc:
            raise LLMProviderError(
                f"OpenAI Codex vision failed: {exc}",
                provider="openai",
                original=exc,
            ) from exc
