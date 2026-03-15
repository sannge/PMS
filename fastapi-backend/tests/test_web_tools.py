"""Unit tests for Blair AI agent web tools (web_search, scrape_url).

Tests cover:
- SSRF validation (_validate_url_safe) for private/internal IPs
- Rate limiting integration for both tools
- web_search: formatting, empty query, truncation
- scrape_url: text extraction, timeout handling
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.ai.agent.tools.context import (
    _tool_context,
    clear_tool_context,
    set_tool_context,
)
from app.ai.agent.tools.web_tools import (
    WEB_TOOLS,
    _validate_url_safe,
    scrape_url,
    web_search,
)
from app.ai.rate_limiter import RateLimitResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = str(uuid4())


def _setup_context(**overrides: object) -> dict:
    """Populate tool context with sensible defaults + overrides."""
    ctx = {
        "user_id": _USER_ID,
        "accessible_app_ids": [],
        "accessible_project_ids": [],
        "db_session_factory": MagicMock(),
        "provider_registry": MagicMock(),
    }
    ctx.update(overrides)
    set_tool_context(**{k: ctx[k] for k in (
        "user_id", "accessible_app_ids", "accessible_project_ids",
        "db_session_factory", "provider_registry",
    )})
    return ctx


def _clear() -> None:
    clear_tool_context()


def _make_rate_limit_result(allowed: bool = True) -> RateLimitResult:
    """Build a RateLimitResult stub."""
    from datetime import datetime, timezone
    return RateLimitResult(
        allowed=allowed,
        remaining=5 if allowed else 0,
        reset_at=datetime.now(timezone.utc),
        limit=20,
        reset_seconds=60,
    )


def _mock_getaddrinfo(ip: str):
    """Return a mock getaddrinfo that resolves to *ip*."""
    def _getaddrinfo(hostname, port, family=0, type_=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]
    return _getaddrinfo


# ---------------------------------------------------------------------------
# SSRF validation tests
# ---------------------------------------------------------------------------


class TestSSRFValidation:

    @pytest.mark.asyncio
    async def test_ssrf_blocks_metadata_ip(self):
        """169.254.169.254 (cloud metadata) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("169.254.169.254")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://metadata.internal/latest")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_localhost(self):
        """127.0.0.1 must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("127.0.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://localhost/admin")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_10(self):
        """10.0.0.1 (RFC 1918) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("10.0.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://internal.corp/api")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_172(self):
        """172.16.0.1 (RFC 1918) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("172.16.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://docker-host/api")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_192(self):
        """192.168.1.1 (RFC 1918) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("192.168.1.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://router.local/admin")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_non_http(self):
        """Non-http/https schemes must be rejected before DNS."""
        with pytest.raises(ValueError, match="Only http/https"):
            await _validate_url_safe("ftp://files.example.com/data.csv")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_dns_rebind(self):
        """A hostname resolving to a private IP must be blocked (DNS rebind)."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("10.255.255.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://evil-rebind.example.com/")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_shared_address_space(self):
        """100.64.0.1 (IANA Shared/CGNAT) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("100.64.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://cgnat-host.example.com/")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_this_host(self):
        """0.0.0.1 (this-host range) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("0.0.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://this-host.example.com/")

    @pytest.mark.asyncio
    async def test_ssrf_blocks_reserved(self):
        """240.0.0.1 (reserved) must be blocked."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("240.0.0.1")):
            with pytest.raises(ValueError, match="blocked address"):
                await _validate_url_safe("http://reserved.example.com/")

    @pytest.mark.asyncio
    async def test_ssrf_allows_public_ip(self):
        """8.8.8.8 (public) must be allowed."""
        with patch("socket.getaddrinfo", _mock_getaddrinfo("8.8.8.8")):
            # Should not raise
            await _validate_url_safe("http://example.com/page")


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------


class TestWebRateLimits:

    @pytest.mark.asyncio
    async def test_search_rate_limited(self):
        """web_search returns error when rate limit is exceeded."""
        _setup_context()
        try:
            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=False)
            )
            with patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ):
                result = await web_search.ainvoke({"query": "test query"})
            assert "Rate limit exceeded" in result
        finally:
            _clear()

    @pytest.mark.asyncio
    async def test_scrape_rate_limited(self):
        """scrape_url returns error when rate limit is exceeded."""
        _setup_context()
        try:
            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=False)
            )
            with patch(
                "socket.getaddrinfo", _mock_getaddrinfo("8.8.8.8")
            ), patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ):
                result = await scrape_url.ainvoke({"url": "https://example.com"})
            assert "Rate limit exceeded" in result
        finally:
            _clear()


# ---------------------------------------------------------------------------
# web_search tests
# ---------------------------------------------------------------------------


