"""
Crossref API client.

Responsibility:
- Query the Crossref works API and normalize results into the common
  candidate paper shape. Also used by Agent 3 to check retraction status.
"""

from sources.base import BaseSourceClient


class CrossrefClient(BaseSourceClient):
    def __init__(self):
        super().__init__(base_url="https://api.crossref.org")

    # TODO: implement search(query: str) -> list[dict] normalized to candidate schema
    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError

    # TODO: implement is_retracted(doi: str) -> bool for Agent 3 integrity checks
    async def is_retracted(self, doi: str) -> bool:
        raise NotImplementedError
