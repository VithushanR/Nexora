"""
Shared plumbing for every source client: one rate-limited, retrying async
HTTP client per source, per your tech-stack decision (httpx + tenacity +
aiolimiter). Nothing here calls an LLM -- retrieval is fully deterministic.
"""

import html
import os
import re
import logging
from typing import Optional, overload
import httpx
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("nexora.sources")

#  Deliberately NOT a blanket "<[^>]+>": several of these sources (arXiv,
# Semantic Scholar) are math/CS abstracts where a bare "<" or ">" can be
# genuine inequality notation (e.g. "for x < 4 and y > 2"). Requiring the
# character right after "<" to be a letter -- real tag syntax always looks
# like <tagname ...> or </tagname>, never "< 4" or "<4" -- avoids treating
# that prose as markup while still catching real tags like <h4>, </h4>,
# <i>, <sub>, <a href="...">.
_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s+[^<>]*)?/?>")


@overload
def strip_html_tags(text: None) -> None: ...
@overload
def strip_html_tags(text: str) -> str: ...
def strip_html_tags(text: Optional[str]) -> Optional[str]:
    """Strips embedded HTML/XML markup from a source's raw abstract text.

    Some sources return structured abstracts with inline tags -- e.g. Europe
    PMC's abstractText commonly contains "<h4>Methods</h4>...<h4>Results</h4>"
    section headers (confirmed against real API responses), and OpenAlex's
    abstract_inverted_index can preserve the same tags verbatim as literal
    tokens when the underlying publisher text was JATS-tagged. Left
    unstripped, this markup doesn't just look wrong on screen -- it also
    reaches LLM screening/summarization prompts as if it were content.
    Applied at every source's abstract extraction point (not just the
    display layer) so the stored abstract is always clean text, however it
    will be used downstream.
    """
    if not text:
        return text
    without_tags = _TAG_RE.sub(" ", text)
    return " ".join(html.unescape(without_tags).split())

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL")
if not CONTACT_EMAIL:
    # No hardcoded fallback on purpose -- CONTACT_EMAIL is used as
    # attribution to OpenAlex/Crossref's "polite pool" and in outgoing
    # User-Agent headers. Silently substituting a placeholder here would
    # mean requests go out under an address nobody actually configured.
    # Fail loudly instead so a missing/unloaded .env is caught immediately,
    # not discovered later as a confusing rate-limit or API-behavior issue.
    logger.error("CONTACT_EMAIL is not set -- check that .env exists and is "
                 "actually loaded (e.g. load_dotenv() called before this module imports).")
    raise RuntimeError(
        "CONTACT_EMAIL environment variable is not set. This is required "
        "for OpenAlex/Crossref polite-pool attribution and outgoing "
        "User-Agent headers. Set it in your .env file and make sure "
        "load_dotenv() runs before backend.sources.base is imported."
    )

USER_AGENT = f"Nexora-Research-Agent/1.0 (mailto:{CONTACT_EMAIL})"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Per-source rate limits -- conservative, tuned per each API's published
# guidance. See docs/data-sources.md for the source of each number.
RATE_LIMITS = {
    "openalex": AsyncLimiter(10, 1),          # polite pool, mailto set
    "semantic_scholar": AsyncLimiter(1, 1),   # keyless / low-volume keyed tier
    "arxiv": AsyncLimiter(1, 3),               # arXiv etiquette: 1 req / 3s
    "europepmc": AsyncLimiter(2, 1),
    "crossref": AsyncLimiter(5, 1),
    "unpaywall": AsyncLimiter(2, 1),
    "core": AsyncLimiter(1, 1),
    "pmc": AsyncLimiter(2, 1),
}


class SourceUnavailableError(Exception):
    """Raised when a source could not be reached after retries. Callers
    catch this per-source and continue with whatever other sources
    succeeded -- one dead source must never fail the whole retrieval step."""


def retryable():
    """Standard retry policy for all source HTTP calls: 3 attempts,
    exponential backoff, only on transient errors (timeouts, 5xx, network)."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    )


async def get_json(client: httpx.AsyncClient, source: str, url: str, **kwargs) -> dict:
    """Rate-limited, retrying GET returning parsed JSON. Raises
    SourceUnavailableError (not the raw httpx exception) on final failure,
    so calling code has one exception type to catch per source."""
    limiter = RATE_LIMITS.get(source, AsyncLimiter(2, 1))

    @retryable()
    async def _do():
        async with limiter:
            r = await client.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT, **kwargs)
            r.raise_for_status()
            return r.json()

    try:
        return await _do()
    except Exception as e:
        raise SourceUnavailableError(f"{source}: {type(e).__name__}: {e}") from e


async def get_text(client: httpx.AsyncClient, source: str, url: str, **kwargs) -> str:
    limiter = RATE_LIMITS.get(source, AsyncLimiter(2, 1))

    @retryable()
    async def _do():
        async with limiter:
            r = await client.get(url, headers=DEFAULT_HEADERS, timeout=DEFAULT_TIMEOUT, **kwargs)
            r.raise_for_status()
            return r.text

    try:
        return await _do()
    except Exception as e:
        raise SourceUnavailableError(f"{source}: {type(e).__name__}: {e}") from e

async def get_bytes(client: httpx.AsyncClient, source: str, url: str, *,
                    timeout: httpx.Timeout | None = None, max_bytes: int | None = None,
                    **kwargs) -> bytes:
    """Rate-limited, retrying GET returning raw bytes -- used by Agent 3's
    full-text cascade to pull OA PDFs. Redirects are followed because most
    OA landing pages bounce through one or two hops before the real file.

    `max_bytes` guards against a mis-linked "PDF" that is actually a huge
    file: we stream and abort once the cap is passed, rather than pulling
    an unbounded download into memory.
    """
    limiter = RATE_LIMITS.get(source, AsyncLimiter(2, 1))

    @retryable()
    async def _do():
        async with limiter:
            async with client.stream("GET", url, headers=DEFAULT_HEADERS,
                                     timeout=timeout or DEFAULT_TIMEOUT,
                                     follow_redirects=True, **kwargs) as r:
                r.raise_for_status()
                chunks, total = [], 0
                async for chunk in r.aiter_bytes():
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise ValueError(f"response exceeded max_bytes ({max_bytes})")
                    chunks.append(chunk)
                return b"".join(chunks)

    try:
        return await _do()
    except Exception as e:
        raise SourceUnavailableError(f"{source}: {type(e).__name__}: {e}") from e
