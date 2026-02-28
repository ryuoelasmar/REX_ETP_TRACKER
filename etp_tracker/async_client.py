"""Async SEC EDGAR client with rate limiting and shared disk cache.

Drop-in concurrent fetcher that respects SEC's 10 req/s limit (capped at 8).
Reads and writes the same cache files as SECClient so they are fully
interchangeable.  Falls back gracefully when aiohttp is not installed.

Usage::

    from etp_tracker.async_client import fetch_submissions_async
    results = fetch_submissions_async(ciks, cache_dir, user_agent)
    # results = {cik: json_text_or_None, ...}
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import asyncio
    import aiohttp
    from aiolimiter import AsyncLimiter
    HAS_ASYNC = True
except ImportError:
    HAS_ASYNC = False
    log.warning(
        "aiohttp/aiolimiter not installed. Async client unavailable. "
        "pip install aiohttp aiolimiter"
    )

try:
    from .config import USER_AGENT_DEFAULT, SEC_SUBMISSIONS_URL
except Exception:
    USER_AGENT_DEFAULT = "REX-ETP-FilingTracker/1.0 (contact: set USER_AGENT)"
    SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{CIK_PADDED}.json"


class AsyncSECClient:
    """Async SEC EDGAR client with rate limiting and disk cache.

    Cache layout matches ``SECClient`` exactly:
    - submissions JSON  -> ``{cache_dir}/submissions/{cik_padded}.json``
    - arbitrary text    -> ``{cache_dir}/web/{sha256(url)}.txt``
    """

    def __init__(
        self,
        cache_dir: Path | str,
        user_agent: str,
        rate_limit: int = 8,
        request_timeout: int = 30,
        refresh_max_age_hours: float = 6.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "submissions").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "web").mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or USER_AGENT_DEFAULT
        self.rate_limit = rate_limit
        self.request_timeout = request_timeout
        self.refresh_max_age_hours = refresh_max_age_hours
        if HAS_ASYNC:
            self.limiter = AsyncLimiter(rate_limit, 1.0)
            self.sem = asyncio.Semaphore(rate_limit)

    # ------------------------------------------------------------------
    # Cache helpers -- mirror SECClient exactly
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_url(url: str) -> str:
        """SHA-256 hash of URL, matching SECClient._hash_url."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _web_cache_path(self, url: str) -> Path:
        """Cache path for arbitrary URLs (web/ subfolder, hash-based)."""
        return self.cache_dir / "web" / (self._hash_url(url) + ".txt")

    def _submissions_cache_path(self, cik_padded: str) -> Path:
        """Cache path for submissions JSON (submissions/ subfolder, CIK-based)."""
        return self.cache_dir / "submissions" / f"{cik_padded}.json"

    def _read_web_cache(self, url: str) -> Optional[str]:
        """Read web cache. Returns content or None."""
        path = self._web_cache_path(url)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        return None

    def _write_web_cache(self, url: str, content: str) -> None:
        """Write content to web cache."""
        path = self._web_cache_path(url)
        try:
            path.write_text(content, encoding="utf-8", errors="ignore")
        except Exception:
            pass

    def _read_submissions_cache(self, cik_padded: str) -> Optional[str]:
        """Read submissions cache if fresh. Returns JSON text or None."""
        path = self._submissions_cache_path(cik_padded)
        if not path.exists():
            return None
        try:
            age_hours = (time.time() - path.stat().st_mtime) / 3600.0
            if age_hours >= self.refresh_max_age_hours:
                return None
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _write_submissions_cache(self, cik_padded: str, content: str) -> None:
        """Write submissions JSON to cache."""
        path = self._submissions_cache_path(cik_padded)
        try:
            path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Async fetch primitives
    # ------------------------------------------------------------------

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> str:
        """Fetch a single URL with rate limiting. No caching (caller handles)."""
        async with self.sem:
            async with self.limiter:
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                async with session.get(
                    url, headers={"User-Agent": self.user_agent}, timeout=timeout
                ) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 10))
                        log.warning("Rate limited by SEC. Waiting %ds", retry_after)
                        await asyncio.sleep(retry_after)
                        # Retry once (recursive, re-acquires semaphore + limiter)
                        return await self._fetch_url(session, url)
                    resp.raise_for_status()
                    return await resp.text()

    # ------------------------------------------------------------------
    # Public: generic URL fetching (web cache)
    # ------------------------------------------------------------------

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        """Fetch a single URL with rate limiting and web cache."""
        cached = self._read_web_cache(url)
        if cached is not None:
            return cached
        content = await self._fetch_url(session, url)
        self._write_web_cache(url, content)
        return content

    async def fetch_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        """Fetch multiple URLs concurrently. Returns {url: content_or_None}."""
        if not HAS_ASYNC:
            raise RuntimeError("aiohttp/aiolimiter not installed")

        results: dict[str, Optional[str]] = {}
        async with aiohttp.ClientSession() as session:
            tasks = {url: asyncio.create_task(self.fetch(session, url)) for url in urls}
            for url, task in tasks.items():
                try:
                    results[url] = await task
                except Exception as exc:
                    log.error("Failed to fetch %s: %s", url, exc)
                    results[url] = None
        return results

    # ------------------------------------------------------------------
    # Public: submissions batch (submissions cache)
    # ------------------------------------------------------------------

    async def fetch_submissions_batch(
        self, ciks: list[str]
    ) -> dict[str, Optional[str]]:
        """Fetch submissions JSONs for multiple CIKs concurrently.

        Returns ``{cik: json_text_or_None}``.
        Uses the submissions/ cache subfolder (CIK-based filenames),
        matching SECClient.load_submissions_json exactly.
        """
        if not HAS_ASYNC:
            raise RuntimeError("aiohttp/aiolimiter not installed")

        # Build CIK -> padded CIK -> URL mapping
        cik_map: dict[str, tuple[str, str]] = {}  # cik -> (cik_padded, url)
        for cik in ciks:
            cik_padded = f"{int(str(cik)):010d}"
            url = SEC_SUBMISSIONS_URL.replace("{CIK_PADDED}", cik_padded)
            cik_map[str(cik)] = (cik_padded, url)

        results: dict[str, Optional[str]] = {}

        # Separate cached vs. needs-fetch
        to_fetch: dict[str, str] = {}  # cik -> url
        for cik, (cik_padded, url) in cik_map.items():
            cached = self._read_submissions_cache(cik_padded)
            if cached is not None:
                results[cik] = cached
            else:
                to_fetch[cik] = url

        if not to_fetch:
            log.info("All %d submissions served from cache", len(ciks))
            return results

        log.info(
            "Fetching %d submissions async (%d cached)",
            len(to_fetch),
            len(results),
        )

        # Fetch missing concurrently
        async with aiohttp.ClientSession() as session:
            tasks = {
                cik: asyncio.create_task(self._fetch_url(session, url))
                for cik, url in to_fetch.items()
            }
            for cik, task in tasks.items():
                cik_padded = cik_map[cik][0]
                try:
                    content = await task
                    # Validate it parses as JSON before caching
                    json.loads(content)
                    self._write_submissions_cache(cik_padded, content)
                    results[cik] = content
                except Exception as exc:
                    log.error("Failed to fetch submissions for CIK %s: %s", cik, exc)
                    results[cik] = None

        return results


