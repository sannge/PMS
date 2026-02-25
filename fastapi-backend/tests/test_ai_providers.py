"""Unit tests for AI provider adapters, encryption, normalizer, and registry.

All external API calls are mocked. No real network requests are made.
"""

import base64
import math
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import openai
import pytest
from cryptography.fernet import Fernet

from app.ai.embedding_normalizer import EmbeddingNormalizer
from app.ai.encryption import ApiKeyEncryption
from app.ai.openai_provider import OpenAIProvider, _convert_messages as openai_convert
from app.ai.anthropic_provider import AnthropicProvider, _convert_messages as anthropic_convert
from app.ai.ollama_provider import OllamaProvider, _extract_images as ollama_extract
from app.ai.provider_interface import LLMProviderError
from app.ai.provider_registry import ConfigurationError, ProviderRegistry


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------

class TestOpenAIProvider:

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_chat_completion_returns_string(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o",
        )

        assert isinstance(result, str)
        assert result == "Hello!"
        mock_client.chat.completions.create.assert_awaited_once()

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_chat_completion_returns_empty_on_none(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o",
        )
        assert result == ""

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_chat_completion_stream_yields_chunks(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        # Build async iterator of chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None  # final chunk with no content

        async def fake_stream():
            for c in [chunk1, chunk2, chunk3]:
                yield c

        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream())

        provider = OpenAIProvider(api_key="sk-test")
        chunks = []
        async for text in provider.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o",
        ):
            chunks.append(text)

        assert chunks == ["Hello", " world"]

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_generate_embedding_returns_vector(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        embedding_data = MagicMock()
        embedding_data.embedding = [0.1, 0.2, 0.3]

        mock_response = MagicMock()
        mock_response.data = [embedding_data]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.generate_embedding(text="test", model="text-embedding-3-small")

        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_generate_embeddings_batch_returns_list(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        emb0 = MagicMock()
        emb0.index = 0
        emb0.embedding = [0.1, 0.2]

        emb1 = MagicMock()
        emb1.index = 1
        emb1.embedding = [0.3, 0.4]

        mock_response = MagicMock()
        # Return in reverse order to test sorting
        mock_response.data = [emb1, emb0]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.generate_embeddings_batch(
            texts=["hello", "world"],
            model="text-embedding-3-small",
        )

        assert isinstance(result, list)
        assert len(result) == 2
        # Should be sorted by index
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_describe_image_returns_description(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A photo of a cat."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.describe_image(
            image_bytes=b"\x89PNG\r\n",
            prompt="Describe this image",
            model="gpt-4o",
        )

        assert isinstance(result, str)
        assert result == "A photo of a cat."
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        # Verify image_url block was built
        content_blocks = messages[0]["content"]
        assert content_blocks[1]["type"] == "image_url"
        assert "data:image/png;base64," in content_blocks[1]["image_url"]["url"]

    def test_chat_with_image_content_block(self):
        """Verify _convert_messages converts image blocks to OpenAI format."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "data": "abc123", "media_type": "image/jpeg"},
                ],
            }
        ]

        converted = openai_convert(messages)
        content = converted[0]["content"]

        assert content[0] == {"type": "text", "text": "What is this?"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,abc123"

    @patch("app.ai.openai_provider.AsyncOpenAI")
    async def test_api_error_wrapped_in_llm_provider_error(self, mock_openai_cls):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIError(
                message="rate limit",
                request=MagicMock(),
                body=None,
            )
        )

        provider = OpenAIProvider(api_key="sk-test")
        with pytest.raises(LLMProviderError) as exc_info:
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4o",
            )
        assert exc_info.value.provider == "openai"
        assert exc_info.value.original is not None


# ---------------------------------------------------------------------------
# Anthropic Provider
# ---------------------------------------------------------------------------

class TestAnthropicProvider:

    @patch("app.ai.anthropic_provider.AsyncAnthropic")
    async def test_chat_completion_returns_string(self, mock_anthropic_cls):
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.text = "Hello from Claude!"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = AnthropicProvider(api_key="sk-ant-test")
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-20250514",
        )

        assert isinstance(result, str)
        assert result == "Hello from Claude!"

    @patch("app.ai.anthropic_provider.AsyncAnthropic")
    async def test_chat_completion_extracts_system_prompt(self, mock_anthropic_cls):
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.text = "response"
        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = AnthropicProvider(api_key="sk-ant-test")
        await provider.chat_completion(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
            ],
            model="claude-sonnet-4-20250514",
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        # System should be extracted as separate param
        assert call_kwargs["system"] == "You are helpful."
        # Messages should NOT contain system role
        for msg in call_kwargs["messages"]:
            assert msg["role"] != "system"

    @patch("app.ai.anthropic_provider.AsyncAnthropic")
    async def test_chat_completion_stream_yields_chunks(self, mock_anthropic_cls):
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        async def fake_text_stream():
            for text in ["Hello", " from", " Claude"]:
                yield text

        mock_stream_ctx = AsyncMock()
        mock_stream_obj = MagicMock()
        mock_stream_obj.text_stream = fake_text_stream()

        # AsyncAnthropic uses async context manager for streaming
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_obj)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        provider = AnthropicProvider(api_key="sk-ant-test")
        chunks = []
        async for text in provider.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-20250514",
        ):
            chunks.append(text)

        assert chunks == ["Hello", " from", " Claude"]

    async def test_embedding_raises_not_implemented(self):
        provider = AnthropicProvider.__new__(AnthropicProvider)
        with pytest.raises(NotImplementedError, match="Anthropic does not provide"):
            await provider.generate_embedding(text="test", model="x")

    async def test_embeddings_batch_raises_not_implemented(self):
        provider = AnthropicProvider.__new__(AnthropicProvider)
        with pytest.raises(NotImplementedError, match="Anthropic does not provide"):
            await provider.generate_embeddings_batch(texts=["a"], model="x")

    @patch("app.ai.anthropic_provider.AsyncAnthropic")
    async def test_describe_image_returns_description(self, mock_anthropic_cls):
        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.text = "It is a cat."
        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        provider = AnthropicProvider(api_key="sk-ant-test")
        result = await provider.describe_image(
            image_bytes=b"\x89PNG\r\n",
            prompt="Describe this",
            model="claude-sonnet-4-20250514",
        )

        assert result == "It is a cat."
        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Anthropic image format: {"type": "image", "source": {"type": "base64", ...}}
        image_block = messages[0]["content"][0]
        assert image_block["type"] == "image"
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["media_type"] == "image/png"

    def test_chat_with_image_content_block(self):
        """Verify _convert_messages converts image blocks to Anthropic format."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "data": "abc123", "media_type": "image/jpeg"},
                ],
            }
        ]

        system_prompt, converted = anthropic_convert(messages)
        content = converted[0]["content"]

        assert system_prompt is None
        assert content[0] == {"type": "text", "text": "What is this?"}
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"
        assert content[1]["source"]["media_type"] == "image/jpeg"
        assert content[1]["source"]["data"] == "abc123"

    @patch("app.ai.anthropic_provider.AsyncAnthropic")
    async def test_api_error_wrapped_in_llm_provider_error(self, mock_anthropic_cls):
        import anthropic as anthropic_lib

        mock_client = AsyncMock()
        mock_anthropic_cls.return_value = mock_client

        mock_client.messages.create = AsyncMock(
            side_effect=anthropic_lib.APIError(
                message="overloaded",
                request=MagicMock(),
                body=None,
            )
        )

        provider = AnthropicProvider(api_key="sk-ant-test")
        with pytest.raises(LLMProviderError) as exc_info:
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-20250514",
            )
        assert exc_info.value.provider == "anthropic"
        assert exc_info.value.original is not None


