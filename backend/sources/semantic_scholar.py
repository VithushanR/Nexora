"""Semantic Scholar retrieval client. Works keyless at low volume; an
optional API key raises limits. Docs: https://api.semanticscholar.org/api-docs/graph"""

import os
import logging
import httpx
from backend.sources.base import get_json, DEFAULT_HEADERS

logger = logging.getLogger("nexora.sources.semantic_scholar")

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

if not API_KEY:
    # Not a hard failure -- unlike CONTACT_EMAIL, Semantic Scholar is
    # documented as working keyless at low volume. This is a visible
    # warning, not a silent gap, so a missing key shows up in logs
    # instead of only being discovered later as unexplained rate limiting.
    logger.warning("SEMANTIC_SCHOLAR_API_KEY is not set -- running keyless. "
                   "This works at low volume but rate limits are tighter than "
                   "with a key. Set SEMANTIC_SCHOLAR_API_KEY in .env to raise limits.")


async def search(client: httpx.AsyncClient, query: str, limit: int = 15) -> list[dict]:
    headers = dict(DEFAULT_HEADERS)
    if API_KEY:
        headers["x-api-key"] = API_KEY
    params = {"query": query, "limit": limit, "fields": "title,abstract,year,externalIds,openAccessPdf"}

    from backend.sources.base import RATE_LIMITS, retryable, SourceUnavailableError

    @retryable()
    async def _do():
        async with RATE_LIMITS["semantic_scholar"]:
            r = await client.get(BASE_URL, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            return r.json()

    try:
        data = await _do()
    except Exception as e:
        raise SourceUnavailableError(f"semantic_scholar: {type(e).__name__}: {e}") from e

    out = []
    for p in data.get("data", []):
        ext = p.get("externalIds") or {}
        out.append({
            "title": p.get("title"),
            "doi": ext.get("DOI"),
            "abstract": p.get("abstract") or "",
            "year": p.get("year"),
            "source": "semantic_scholar",
            "arxiv_id": ext.get("ArXiv"),
            "pmcid": ext.get("PubMedCentral"),
            "known_oa_pdf_url": (p.get("openAccessPdf") or {}).get("url"),
        })
    return out