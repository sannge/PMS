"""Web tools for Blair AI agent: search and scrape.

Provides ``web_search`` (DuckDuckGo) and ``scrape_url`` (trafilatura
text extraction) with SSRF protection and per-user rate limiting.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("100.64.0.0/10"),  # IANA Shared Address Space
    ipaddress.ip_network("0.0.0.0/8"),  # This host
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
]


async def _ssrf_request_hook(request: httpx.Request) -> None:
    """Re-validate DNS just before every HTTP request to prevent DNS rebinding."""
    hostname = request.url.host
    if not hostname:
        return
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        raise httpx.ConnectError(f"DNS resolution failed for {hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise httpx.ConnectError(f"Blocked: {hostname} resolves to private IP {ip}")


async def _validate_url_safe(url: str) -> None:
    """Validate that *url* does not resolve to a blocked (private/internal) IP.

    Raises:
        ValueError: If the URL scheme is not http/https, hostname is missing,
            DNS resolution fails, or any resolved IP falls in a blocked range.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")

    # DNS resolve
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError("URL resolves to a blocked address")


# ---------------------------------------------------------------------------
# Rate limit helper
# ---------------------------------------------------------------------------


async def _check_web_rate_limit(endpoint: str) -> str | None:
    """Check per-user rate limit for a web tool.

    Returns an error message string if the limit is exceeded, or ``None``
    if the request is allowed.
    """
    from .context import _get_user_id
    from ...rate_limiter import get_rate_limiter, _get_limits

    user_id = str(_get_user_id())
    rl = get_rate_limiter()
    limit, window = _get_limits().get(endpoint, (10, 60))
    result = await rl.check_and_increment(
        endpoint=endpoint,
        scope_id=user_id,
        limit=limit,
        window_seconds=window,
    )
    if not result.allowed:
        return f"Rate limit exceeded for {endpoint}. Please wait before trying again."
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns titles, URLs, and snippets.

    Use this to find current information, articles, documentation, or any
    web content. Chain with scrape_url to get full page content.

    Args:
        query: Search query (1-500 characters).
        max_results: Number of results to return (1-8, default 5).
    """
    # Validate
    if not query or not query.strip():
        return "Error: search query cannot be empty."
    query = query.strip()
    if len(query) > 500:
        return "Error: search query must be 500 characters or fewer."
    max_results = max(1, min(8, max_results))

    # Rate limit
    err = await _check_web_rate_limit("web_search")
    if err:
        return err

    try:
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import DuckDuckGoSearchException
    except ImportError:
        logger.error("duckduckgo-search package not installed")
        return "Web search unavailable: duckduckgo-search package is not installed."

    def _do_search() -> list[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            results = await asyncio.to_thread(_do_search)
            if not results:
                return f"No results found for: {query}"

            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "Untitled")
                url = r.get("href", "")
                snippet = r.get("body", "")
                lines.append(f"{i}. **{title}**\n   {url}\n   {snippet}")

            output = "\n\n".join(lines)
            from .helpers import _truncate, _wrap_user_content

            return _truncate(_wrap_user_content(output))
        except DuckDuckGoSearchException as e:
            last_err = e
            logger.warning("Web search attempt %d failed (DDG): %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
        except Exception as e:
            logger.exception("Web search failed (unexpected)")
            return f"Web search failed: {type(e).__name__}: {e}"

    logger.error("Web search failed after 3 attempts: %s", last_err)
    return f"Web search temporarily unavailable after 3 retries: {last_err}"


@tool
async def scrape_url(url: str) -> str:
    """Fetch a web page and extract its text content. SSRF-safe.

    Use this after web_search to get the full content of a specific page.
    Returns extracted text (no HTML tags).

    Args:
        url: The URL to fetch (http or https only).
    """
    if not url or not url.strip():
        return "Error: URL cannot be empty."
    url = url.strip()

    # SSRF check
    try:
        await _validate_url_safe(url)
    except ValueError as e:
        return f"Error: {e}"

    # Rate limit
    err = await _check_web_rate_limit("web_scrape")
    if err:
        return err

    from app.ai.config_service import get_agent_config

    try:
        cfg = get_agent_config()
        timeout = cfg.get_int("web.scrape_timeout", 10)
        max_bytes = cfg.get_int("web.scrape_max_bytes", 2_097_152)

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            event_hooks={"request": [_ssrf_request_hook]},
        ) as client:
            # Manual redirect loop with per-hop SSRF validation
            # Use HEAD requests for redirect following, then stream the final URL
            current_url = url
            for _redirect in range(5):
                head_response = await client.head(
                    current_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Blair/1.0)"},
                )
                if head_response.is_redirect:
                    location = head_response.headers.get("location", "")
                    if not location:
                        return "Error: redirect with no location header."
                    # Resolve relative redirects
                    from urllib.parse import urljoin

                    current_url = urljoin(str(head_response.url), str(location))
                    try:
                        await _validate_url_safe(current_url)
                    except ValueError as e:
                        return f"Error: redirect blocked — {e}"
                    continue
                break
            else:
                return "Error: too many redirects."

            # Content-Type check on the final URL
            content_type = head_response.headers.get("content-type", "")
            if content_type and not any(
                ct in content_type.lower() for ct in ("text/html", "text/plain", "application/xhtml")
            ):
                return f"Error: URL returned non-HTML content type: {content_type.split(';')[0]}"

            # Streaming GET with size cap to avoid full response buffering
            async with client.stream(
                "GET",
                current_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Blair/1.0)"},
            ) as response:
                response.raise_for_status()
                # Guard against servers that redirect on GET but not HEAD
                if response.is_redirect:
                    return f"Error: unexpected redirect on final GET from {current_url}"
                # Re-check Content-Type from the actual GET response
                get_ct = response.headers.get("content-type", "")
                if get_ct and not any(ct in get_ct.lower() for ct in ("text/html", "text/plain", "application/xhtml")):
                    return f"Error: URL returned non-HTML content type: {get_ct.split(';')[0]}"
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_bytes:
                        break
                content = b"".join(chunks)[:max_bytes]

            html = content.decode("utf-8", errors="replace")

        # Extract text with trafilatura
        try:
            import trafilatura

            text = await asyncio.to_thread(trafilatura.extract, html)
        except Exception:
            text = None

        # Fallback: basic tag stripping
        if not text:
            import re

            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return f"Could not extract text content from {url}"

        from .helpers import _truncate, _wrap_user_content

        return _truncate(_wrap_user_content(text))

    except httpx.TimeoutException:
        return f"Timeout fetching {url}. The page took too long to respond."
    except httpx.HTTPStatusError as e:
        return f"HTTP error {e.response.status_code} fetching {url}"
    except Exception:
        logger.exception("URL scrape failed")
        return f"Failed to fetch content from {url}. Please try a different URL."


# ---------------------------------------------------------------------------
# Public export
# ---------------------------------------------------------------------------

WEB_TOOLS = [web_search, scrape_url]