# ---------------------------------------------------------------------------
# Ollama Provider
# ---------------------------------------------------------------------------

class TestOllamaProvider:

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_chat_completion_returns_string(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "Ollama says hi"}}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        result = await provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="llama3",
        )

        assert isinstance(result, str)
        assert result == "Ollama says hi"

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_chat_completion_stream_yields_chunks(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        lines = [
            '{"message": {"content": "Hello"}, "done": false}',
            '{"message": {"content": " world"}, "done": false}',
            '{"message": {"content": ""}, "done": true}',
        ]

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = fake_aiter_lines

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        provider = OllamaProvider()
        chunks = []
        async for text in provider.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="llama3",
        ):
            chunks.append(text)

        assert chunks == ["Hello", " world"]

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_generate_embedding_returns_vector(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embeddings": [[0.5, 0.6, 0.7]]}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        result = await provider.generate_embedding(text="test", model="nomic-embed-text")

        assert isinstance(result, list)
        assert result == [0.5, 0.6, 0.7]

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_generate_embedding_empty_raises_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embeddings": []}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        with pytest.raises(LLMProviderError, match="empty embeddings"):
            await provider.generate_embedding(text="test", model="nomic-embed-text")

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_api_error_wrapped_in_llm_provider_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPError("connection refused")
        )

        provider = OllamaProvider()
        with pytest.raises(LLMProviderError) as exc_info:
            await provider.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="llama3",
            )
        assert exc_info.value.provider == "ollama"
        assert exc_info.value.original is not None

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_ollama_offline_embedding_raises_error(self, mock_client_cls):
        """When Ollama is offline, embedding call raises LLMProviderError."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        provider = OllamaProvider()
        with pytest.raises(LLMProviderError, match="Ollama embedding failed"):
            await provider.generate_embedding(text="test", model="nomic-embed-text")

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_close_disposes_client(self, mock_client_cls):
        """Calling close() properly closes the underlying httpx client."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        provider = OllamaProvider()
        await provider.close()
        mock_client.aclose.assert_awaited_once()

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_context_manager(self, mock_client_cls):
        """OllamaProvider supports async context manager usage."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        async with OllamaProvider() as provider:
            assert isinstance(provider, OllamaProvider)
        mock_client.aclose.assert_awaited_once()

    def test_extract_images_converts_multimodal_blocks(self):
        """Verify _extract_images converts image blocks to Ollama format."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "data": "abc123", "media_type": "image/jpeg"},
                ],
            }
        ]

        converted = ollama_extract(messages)
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "What is this?"
        assert converted[0]["images"] == ["abc123"]

    def test_extract_images_plain_text_unchanged(self):
        """Plain text messages pass through without images key."""
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        converted = ollama_extract(messages)
        assert len(converted) == 1
        assert converted[0]["content"] == "Hello"
        assert "images" not in converted[0]

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_generate_embeddings_batch_returns_list(self, mock_client_cls):
        """Batch embedding returns list of vectors matching input order."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        result = await provider.generate_embeddings_batch(
            texts=["hello", "world"],
            model="nomic-embed-text",
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_generate_embeddings_batch_count_mismatch_raises(self, mock_client_cls):
        """Batch embedding raises error when count mismatch."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embeddings": [[0.1, 0.2]]}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        with pytest.raises(LLMProviderError, match="1 embeddings for 2 inputs"):
            await provider.generate_embeddings_batch(
                texts=["hello", "world"],
                model="nomic-embed-text",
            )

    @patch("app.ai.ollama_provider.httpx.AsyncClient")
    async def test_describe_image_returns_description(self, mock_client_cls):
        """Ollama describe_image sends image as base64 in images array."""
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "A cat sitting on a mat."}}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        provider = OllamaProvider()
        result = await provider.describe_image(
            image_bytes=b"\x89PNG\r\n",
            prompt="Describe this image",
            model="llava",
        )

        assert result == "A cat sitting on a mat."
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        messages = payload["messages"]
        assert messages[0]["images"] is not None
        assert len(messages[0]["images"]) == 1
        assert messages[0]["content"] == "Describe this image"


