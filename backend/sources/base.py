"""
Shared base for source API clients.

Responsibility:
- Provide a common async httpx client with retry + exponential backoff
  (tenacity) and rate limiting (aiolimiter) that each concrete source
  client (openalex, semantic_scholar, crossref, arxiv, doaj) builds on.
"""

import httpx
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential


class BaseSourceClient:
    # TODO: accept base_url, rate limit, and headers per subclass
    def __init__(self, base_url: str, rate_limit_per_sec: float = 5.0):
        self.base_url = base_url
        self._limiter = AsyncLimiter(rate_limit_per_sec, 1)
        self._client = httpx.AsyncClient(base_url=base_url)

    # TODO: apply @retry(stop=stop_after_attempt(3), wait=wait_exponential(...))
    async def get(self, path: str, params: dict | None = None) -> httpx.Response:
        raise NotImplementedError

    async def aclose(self) -> None:
        await self._client.aclose()