class TestWebSearch:

    @pytest.mark.asyncio
    async def test_search_returns_formatted(self):
        """web_search formats DDGS results with numbered titles and snippets."""
        _setup_context()
        try:
            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=True)
            )
            mock_results = [
                {"title": "Example Page", "href": "https://example.com", "body": "A snippet."},
                {"title": "Another Page", "href": "https://another.com", "body": "More info."},
            ]
            with patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ), patch(
                "duckduckgo_search.DDGS"
            ) as MockDDGS:
                mock_instance = MockDDGS.return_value
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                mock_instance.text.return_value = mock_results
                result = await web_search.ainvoke({"query": "test"})

            assert "1. **Example Page**" in result
            assert "https://example.com" in result
            assert "2. **Another Page**" in result
        finally:
            _clear()

    @pytest.mark.asyncio
    async def test_search_empty_query(self):
        """web_search rejects empty query strings."""
        _setup_context()
        try:
            result = await web_search.ainvoke({"query": ""})
            assert "empty" in result.lower()
        finally:
            _clear()

    @pytest.mark.asyncio
    async def test_search_truncates_output(self):
        """web_search truncates results exceeding MAX_TOOL_OUTPUT_CHARS."""
        _setup_context()
        try:
            from app.ai.agent_tools import MAX_TOOL_OUTPUT_CHARS

            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=True)
            )
            # Build results that will exceed the limit
            long_body = "X" * (MAX_TOOL_OUTPUT_CHARS + 500)
            mock_results = [
                {"title": "Big Page", "href": "https://big.com", "body": long_body},
            ]
            with patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ), patch(
                "duckduckgo_search.DDGS"
            ) as MockDDGS:
                mock_instance = MockDDGS.return_value
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                mock_instance.text.return_value = mock_results
                result = await web_search.ainvoke({"query": "test"})

            assert len(result) <= MAX_TOOL_OUTPUT_CHARS + 100  # allow for truncation message
            assert "truncated" in result
        finally:
            _clear()


# ---------------------------------------------------------------------------
# scrape_url tests
# ---------------------------------------------------------------------------


class TestScrapeUrl:

    @pytest.mark.asyncio
    async def test_scrape_extracts_text(self):
        """scrape_url extracts text content from HTML via trafilatura."""
        _setup_context()
        try:
            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=True)
            )

            # Mock httpx HEAD response (redirect check)
            mock_head_response = MagicMock()
            mock_head_response.is_redirect = False
            mock_head_response.headers = {"content-type": "text/html; charset=utf-8"}

            # Mock httpx streaming response
            mock_stream_response = AsyncMock()
            mock_stream_response.raise_for_status = MagicMock()
            mock_stream_response.is_redirect = False
            mock_stream_response.headers = {"content-type": "text/html; charset=utf-8"}

            async def _aiter_bytes(chunk_size=65536):
                yield b"<html><body><p>Hello World</p></body></html>"

            mock_stream_response.aiter_bytes = _aiter_bytes
            mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
            mock_stream_response.__aexit__ = AsyncMock(return_value=False)

            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_head_response)
            mock_client.stream = MagicMock(return_value=mock_stream_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")
            ), patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ), patch(
                "app.ai.rate_limiter._get_limits",
                return_value={"web_scrape": (10, 60), "web_search": (20, 60)},
            ), patch(
                "app.ai.config_service.get_agent_config"
            ) as mock_cfg, patch(
                "httpx.AsyncClient", return_value=mock_client
            ), patch(
                "trafilatura.extract", return_value="Hello World"
            ):
                mock_cfg.return_value.get_int = MagicMock(side_effect=lambda k, d: d)
                result = await scrape_url.ainvoke({"url": "https://example.com"})

            assert "Hello World" in result
            assert "[USER CONTENT START]" in result
        finally:
            _clear()

    @pytest.mark.asyncio
    async def test_scrape_timeout_handled(self):
        """scrape_url returns a friendly message on timeout."""
        _setup_context()
        try:
            import httpx

            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=True)
            )

            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")
            ), patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ), patch(
                "app.ai.config_service.get_agent_config"
            ) as mock_cfg, patch(
                "httpx.AsyncClient", return_value=mock_client
            ):
                mock_cfg.return_value.get_int = MagicMock(side_effect=lambda k, d: d)
                result = await scrape_url.ainvoke({"url": "https://slow.example.com"})

            assert "Timeout" in result
            assert "slow.example.com" in result
        finally:
            _clear()


# ---------------------------------------------------------------------------
# Export sanity
# ---------------------------------------------------------------------------


class TestScrapeContentTypeRejection:

    @pytest.mark.asyncio
    async def test_scrape_rejects_non_html_content_type(self):
        """scrape_url returns error for non-HTML content types like application/pdf."""
        _setup_context()
        try:
            mock_rl = MagicMock()
            mock_rl.check_and_increment = AsyncMock(
                return_value=_make_rate_limit_result(allowed=True)
            )

            # Mock HEAD response with content-type: application/pdf
            mock_head_response = MagicMock()
            mock_head_response.is_redirect = False
            mock_head_response.headers = {"content-type": "application/pdf"}

            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_head_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "socket.getaddrinfo", _mock_getaddrinfo("93.184.216.34")
            ), patch(
                "app.ai.rate_limiter.get_rate_limiter", return_value=mock_rl
            ), patch(
                "app.ai.config_service.get_agent_config"
            ) as mock_cfg, patch(
                "httpx.AsyncClient", return_value=mock_client
            ):
                mock_cfg.return_value.get_int = MagicMock(side_effect=lambda k, d: d)
                result = await scrape_url.ainvoke({"url": "https://example.com/file.pdf"})

            assert "non-HTML content type" in result
            assert "application/pdf" in result
        finally:
            _clear()


# ---------------------------------------------------------------------------
# Export sanity
# ---------------------------------------------------------------------------


class TestWebToolsExport:

    def test_web_tools_list(self):
        """WEB_TOOLS contains exactly 2 tools."""
        assert len(WEB_TOOLS) == 2
        tool_names = [t.name for t in WEB_TOOLS]
        assert "web_search" in tool_names
        assert "scrape_url" in tool_names
