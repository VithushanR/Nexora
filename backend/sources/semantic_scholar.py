"""
Semantic Scholar API client.

Responsibility:
- Query the Semantic Scholar Graph API (optionally authenticated via
  SEMANTIC_SCHOLAR_API_KEY for higher rate limits) and normalize results
  into the common candidate paper shape.
"""

from config import get_settings
from sources.base import BaseSourceClient


class SemanticScholarClient(BaseSourceClient):
    def __init__(self):
        # TODO: attach API key header from settings if present
        super().__init__(base_url="https://api.semanticscholar.org/graph/v1")

    # TODO: implement search(query: str) -> list[dict] normalized to candidate schema
    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError
