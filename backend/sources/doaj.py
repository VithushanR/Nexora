"""
DOAJ (Directory of Open Access Journals) API client.

Responsibility:
- Query the DOAJ articles API and normalize results into the common
  candidate paper shape.
"""

from sources.base import BaseSourceClient


class DoajClient(BaseSourceClient):
    def __init__(self):
        super().__init__(base_url="https://doaj.org/api")

    # TODO: implement search(query: str) -> list[dict] normalized to candidate schema
    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError
