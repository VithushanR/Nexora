"""
backend/routers/auth.py

Part D — Authentication endpoint: Google Sign-In.

Owns: this file
Depends on: auth/google_auth.py (verify_google_id_token),
            auth/users.py (find_or_create_user),
            auth/jwt.py (create_access_token)

Endpoint:
    POST /auth/google -> {"access_token": "string", "token_type": "bearer"}

Flow (see auth/google_auth.py's module docstring for the full diagram):
    1. Frontend runs Google's Sign-In flow, gets an ID token from Google.
    2. Frontend POSTs that ID token here.
    3. We verify it's genuinely from Google AND issued for this specific
       app (audience check) -- auth/google_auth.py.
    4. We find or create this app's own internal user_id for that Google
       account -- auth/users.py.
    5. We issue our own JWT for that internal user_id -- auth/jwt.py,
       completely unchanged from what Part D already built.
    6. Frontend uses that JWT as the Bearer token on every other
       request (documents, research, copilot, etc.) via get_current_user().

GOOGLE_OAUTH_CLIENT_ID is shared config with Part C (frontend) -- both
sides must use the identical value or every login attempt will fail
with an audience mismatch inside verify_google_id_token().
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from auth.google_auth import verify_google_id_token
from auth.jwt import create_access_token
from auth.users import find_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    id_token: str


class GoogleLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/google", response_model=GoogleLoginResponse)
async def login_with_google(body: GoogleLoginRequest):
    """
    Verifies a Google ID token and returns this app's own JWT.

    Returns 401 (not a raw exception) for any verification failure --
    invalid token, expired, wrong signature, or wrong audience -- rather
    than leaking which specific check failed, matching the same
    non-disclosure pattern used in auth/jwt.py's decode_access_token().
    """
    try:
        google_payload = verify_google_id_token(body.id_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credentials.",
        )

    google_sub = google_payload["sub"]
    email = google_payload.get("email", "")
    name = google_payload.get("name")

    if not email:
        # Extremely unlikely with standard Google Sign-In scopes (email
        # is included by default), but find_or_create_user() requires a
        # non-empty email and raises ValueError otherwise -- catching
        # this here first turns a would-be 500 into a clear 400 instead.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account did not provide an email address.",
        )

    user_id = find_or_create_user(google_sub=google_sub, email=email, name=name)

    access_token = create_access_token(user_id)

    return GoogleLoginResponse(access_token=access_token)
