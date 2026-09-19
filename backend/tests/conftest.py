"""
Shared pytest setup.

CONTACT_EMAIL must be in the environment *before* backend.sources.base is
imported -- that module raises at import time when it is missing, by
design, so that a missing .env is caught immediately instead of surfacing
later as a confusing rate-limit problem. conftest.py runs before test
modules are collected, which makes this the right place to guarantee it.

backend/config.py now also calls load_dotenv() itself (anchored to
backend/.env) as soon as it's imported. That call is NOT a substitute for
the one below, though: this file doesn't import backend.config, so nothing
would load .env into os.environ before the setdefault() calls run if this
call were removed -- the "real .env wins" guarantee below would silently
stop holding. Keeping it here is deliberate, harmless redundancy (dotenv's
load_dotenv() is idempotent), not an oversight.

A real .env wins if one exists; the placeholder below only keeps the suite
runnable in CI, where there is no .env and no outbound request is made
anyway because every source call in these tests is mocked.
"""

import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("CONTACT_EMAIL", "tests@nexora.local")
os.environ.setdefault("OPENALEX_MAILTO", "tests@nexora.local")
os.environ.setdefault("JWT_SECRET_KEY", "nexora-test-only-jwt-secret")

# auth/google_auth.py and auth/encryption.py both raise RuntimeError at
# import time (by design) when their required env var is missing -- same
# fail-loud pattern as CONTACT_EMAIL above. Test-only placeholders keep the
# suite collectible without a fully populated real .env; a real .env still
# wins if one exists, and no test in this suite makes a real Google/network
# call or relies on ENCRYPTION_KEY decrypting anything encrypted elsewhere.
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "nexora-test-only.apps.googleusercontent.com")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
