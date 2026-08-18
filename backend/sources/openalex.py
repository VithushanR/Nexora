"""
OpenAlex API client.

Responsibility:
- Query the OpenAlex works API (uses OPENALEX_MAILTO for the polite pool)
  and normalize results into the common candidate paper shape.
"""

from config import get_settings
from sources.base import BaseSourceClient


class OpenAlexClient(BaseSourceClient):
    def __init__(self):
        # TODO: pass mailto param from settings for the polite pool
        super().__init__(base_url="https://api.openalex.org")

    # TODO: implement search(query: str) -> list[dict] normalized to candidate schema
    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError
