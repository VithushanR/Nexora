"""OpenAlex retrieval client. No key required; mailto= gives the polite-pool
rate tier. Docs: https://docs.openalex.org/api-entities/works"""

import httpx
from backend.sources.base import get_json, CONTACT_EMAIL, SourceUnavailableError

BASE_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


async def search(client: httpx.AsyncClient, query: str, per_page: int = 15) -> list[dict]:
    """Returns a list of candidate dicts in the shared shape used across
    all source clients. Raises SourceUnavailableError on failure -- callers
    must catch this per source, per the retrieval node's design."""
    params = {"search": query, "per-page": per_page, "mailto": CONTACT_EMAIL}
    data = await get_json(client, "openalex", BASE_URL, params=params)

    out = []
    for w in data.get("results", []):
        best_oa = w.get("best_oa_location") or {}
        oa_info = w.get("open_access") or {}
        ids = w.get("ids") or {}
        pmcid = ids.get("pmcid")
        if pmcid:
            pmcid = pmcid.rsplit("/", 1)[-1]

        out.append({
            "title": w.get("title"),
            "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
            "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
            "year": w.get("publication_year"),
            "source": "openalex",
            "arxiv_id": None,
            "pmcid": pmcid,
            "known_oa_pdf_url": best_oa.get("pdf_url") or oa_info.get("oa_url"),
        })
    return out  