"""
Application configuration.

Responsibility:
- Load environment variables from .env (GEMINI_API_KEY, OPENALEX_MAILTO,
  SEMANTIC_SCHOLAR_API_KEY, etc.).
- Expose a cached Settings object for the rest of the app to import.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Must run before any other backend module reads an env var at import time
# (backend/auth/jwt.py, backend/auth/google_auth.py, backend/auth/encryption.py,
# backend/sources/base.py all raise RuntimeError at import if their required
# var is missing). Anchored to this file's own directory -- not a bare
# load_dotenv() -- so it finds backend/.env regardless of the process's
# current working directory (repo root vs. backend/).
load_dotenv(Path(__file__).resolve().parent / ".env")


def _missing_database_url() -> str:
    raise RuntimeError(
        "DATABASE_URL is not set. Configure the shared PostgreSQL connection "
        "string in the environment or backend/.env."
    )


def _missing_checkpoint_database_url() -> str:
    raise RuntimeError(
        "CHECKPOINT_DATABASE_URL is not set. Configure the PostgreSQL "
        "checkpoint connection string in the environment or backend/.env."
    )


class Settings(BaseSettings):
    # TODO: add fields for every var in .env.example
    gemini_api_key: str = ""
    openalex_mailto: str = ""
    semantic_scholar_api_key: str | None = None
    nvidia_api_key: str = ""
    database_url: str = Field(default_factory=_missing_database_url)
    checkpoint_database_url: str = Field(
        default_factory=_missing_checkpoint_database_url
    )
    sqlite_db_path: str = "nexora_checkpoints.sqlite"
    thread_metadata_db_path: str = "nexora_threads.sqlite"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    # TODO: consider validation / fail-fast on missing required keys
    return Settings()
