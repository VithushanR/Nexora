"""
DOAJ (Directory of Open Access Journals) API client.

Responsibility:
- Query the DOAJ articles API and normalize results into the common
  candidate paper shape.

Not wired into backend/agents/retrieval_screening.py's SOURCE_CLIENTS --
this is an unimplemented stub, not a fifth active source. It follows the
same shape as the four real clients (openalex.py, semantic_scholar.py,
arxiv.py, europepmc.py: async search(client, query) -> list[dict]) so it
can be wired in later with no signature changes elsewhere. The previous
version of this file imported a `BaseSourceClient` class-based pattern
that was never actually implemented anywhere in backend/sources/base.py --
this rewrite matches what the rest of this package actually does.
"""

import httpx

BASE_URL = "https://doaj.org/api"


async def search(client: httpx.AsyncClient, query: str) -> list[dict]:
    # TODO: implement search(query) -> list[dict] normalized to candidate schema
    raise NotImplementedError
