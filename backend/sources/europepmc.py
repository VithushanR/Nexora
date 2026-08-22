"""Europe PMC retrieval client. No key. Best free source for medical /
life-science full text -- flags OA availability directly in search results.
Docs: https://europepmc.org/RestfulWebService"""

import httpx
from backend.sources.base import get_json

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


async def search(client: httpx.AsyncClient, query: str, page_size: int = 15) -> list[dict]:
    params = {"query": query, "format": "json", "pageSize": page_size, "resultType": "core"}
    data = await get_json(client, "europepmc", BASE_URL, params=params)

    out = []
    for res in data.get("resultList", {}).get("result", []):
        year = None
        pub_year = res.get("pubYear", "")
        if pub_year.isdigit():
            year = int(pub_year)

        out.append({
            "title": res.get("title"),
            "doi": res.get("doi"),
            "abstract": res.get("abstractText") or "",
            "year": year,
            "source": "europepmc",
            "arxiv_id": None,
            "pmcid": res.get("pmcid"),
            "known_oa_pdf_url": None,
            "epmc_has_fulltext": res.get("inEPMC") == "Y" or res.get("isOpenAccess") == "Y",
        })
    return out