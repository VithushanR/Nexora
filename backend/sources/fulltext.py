"""
Full-text cascade for Agent 3.

Seven strategies, tried in order, first success wins. Retrieval (Agent 2)
only guarantees an abstract; the methodology/results summaries in the
evidence table are far more useful when there is real full text behind
them, so this module works hard to find one before giving up.

    1. known_oa_pdf   -- OA PDF URL already carried in retrieval metadata
    2. arxiv          -- arXiv PDF by arxiv_id
    3. europepmc_xml  -- Europe PMC JATS full text (best for life sciences)
    4. pmc_pdf        -- PubMed Central OA PDF via DOI -> PMCID conversion
    5. unpaywall      -- every OA location Unpaywall knows, not just "best"
    6. core_fulltext  -- CORE's fullText field
    7. core_download  -- CORE's downloadUrl PDF (populated far more often)

Two guards keep this honest rather than merely productive:

  * PDF magic bytes are checked instead of Content-Type, because several OA
    servers (MDPI among them) don't set that header cleanly and genuine
    PDFs were being thrown away.
  * title_plausibly_matches() rejects text whose front matter doesn't
    overlap the expected title. Fetching *some* PDF is easy; fetching the
    *right* one is the part that matters, and a mis-fetched full text would
    poison the evidence row far worse than an honest abstract fallback.

Nothing here calls an LLM -- this is pure deterministic fetching.
"""

import io
import os
import re
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Callable, Optional

import httpx

from backend.sources.base import (
    get_bytes, get_text, get_json, DEFAULT_HEADERS,
    CONTACT_EMAIL, RATE_LIMITS,
)

logger = logging.getLogger("nexora.fulltext")

CORE_API_KEY = os.getenv("CORE_API_KEY", "")

PDF_TIMEOUT = httpx.Timeout(45.0, connect=10.0)
MAX_PDF_BYTES = 40 * 1024 * 1024     # 40 MB -- generous for a paper, bounded for us
MAX_PDF_PAGES = 20
MIN_USABLE_CHARS = 500               # below this, treat the fetch as failed
TITLE_MATCH_THRESHOLD = 0.4


# ------------------------------------------------------------------
# PDF handling
# ------------------------------------------------------------------

def _looks_like_pdf(content: bytes) -> bool:
    """Real magic bytes, not the Content-Type header -- see module docstring."""
    return content[:5] == b"%PDF-"


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])


async def _fetch_pdf_text(client: httpx.AsyncClient, source: str, url: Optional[str]) -> Optional[str]:
    """Downloads `url` and extracts text if it is genuinely a PDF. Returns
    None on any failure -- every strategy here is best-effort, so a dead
    URL must fall through to the next strategy rather than raise."""
    if not url:
        return None
    try:
        content = await get_bytes(client, source, url, timeout=PDF_TIMEOUT, max_bytes=MAX_PDF_BYTES)
    except Exception as e:
        logger.debug("PDF fetch failed (%s): %s", url, e)
        return None

    if not _looks_like_pdf(content):
        return None

    try:
        # Parsing a 20-page PDF is CPU-bound and blocking; keep it off the
        # event loop so concurrent paper processing isn't serialised by it.
        return await asyncio.to_thread(_extract_pdf_text, content)
    except Exception as e:
        logger.debug("PDF parse failed (%s): %s", url, e)
        return None


# ------------------------------------------------------------------
# Strategy 1 -- OA PDF URL already known from retrieval
# ------------------------------------------------------------------

