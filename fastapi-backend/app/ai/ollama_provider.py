"""Ollama provider adapter implementing LLMProvider and VisionProvider."""

import base64
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .provider_interface import LLMProvider, LLMProviderError, VisionProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_REQUEST_TIMEOUT = 120.0  # Ollama can be slow on large models


def _extract_images(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert normalized multimodal messages to Ollama's format.

    Ollama expects images as a base64 array in the message rather than
    inline content blocks. This extracts image data and places it in the
    ``images`` key.
    """
    converted: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            images: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "image":
                        images.append(part["data"])
                    elif part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    text_parts.append(part)
            entry: dict[str, Any] = {
                "role": msg["role"],
                "content": " ".join(text_parts),
            }
            if images:
                entry["images"] = images
            converted.append(entry)
        else:
            converted.append({"role": msg["role"], "content": content or ""})
    return converted


class OllamaProvider(LLMProvider, VisionProvider):
    """Ollama local inference adapter.

    Communicates with a local Ollama server via its HTTP API.
    Supports chat, streaming, embeddings, and vision.

    Args:
        base_url: Ollama server URL (default: ``http://localhost:11434``).
        api_key: Ignored (Ollama doesn't require authentication),
            accepted for interface consistency.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client to release connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaProvider":
        """Support async context manager usage."""
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Close client on context manager exit."""
        await self.close()

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            payload: dict[str, Any] = {
                "model": model,
                "messages": _extract_images(messages),
                "stream": False,
                "options": {"temperature": temperature},
            }
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens

            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama chat completion failed: {exc}",
                provider="ollama",
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
            payload: dict[str, Any] = {
                "model": model,
                "messages": _extract_images(messages),
                "stream": True,
                "options": {"temperature": temperature},
            }
            if max_tokens is not None:
                payload["options"]["num_predict"] = max_tokens

            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done", False):
                        break
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama streaming failed: {exc}",
                provider="ollama",
                original=exc,
            ) from exc

    async def generate_embedding(
        self,
        text: str,
        model: str,
    ) -> list[float]:
        try:
            payload: dict[str, Any] = {
                "model": model,
                "input": text,
            }
            response = await self._client.post("/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            # Ollama /api/embed returns {"embeddings": [[...]]}
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise LLMProviderError(
                    f"Ollama returned empty embeddings for model {model}",
                    provider="ollama",
                )
            return embeddings[0]
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama embedding failed: {exc}",
                provider="ollama",
                original=exc,
            ) from exc

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]:
        # Ollama /api/embed supports list input natively
        try:
            payload: dict[str, Any] = {
                "model": model,
                "input": texts,
            }
            response = await self._client.post("/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(texts):
                raise LLMProviderError(
                    f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs",
                    provider="ollama",
                )
            return embeddings
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama batch embedding failed: {exc}",
                provider="ollama",
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
                "content": prompt,
                "images": [b64_data],
            }
        ]
        try:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": False,
            }
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama vision failed: {exc}",
                provider="ollama",
                original=exc,
            ) from exc
