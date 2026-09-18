"""
backend/tests/test_google_auth.py

Part D — tests for auth/google_auth.py

Mocks google.oauth2.id_token.verify_oauth2_token (the one genuinely
external boundary -- actually calling Google's servers is neither
possible nor desirable in a test suite), while testing OUR OWN logic
around it for real: that we pass the audience parameter at all, that we
double-check the aud claim ourselves as defense in depth, and that
failures are collapsed into ValueError consistently.
"""

import pytest

import auth.google_auth as google_auth_module
from auth.google_auth import verify_google_id_token, GOOGLE_OAUTH_CLIENT_ID


class TestVerifyGoogleIdToken:
    def test_valid_token_returns_payload(self, monkeypatch):
        fake_payload = {
            "sub": "1234567890",
            "email": "student@example.com",
            "email_verified": True,
            "name": "Test Student",
            "aud": GOOGLE_OAUTH_CLIENT_ID,
        }

        def fake_verify(id_token, request, audience=None):
            assert audience == GOOGLE_OAUTH_CLIENT_ID  # confirm we actually pass it
            return fake_payload

        monkeypatch.setattr(
            google_auth_module.google_id_token, "verify_oauth2_token", fake_verify
        )

        result = verify_google_id_token("some-fake-token")
        assert result["sub"] == "1234567890"
        assert result["email"] == "student@example.com"

    def test_audience_is_always_passed_explicitly(self, monkeypatch):
        """
        The whole point of the fix: audience must never be omitted or
        None, or the aud check silently doesn't happen.
        """
        captured = {}

        def fake_verify(id_token, request, audience=None):
            captured["audience"] = audience
            return {"sub": "x", "email": "x@x.com", "aud": audience}

        monkeypatch.setattr(
            google_auth_module.google_id_token, "verify_oauth2_token", fake_verify
        )

        verify_google_id_token("some-token")
        assert captured["audience"] is not None
        assert captured["audience"] == GOOGLE_OAUTH_CLIENT_ID

    def test_google_raises_on_bad_signature_becomes_value_error(self, monkeypatch):
        def fake_verify(id_token, request, audience=None):
            raise ValueError(
                "Token used too early"
            )  # google-auth's own exception shape

        monkeypatch.setattr(
            google_auth_module.google_id_token, "verify_oauth2_token", fake_verify
        )

        with pytest.raises(ValueError):
            verify_google_id_token("bad-token")

    def test_wrong_audience_raises_value_error(self, monkeypatch):
        """
        Simulates a token that was genuinely issued by Google, but for
        a DIFFERENT application -- this is exactly the replay scenario
        the audience check exists to prevent.
        """

        def fake_verify(id_token, request, audience=None):
            raise ValueError(
                f"Token has wrong audience some-other-client-id, expected {audience}"
            )

        monkeypatch.setattr(
            google_auth_module.google_id_token, "verify_oauth2_token", fake_verify
        )

        with pytest.raises(ValueError, match="audience"):
            verify_google_id_token("token-for-a-different-app")

    def test_defense_in_depth_audience_recheck(self, monkeypatch):
        """
        Even if verify_oauth2_token somehow returned a payload with a
        mismatched aud (e.g. a future library bug, or the audience=
        argument accidentally being dropped in a refactor), our own
        explicit re-check must still catch it rather than trusting the
        library blindly.
        """

        def fake_verify_that_forgot_to_check(id_token, request, audience=None):
            # Simulates a payload that slipped through with the wrong audience.
            return {"sub": "123", "email": "x@x.com", "aud": "some-other-app-client-id"}

        monkeypatch.setattr(
            google_auth_module.google_id_token,
            "verify_oauth2_token",
            fake_verify_that_forgot_to_check,
        )

        with pytest.raises(ValueError, match="audience"):
            verify_google_id_token("token-with-mismatched-aud")

    def test_empty_token_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_google_id_token("")
