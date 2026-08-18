"""
arXiv API client.

Responsibility:
- Query the arXiv Atom feed API and normalize results into the common
  candidate paper shape.
"""

from sources.base import BaseSourceClient


class ArxivClient(BaseSourceClient):
    def __init__(self):
        super().__init__(base_url="http://export.arxiv.org/api")

    # TODO: implement search(query: str) -> list[dict], parsing the Atom/XML response
    async def search(self, query: str) -> list[dict]:
        raise NotImplementedError
