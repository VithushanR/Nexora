"""
Application configuration.

Responsibility:
- Load environment variables from .env (GEMINI_API_KEY, OPENALEX_MAILTO,
  SEMANTIC_SCHOLAR_API_KEY, etc.).
- Expose a cached Settings object for the rest of the app to import.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # TODO: add fields for every var in .env.example
    gemini_api_key: str = ""
    openalex_mailto: str = ""
    semantic_scholar_api_key: str | None = None

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    # TODO: consider validation / fail-fast on missing required keys
    return Settings()