# ---------------------------------------------------------------------------
# API Key Encryption
# ---------------------------------------------------------------------------

class TestApiKeyEncryption:

    def test_encryption_roundtrip(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        enc = ApiKeyEncryption(key)

        plaintext = "sk-secret-api-key-12345"
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        assert enc.decrypt(ciphertext) == plaintext

    def test_invalid_key_raises_error(self):
        from cryptography.fernet import Fernet

        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        enc1 = ApiKeyEncryption(key1)
        enc2 = ApiKeyEncryption(key2)

        ciphertext = enc1.encrypt("my-secret")
        with pytest.raises(Exception):
            enc2.decrypt(ciphertext)

    def test_generate_key_is_valid(self):
        key = ApiKeyEncryption.generate_key()
        assert isinstance(key, str)
        # Should be usable to construct a new instance without error
        enc = ApiKeyEncryption(key)
        roundtrip = enc.decrypt(enc.encrypt("test"))
        assert roundtrip == "test"

    def test_empty_key_raises_value_error(self):
        with pytest.raises(ValueError, match="AI encryption key is not configured"):
            ApiKeyEncryption("")

    async def test_rotate_all_re_encrypts_keys(self):
        """rotate_all decrypts with old key and re-encrypts with new key."""
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        enc = ApiKeyEncryption(old_key)

        # Create mock providers with encrypted keys
        provider1 = MagicMock()
        provider1.api_key_encrypted = enc.encrypt("sk-key-one")

        provider2 = MagicMock()
        provider2.api_key_encrypted = enc.encrypt("sk-key-two")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [provider1, provider2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        rotated = await enc.rotate_all(mock_db, new_key)

        assert rotated == 2

        # Verify the new encrypted values can be decrypted with the new key
        new_enc = ApiKeyEncryption(new_key)
        assert new_enc.decrypt(provider1.api_key_encrypted) == "sk-key-one"
        assert new_enc.decrypt(provider2.api_key_encrypted) == "sk-key-two"

        # Verify old key can no longer decrypt
        with pytest.raises(Exception):
            enc.decrypt(provider1.api_key_encrypted)

    async def test_rotate_all_handles_empty_providers(self):
        """rotate_all returns 0 when no providers have API keys."""
        key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        enc = ApiKeyEncryption(key)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        rotated = await enc.rotate_all(mock_db, new_key)
        assert rotated == 0


# ---------------------------------------------------------------------------
# Embedding Normalizer
# ---------------------------------------------------------------------------

class TestEmbeddingNormalizer:

    def test_pads_short_vectors(self):
        normalizer = EmbeddingNormalizer(target_dimensions=5)
        result = normalizer.normalize([1.0, 2.0])
        assert len(result) == 5
        # Last three elements were originally zero-padded, then L2-normalized
        # Check that the structure is correct (padded zeros remain zero after normalization)
        # Wait -- after L2 norm, zeros remain zero: 0.0 / norm == 0.0
        assert result[2] == pytest.approx(0.0)
        assert result[3] == pytest.approx(0.0)
        assert result[4] == pytest.approx(0.0)

    def test_truncates_long_vectors(self):
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        result = normalizer.normalize([1.0, 2.0, 3.0, 4.0, 5.0])
        assert len(result) == 3

    def test_l2_normalizes(self):
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        result = normalizer.normalize([3.0, 4.0, 0.0])
        # L2 norm of [3,4,0] = 5, so normalized = [0.6, 0.8, 0.0]
        assert result[0] == pytest.approx(0.6)
        assert result[1] == pytest.approx(0.8)
        assert result[2] == pytest.approx(0.0)
        # Verify unit length
        norm = math.sqrt(sum(x * x for x in result))
        assert norm == pytest.approx(1.0)

    def test_zero_vector_handled(self):
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        result = normalizer.normalize([0.0, 0.0, 0.0])
        assert len(result) == 3
        # Zero vector should be returned as-is (no division by zero)
        assert result == [0.0, 0.0, 0.0]

    def test_exact_dimension_unchanged_length(self):
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        result = normalizer.normalize([1.0, 0.0, 0.0])
        assert len(result) == 3
        # [1,0,0] is already unit length
        assert result == pytest.approx([1.0, 0.0, 0.0])

    def test_near_zero_vector_not_amplified(self):
        """Near-zero vectors (below epsilon) are returned without normalization."""
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        tiny = [1e-15, 1e-15, 1e-15]
        result = normalizer.normalize(tiny)
        assert len(result) == 3
        # Should NOT be unit length -- returned as-is because norm < epsilon
        norm = math.sqrt(sum(x * x for x in result))
        assert norm < 1e-10

    def test_invalid_target_dimensions(self):
        with pytest.raises(ValueError, match="target_dimensions must be >= 1"):
            EmbeddingNormalizer(target_dimensions=0)


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    """Test ProviderRegistry resolution logic using mock DB sessions.

    Since ProviderRegistry is a singleton, we reset it between tests.
    """

    def setup_method(self):
        """Reset singleton state before each test."""
        ProviderRegistry._instance = None

    def _make_provider(self, *, provider_type="openai", scope="global",
                       user_id=None, is_enabled=True, api_key_encrypted="enc"):
        p = MagicMock()
        p.id = uuid4()
        p.name = f"test-{provider_type}"
        p.provider_type = provider_type
        p.scope = scope
        p.user_id = user_id
        p.is_enabled = is_enabled
        p.api_key_encrypted = api_key_encrypted
        p.base_url = None
        return p

    def _make_model(self, provider, *, capability="chat", model_id="gpt-4o",
                    is_default=True, is_enabled=True):
        m = MagicMock()
        m.id = uuid4()
        m.provider_id = provider.id
        m.provider = provider
        m.model_id = model_id
        m.capability = capability
        m.is_default = is_default
        m.is_enabled = is_enabled
        return m

    @patch("app.ai.provider_registry.ApiKeyEncryption")
    @patch("app.ai.provider_registry.settings")
    async def test_resolves_user_override_first(self, mock_settings, mock_enc_cls):
        """When a user-scoped provider exists, it takes priority over global."""
        mock_settings.ai_encryption_key = "fake-key"
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "sk-user-key"
        mock_enc_cls.return_value = mock_enc_instance

        user_id = uuid4()
        user_provider = self._make_provider(scope="user", user_id=user_id)
        user_model = self._make_model(user_provider, model_id="gpt-4o-user")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # First call (user scope) returns user model, second (global) not called
        mock_result.scalar_one_or_none.return_value = user_model
        mock_db.execute = AsyncMock(return_value=mock_result)

        registry = ProviderRegistry()
        adapter, model_id = await registry.get_chat_provider(mock_db, user_id=user_id)

        assert model_id == "gpt-4o-user"
        assert isinstance(adapter, OpenAIProvider)

    @patch("app.ai.provider_registry.ApiKeyEncryption")
    @patch("app.ai.provider_registry.settings")
    async def test_falls_back_to_global(self, mock_settings, mock_enc_cls):
        """When no user provider exists, falls back to global."""
        mock_settings.ai_encryption_key = "fake-key"
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "sk-global-key"
        mock_enc_cls.return_value = mock_enc_instance

        global_provider = self._make_provider(scope="global")
        global_model = self._make_model(global_provider, model_id="gpt-4o-global")

        mock_db = AsyncMock()
        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # User scope query returns None
                result.scalar_one_or_none.return_value = None
            else:
                # Global scope query returns global model
                result.scalar_one_or_none.return_value = global_model
            return result

        mock_db.execute = mock_execute

        registry = ProviderRegistry()
        adapter, model_id = await registry.get_chat_provider(mock_db, user_id=uuid4())

        assert model_id == "gpt-4o-global"
        assert isinstance(adapter, OpenAIProvider)

    async def test_raises_on_no_config(self):
        """When no provider is configured, raises ConfigurationError."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        registry = ProviderRegistry()
        with pytest.raises(ConfigurationError, match="No enabled AI provider"):
            await registry.get_chat_provider(mock_db, user_id=uuid4())

    @patch("app.ai.provider_registry.ApiKeyEncryption")
    @patch("app.ai.provider_registry.settings")
    async def test_embedding_always_global(self, mock_settings, mock_enc_cls):
        """Embedding provider is always resolved globally (no user_id param)."""
        mock_settings.ai_encryption_key = "fake-key"
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "sk-embed-key"
        mock_enc_cls.return_value = mock_enc_instance

        global_provider = self._make_provider(scope="global")
        embed_model = self._make_model(
            global_provider, capability="embedding", model_id="text-embedding-3-small"
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = embed_model
        mock_db.execute = AsyncMock(return_value=mock_result)

        registry = ProviderRegistry()
        adapter, model_id = await registry.get_embedding_provider(mock_db)

        assert model_id == "text-embedding-3-small"
        # get_embedding_provider does not accept user_id, confirming global-only
        assert isinstance(adapter, OpenAIProvider)

    @patch("app.ai.provider_registry.ApiKeyEncryption")
    @patch("app.ai.provider_registry.settings")
    async def test_vision_user_override(self, mock_settings, mock_enc_cls):
        """Vision provider supports user override like chat."""
        mock_settings.ai_encryption_key = "fake-key"
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "sk-vision-key"
        mock_enc_cls.return_value = mock_enc_instance

        user_id = uuid4()
        user_provider = self._make_provider(scope="user", user_id=user_id)
        vision_model = self._make_model(
            user_provider, capability="vision", model_id="gpt-4o-vision"
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = vision_model
        mock_db.execute = AsyncMock(return_value=mock_result)

        registry = ProviderRegistry()
        adapter, model_id = await registry.get_vision_provider(mock_db, user_id=user_id)

        assert model_id == "gpt-4o-vision"

    @patch("app.ai.provider_registry.ApiKeyEncryption")
    @patch("app.ai.provider_registry.settings")
    async def test_cache_invalidation_on_refresh(self, mock_settings, mock_enc_cls):
        """After refresh(), cached providers are cleared and re-resolved."""
        mock_settings.ai_encryption_key = "fake-key"
        mock_enc_instance = MagicMock()
        mock_enc_instance.decrypt.return_value = "sk-key"
        mock_enc_cls.return_value = mock_enc_instance

        provider = self._make_provider(scope="global")
        model = self._make_model(provider, model_id="gpt-4o")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        mock_db.execute = AsyncMock(return_value=mock_result)

        registry = ProviderRegistry()

        # First call caches
        adapter1, _ = await registry.get_chat_provider(mock_db)
        assert len(registry._cache) == 1

        # Refresh clears cache
        await registry.refresh()
        assert len(registry._cache) == 0

        # Second call re-populates cache
        adapter2, _ = await registry.get_chat_provider(mock_db)
        assert len(registry._cache) == 1
        # New instance should be different object
        assert adapter1 is not adapter2