async def fetch_known_oa_pdf(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    return await _fetch_pdf_text(client, "oa_pdf", paper.get("known_oa_pdf_url"))


# ------------------------------------------------------------------
# Strategy 2 -- arXiv
# ------------------------------------------------------------------

async def fetch_arxiv_fulltext(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    arxiv_id = paper.get("arxiv_id")
    if not arxiv_id:
        return None
    return await _fetch_pdf_text(client, "arxiv", f"https://arxiv.org/pdf/{arxiv_id}")


# ------------------------------------------------------------------
# Strategy 3 -- Europe PMC full-text XML
# ------------------------------------------------------------------

def _strip_xml_to_text(xml_string: str) -> Optional[str]:
    """Europe PMC returns JATS XML. Strip tags but emit <title> elements on
    their own line -- split_sections() downstream detects sections by
    heading lines, so flattening those away would defeat it."""
    try:
        root = ET.fromstring(xml_string)
    except Exception:
        return None

    parts: list[str] = []

    def walk(elem):
        if elem.tag.endswith("title") and elem.text:
            parts.append("\n" + elem.text.strip() + "\n")
        elif elem.text and elem.text.strip():
            parts.append(elem.text.strip())
        for child in elem:
            walk(child)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

    walk(root)
    return "\n".join(parts)


async def resolve_pmcid(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    """Uses a PMCID already in metadata if present, otherwise converts
    DOI -> PMCID via NCBI's free ID converter."""
    if paper.get("pmcid"):
        return paper["pmcid"]
    doi = paper.get("doi")
    if not doi:
        return None
    try:
        data = await get_json(
            client, "pmc", "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
            params={"ids": doi, "format": "json", "tool": "nexora", "email": CONTACT_EMAIL},
        )
    except Exception:
        return None
    records = data.get("records") or []
    return records[0].get("pmcid") if records else None


def _normalize_pmcid(pmcid: str) -> str:
    return pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"


async def fetch_europepmc_fulltext(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    pmcid = await resolve_pmcid(client, paper)
    if not pmcid:
        return None
    url = (f"https://www.ebi.ac.uk/europepmc/webservices/rest/"
           f"{_normalize_pmcid(pmcid)}/fullTextXML")
    try:
        raw = await get_text(client, "europepmc", url)
    except Exception:
        return None
    if not raw.strip().startswith("<"):
        return None
    return _strip_xml_to_text(raw)


# ------------------------------------------------------------------
# Strategy 4 -- PubMed Central OA PDF
# ------------------------------------------------------------------

async def fetch_pmc_pdf(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    pmcid = await resolve_pmcid(client, paper)
    if not pmcid:
        return None
    url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{_normalize_pmcid(pmcid)}/pdf/"
    return await _fetch_pdf_text(client, "pmc", url)


# ------------------------------------------------------------------
# Strategy 5 -- Unpaywall
# ------------------------------------------------------------------

async def fetch_unpaywall_fulltext(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    doi = paper.get("doi")
    if not doi:
        return None
    try:
        data = await get_json(client, "unpaywall", f"https://api.unpaywall.org/v2/{doi}",
                              params={"email": CONTACT_EMAIL})
    except Exception:
        return None

    # Try the best location first, then every other OA location. Unpaywall's
    # "best" is picked for licence clarity, not for whether the file
    # actually downloads, so the also-rans are worth walking.
    locations = [data.get("best_oa_location")] + (data.get("oa_locations") or [])
    for loc in locations:
        if not loc:
            continue
        for url_key in ("url_for_pdf", "url"):
            text = await _fetch_pdf_text(client, "unpaywall", loc.get(url_key))
            if text:
                return text
    return None


# ------------------------------------------------------------------
# Strategies 6 & 7 -- CORE
# ------------------------------------------------------------------

async def _core_search(client: httpx.AsyncClient, paper: dict) -> Optional[dict]:
    """CORE's search is a POST, so it doesn't fit base.get_json -- the
    limiter and headers still come from base so pacing stays uniform."""
    if not CORE_API_KEY:
        return None

    doi = paper.get("doi")
    query = f'doi:"{doi}"' if doi else (paper.get("title") or "")
    if not query:
        return None

    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {CORE_API_KEY}"}
    try:
        async with RATE_LIMITS["core"]:
            r = await client.post("https://api.core.ac.uk/v3/search/works",
                                  headers=headers, json={"q": query, "limit": 1},
                                  timeout=PDF_TIMEOUT)
            r.raise_for_status()
            results = r.json().get("results") or []
    except Exception as e:
        logger.debug("CORE search failed: %s", e)
        return None
    return results[0] if results else None


async def fetch_core_fulltext(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    work = await _core_search(client, paper)
    return work.get("fullText") if work else None


async def fetch_core_download_pdf(client: httpx.AsyncClient, paper: dict) -> Optional[str]:
    work = await _core_search(client, paper)
    if not work:
        return None
    return await _fetch_pdf_text(client, "core", work.get("downloadUrl"))


# ------------------------------------------------------------------
# Cascade
# ------------------------------------------------------------------

def title_plausibly_matches(expected_title: Optional[str], full_text: Optional[str],
                            min_word_overlap: float = TITLE_MATCH_THRESHOLD) -> bool:
    """Guards against fetching the wrong document or a garbled extraction.
    Looks for the title's content words in the text's front matter -- a real
    paper repeats its own title within the first page or so."""
    if not expected_title or not full_text:
        return False
    front_matter = full_text[:1500].lower()
    title_words = set(re.findall(r"[a-z]{4,}", expected_title.lower()))
    if not title_words:
        return True  # nothing to check against -- don't fail on a title of stopwords
    matched = sum(1 for w in title_words if w in front_matter)
    return (matched / len(title_words)) >= min_word_overlap


FULLTEXT_STRATEGIES: list[tuple[str, Callable]] = [
    ("known_oa_pdf", fetch_known_oa_pdf),
    ("arxiv", fetch_arxiv_fulltext),
    ("europepmc_xml", fetch_europepmc_fulltext),
    ("pmc_pdf", fetch_pmc_pdf),
    ("unpaywall", fetch_unpaywall_fulltext),
    ("core_fulltext", fetch_core_fulltext),
    ("core_download", fetch_core_download_pdf),
]


async def get_full_text(client: httpx.AsyncClient, paper: dict) -> tuple[Optional[str], Optional[str]]:
    """Tries every strategy in order. Returns (text, strategy_name) on the
    first success that clears both the length floor and the title check, or
    (None, None) if all seven fail -- which is a normal outcome, not an
    error, and the caller labels the row as abstract-derived."""
    title = paper.get("title")
    for name, fn in FULLTEXT_STRATEGIES:
        try:
            text = await fn(client, paper)
        except Exception as e:
            logger.debug("Strategy %s raised for %r: %s", name, (title or "")[:60], e)
            text = None

        if not text or len(text) <= MIN_USABLE_CHARS:
            continue

        if title_plausibly_matches(title, text):
            logger.info("Full text via %s (%d chars) for %r", name, len(text), (title or "")[:60])
            return text, name

        logger.info("Strategy %s returned text that did not match the title -- discarded (%r)",
                    name, (title or "")[:60])

    logger.info("No full text found for %r -- falling back to abstract", (title or "")[:60])
    return None, None
