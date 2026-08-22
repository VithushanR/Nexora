"""arXiv retrieval client. No key; XML API. The one source with genuine
full-text PDFs. Etiquette: max ~1 request / 3 seconds (enforced via the
shared arxiv rate limiter in base.py)."""

import xml.etree.ElementTree as ET
import httpx
from backend.sources.base import get_text

BASE_URL = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


async def search(client: httpx.AsyncClient, query: str, max_results: int = 15) -> list[dict]:
    params = {"search_query": query, "max_results": max_results}
    raw_xml = await get_text(client, "arxiv", BASE_URL, params=params)

    root = ET.fromstring(raw_xml)
    out = []
    for entry in root.findall("atom:entry", _NS):
        title_el = entry.find("atom:title", _NS)
        summary_el = entry.find("atom:summary", _NS)
        published_el = entry.find("atom:published", _NS)
        id_el = entry.find("atom:id", _NS)

        # Guard against the elements being missing AND against them being
        # present but empty (Element.text is Optional[str] even when the
        # element itself exists, e.g. <title></title> has .text == None).
        # This is what Pylance was flagging on the old .strip() calls below.
        if title_el is None or title_el.text is None:
            continue
        if summary_el is None or summary_el.text is None:
            continue
        if id_el is None or id_el.text is None:
            continue

        arxiv_id = id_el.text.strip().split("/abs/")[-1]

        year = None
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except ValueError:
                pass

        out.append({
            "title": title_el.text.strip().replace("\n", " "),
            "doi": None,
            "abstract": summary_el.text.strip().replace("\n", " "),
            "year": year,
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "pmcid": None,
            "known_oa_pdf_url": None,
        })
    return out