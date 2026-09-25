"""
backend/auth/jwt.py

Part D — Security Core: JWT issuing/verification + FastAPI auth dependency.

Owned by: Part D
Imported by: Part A (research.py routes), Part B (copilot.py routes),
             Part D's own documents.py

Public surface (do not rename without telling A/B):
    create_access_token(user_id: str) -> str
    decode_access_token(token: str) -> dict
    get_current_user(token: str = Depends(...)) -> str   # returns user_id

Design notes:
- Fails LOUDLY at import time if JWT_SECRET_KEY is missing, matching the
  "fail loudly if CONTACT_EMAIL missing" pattern used elsewhere in the repo.
  We do NOT want a silent fallback secret in prod.
- HS256 (symmetric) is sufficient here: only this backend issues and verifies
  tokens, there's no third-party token consumer.
- get_current_user() is a plain string user_id today. If you later need
  richer user objects, extend the return type here — every route already
  depends on this function, so it's the single choke point.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# ---------------------------------------------------------------------------
# Config — fail loudly, no silent fallback secret
# ---------------------------------------------------------------------------

_raw_jwt_secret_key = os.environ.get("JWT_SECRET_KEY")
if not _raw_jwt_secret_key:
    raise RuntimeError(
        "JWT_SECRET_KEY is not set. Refusing to start with no signing secret. "
        "Set JWT_SECRET_KEY in your environment or .env file."
    )
# Re-bound to a `str`-typed name after the guard above: os.environ.get()
# alone types this as `str | None`, and jwt.encode()/decode() require a
# non-optional key. The guard already makes None impossible here at
# runtime -- this just gives that guarantee a type pyright can see too,
# instead of a cast that would silently accept a real None.
JWT_SECRET_KEY: str = _raw_jwt_secret_key

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "60"))

# tokenUrl is a placeholder path for Swagger UI's "Authorize" button.
# It doesn't have to be a real login route yet, but keep it accurate
# once Part D builds an actual /auth/login endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    """
    Issue a signed JWT for the given user_id.

    `sub` (subject) carries the user_id — standard JWT claim name, so any
    downstream tooling (Swagger, jwt.io debugging) reads it correctly.
    """
    if not user_id:
        raise ValueError("user_id is required to create a token")

    expire_delta = timedelta(minutes=expires_minutes or JWT_EXPIRY_MINUTES)
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + expire_delta,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


def decode_access_token(token: str) -> dict:
    """
    Verify signature + expiry and return the decoded payload.

    Raises HTTPException(401) on any failure — expired, malformed, or
    bad signature all collapse to the same generic 401 message. We do NOT
    leak which specific check failed, since that's useful info to an attacker
    probing token validity.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency — the single choke point every protected route imports
# ---------------------------------------------------------------------------


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    FastAPI dependency. Usage in any router (Part A / Part B / Part D):

        from backend.auth.jwt import get_current_user

        @router.get("/research/{thread_id}/status")
        def get_status(thread_id: str, user_id: str = Depends(get_current_user)):
            ...

    Returns the user_id (str) extracted from the token's `sub` claim.
    Raises 401 if no token was supplied or it fails verification.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    return payload["sub"]