# ------------------------------------------------------------------
# Synchronous entry points
# ------------------------------------------------------------------

def fetch_submissions_async(
    ciks: list[str],
    cache_dir: Path | str,
    user_agent: str,
    rate_limit: int = 8,
    refresh_max_age_hours: float = 6.0,
) -> Optional[dict[str, Optional[str]]]:
    """Synchronous entry point for async batch fetch.

    Returns ``{cik: json_text_or_None}`` or ``None`` if async libs missing.
    """
    if not HAS_ASYNC:
        log.warning("Async not available. Install: pip install aiohttp aiolimiter")
        return None
    client = AsyncSECClient(
        cache_dir=cache_dir,
        user_agent=user_agent,
        rate_limit=rate_limit,
        refresh_max_age_hours=refresh_max_age_hours,
    )
    return asyncio.run(client.fetch_submissions_batch(ciks))


def fetch_urls_async(
    urls: list[str],
    cache_dir: Path | str,
    user_agent: str,
    rate_limit: int = 8,
) -> Optional[dict[str, Optional[str]]]:
    """Synchronous entry point for async batch URL fetch (web cache).

    Returns ``{url: content_or_None}`` or ``None`` if async libs missing.
    """
    if not HAS_ASYNC:
        log.warning("Async not available. Install: pip install aiohttp aiolimiter")
        return None
    client = AsyncSECClient(
        cache_dir=cache_dir,
        user_agent=user_agent,
        rate_limit=rate_limit,
    )
    return asyncio.run(client.fetch_many(urls))
