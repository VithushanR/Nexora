"""
backend/auth/google_auth.py

Part D — Security Core: Google Sign-In verification.

Owned by: Part D
Used by: backend/routers/auth.py (the POST /auth/google endpoint)

Public surface:
    verify_google_id_token(id_token_str: str) -> dict

This module verifies an ID token the frontend received from Google's
Sign-In flow. It does NOT issue your app's own session tokens -- that is
still auth/jwt.py's job (create_access_token). This module's only
responsibility is: "is this ID token genuinely from Google, and was it
issued specifically for OUR app?"

Two checks matter here, and skipping either one defeats the point of
verifying at all:
    1. Signature verification -- confirms Google actually issued this
       token (handled internally by google.oauth2.id_token, which
       fetches and caches Google's public signing keys).
    2. Audience (aud) verification -- confirms the token was issued FOR
       THIS APPLICATION specifically, not some other app that also uses
       Google Sign-In. Without this check, a valid Google ID token
       issued to a completely different application could be replayed
       against this backend and would still pass signature verification,
       since it really is a genuine, unexpired, correctly-signed Google
       token -- just not one meant for us.

GOOGLE_OAUTH_CLIENT_ID is shared configuration, not a backend-only
secret: Part C (frontend) configures the same client ID in their Google
Sign-In button setup. Both sides must use the identical client ID or
verification here will always fail with an audience mismatch.

Fails loudly at import if GOOGLE_OAUTH_CLIENT_ID is missing, matching
the same pattern as JWT_SECRET_KEY and ENCRYPTION_KEY.
"""

import os
from typing import Any, Mapping

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

# ---------------------------------------------------------------------------
# Config — fail loudly, no silent fallback
# ---------------------------------------------------------------------------

GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
if not GOOGLE_OAUTH_CLIENT_ID:
    raise RuntimeError(
        "GOOGLE_OAUTH_CLIENT_ID is not set. Refusing to start without it, "
        "since it is required to verify the audience (aud) claim on Google "
        "ID tokens -- skipping this check would let a token issued for a "
        "different application be replayed against this backend. Set "
        "GOOGLE_OAUTH_CLIENT_ID in your environment or .env file. This must "
        "match the client ID Part C (frontend) configures for Google Sign-In."
    )

# A single shared Request object for verifying tokens. google-auth uses
# this to fetch (and internally cache) Google's public signing keys.
_google_request = google_requests.Request()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def verify_google_id_token(id_token_str: str) -> Mapping[str, Any]:
    """
    Verifies a Google ID token's signature AND that it was issued for
    this specific application (audience check).

    Args:
        id_token_str: the raw ID token string the frontend received from
            Google's Sign-In flow and forwarded to our backend.

    Returns:
        The decoded token payload as a dict. Notably includes:
            - "sub": Google's stable, unique identifier for this user
                     (use this, not "email", as the durable key for
                     find-or-create user lookups -- emails can change,
                     "sub" does not)
            - "email": the user's Google account email
            - "email_verified": bool
            - "name": display name, if available
            - "picture": profile photo URL, if available

    Raises:
        ValueError: if the token is invalid, expired, has a bad
            signature, or was NOT issued for this application (audience
            mismatch). All failure modes are collapsed into ValueError
            rather than distinguishing them, so callers don't need to
            import Google's exception types just to handle this --
            same reasoning as auth/jwt.py's decode_access_token().
    """
    if not id_token_str:
        raise ValueError("id_token_str must be a non-empty string")

    try:
        payload = google_id_token.verify_oauth2_token(
            id_token_str,
            _google_request,
            audience=GOOGLE_OAUTH_CLIENT_ID,
        )
    except Exception as e:
        # google-auth raises several distinct exception types for
        # different failure modes (expired, bad signature, wrong issuer,
        # wrong audience). Collapsing to ValueError here mirrors the
        # same design choice in auth/jwt.py's decode_access_token().
        raise ValueError(f"Invalid Google ID token: {e}") from e

    # Defense in depth: verify_oauth2_token already enforces the audience
    # match internally and raises on mismatch, so this should be
    # unreachable in practice -- but asserting it explicitly means a
    # future refactor that accidentally drops the audience= argument
    # fails loudly here instead of silently accepting tokens meant for
    # a different application.
    if payload.get("aud") != GOOGLE_OAUTH_CLIENT_ID:
        raise ValueError(
            "Google ID token audience does not match this application's "
            "GOOGLE_OAUTH_CLIENT_ID."
        )

    return payload
