"""
Shared pytest setup.

CONTACT_EMAIL must be in the environment *before* backend.sources.base is
imported -- that module raises at import time when it is missing, by
design, so that a missing .env is caught immediately instead of surfacing
later as a confusing rate-limit problem. conftest.py runs before test
modules are collected, which makes this the right place to guarantee it.

A real .env wins if one exists; the placeholder below only keeps the suite
runnable in CI, where there is no .env and no outbound request is made
anyway because every source call in these tests is mocked.
"""

import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("CONTACT_EMAIL", "tests@nexora.local")
os.environ.setdefault("OPENALEX_MAILTO", "tests@nexora.local")
