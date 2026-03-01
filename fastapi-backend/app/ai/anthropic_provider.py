"""Anthropic provider adapter implementing LLMProvider and VisionProvider."""

import base64
import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from .exceptions import ProviderAuthError
from .provider_interface import LLMProvider, LLMProviderError, VisionProvider

logger = logging.getLogger(__name__)

# Default max_tokens for Anthropic (required parameter)
_DEFAULT_MAX_TOKENS = 4096


def _convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert normalized messages to Anthropic's format.

    Anthropic requires a separate ``system`` parameter rather than a system
    message in the messages list. This function extracts the system prompt
    and converts multimodal image blocks::

        {"type": "image", "data": "<base64>", "media_type": "image/png"}

    to Anthropic's format::

        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}

    Returns:
        Tuple of (system_prompt | None, converted_messages).
    """
    system_prompt: str | None = None
    converted: list[dict[str, Any]] = []

    for msg in messages:
        if msg.get("role") == "system":
            # Anthropic uses a separate system parameter
            content = msg.get("content", "")
            system_prompt = content if isinstance(content, str) else str(content)
            continue

        content = msg.get("content")
        if isinstance(content, list):
            new_parts: list[dict[str, Any]] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image":
                    new_parts.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part.get("media_type", "image/png"),
                            "data": part["data"],
                        },
                    })
                else:
                    new_parts.append(part)
            converted.append({**msg, "content": new_parts})
        else:
            converted.append(msg)

    return system_prompt, converted


class AnthropicProvider(LLMProvider, VisionProvider):
    """Anthropic API adapter.

    Supports chat completions (streaming and non-streaming) and vision.
    Embeddings are not supported -- use OpenAI or Ollama for embeddings.

    Args:
        api_key: Anthropic API key.
        base_url: Optional custom API endpoint.
    """

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            system_prompt, converted = _convert_messages(messages)

            params: dict[str, Any] = {
                "model": model,
                "messages": converted,
                "temperature": temperature,
                "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
            }
            if system_prompt:
                params["system"] = system_prompt
            params.update(kwargs)

            response = await self._client.messages.create(**params)
            # Anthropic returns content as a list of blocks
            text_parts = [
                block.text
                for block in response.content
                if hasattr(block, "text")
            ]
            return "".join(text_parts)
        except anthropic.AuthenticationError as exc:
            err_msg = str(exc).lower()
            if "subscription" in err_msg or "unauthorized" in err_msg:
                raise ProviderAuthError(
                    provider="anthropic",
                    message=(
                        "Anthropic rejected your subscription token. "
                        "This may be because Anthropic does not allow third-party "
                        "applications to use personal subscription tokens. "
                        "Please use an API key instead, or contact Anthropic support."
                    ),
                    recoverable=True,
                ) from exc
            raise LLMProviderError(
                f"Anthropic authentication failed: {exc}",
                provider="anthropic",
                original=exc,
            ) from exc
        except anthropic.APIError as exc:
            raise LLMProviderError(
                f"Anthropic chat completion failed: {exc}",
                provider="anthropic",
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
            system_prompt, converted = _convert_messages(messages)

            params: dict[str, Any] = {
                "model": model,
                "messages": converted,
                "temperature": temperature,
                "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
            }
            if system_prompt:
                params["system"] = system_prompt
            params.update(kwargs)

            async with self._client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.AuthenticationError as exc:
            err_msg = str(exc).lower()
            if "subscription" in err_msg or "unauthorized" in err_msg:
                raise ProviderAuthError(
                    provider="anthropic",
                    message=(
                        "Anthropic rejected your subscription token. "
                        "This may be because Anthropic does not allow third-party "
                        "applications to use personal subscription tokens. "
                        "Please use an API key instead, or contact Anthropic support."
                    ),
                    recoverable=True,
                ) from exc
            raise LLMProviderError(
                f"Anthropic streaming authentication failed: {exc}",
                provider="anthropic",
                original=exc,
            ) from exc
        except anthropic.APIError as exc:
            raise LLMProviderError(
                f"Anthropic streaming failed: {exc}",
                provider="anthropic",
                original=exc,
            ) from exc

    async def generate_embedding(
        self,
        text: str,
        model: str,
    ) -> list[float]:
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API. "
            "Use OpenAI or Ollama for embeddings."
        )

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API. "
            "Use OpenAI or Ollama for embeddings."
        )

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
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        try:
            response = await self._client.messages.create(
                model=model,
                messages=messages,
                max_tokens=1024,
            )
            text_parts = [
                block.text
                for block in response.content
                if hasattr(block, "text")
            ]
            return "".join(text_parts)
        except anthropic.APIError as exc:
            raise LLMProviderError(
                f"Anthropic vision failed: {exc}",
                provider="anthropic",
                original=exc,
            ) from exc
