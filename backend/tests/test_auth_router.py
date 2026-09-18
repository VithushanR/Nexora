"""
backend/tests/test_auth_router.py

Part D — tests for routers/auth.py (POST /auth/google)

Mocks only the Google verification boundary (verify_google_id_token),
then tests the REAL find_or_create_user() and REAL create_access_token()
end to end, so this actually proves the whole login flow produces a
usable, decodable JWT for a real internal user_id.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auth as auth_router_module
import auth.users as users_module
from routers.auth import router
from auth.jwt import decode_access_token


@pytest.fixture(autouse=True)
def clean_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_users.db"
    monkeypatch.setattr(users_module, "_DB_PATH", str(db_path))
    users_module._init_db()
    yield


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestGoogleLoginEndpoint:
    def test_valid_google_token_returns_usable_jwt(self, monkeypatch):
        fake_google_payload = {
            "sub": "google-sub-999",
            "email": "student@sliit.lk",
            "name": "Sura",
        }
        monkeypatch.setattr(
            auth_router_module,
            "verify_google_id_token",
            lambda token: fake_google_payload,
        )

        app = _make_test_app()
        client = TestClient(app)
        response = client.post(
            "/auth/google", json={"id_token": "fake-google-id-token"}
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

        # The returned token must be a REAL, decodable JWT for a REAL
        # internal user_id -- not just a string that looks right.
        decoded = decode_access_token(body["access_token"])
        assert "sub" in decoded  # this "sub" is OUR internal user_id, not Google's

    def test_same_google_account_gets_same_internal_user_across_logins(
        self, monkeypatch
    ):
        fake_google_payload = {
            "sub": "google-sub-consistent",
            "email": "consistent@sliit.lk",
        }
        monkeypatch.setattr(
            auth_router_module,
            "verify_google_id_token",
            lambda token: fake_google_payload,
        )

        app = _make_test_app()
        client = TestClient(app)

        first = client.post("/auth/google", json={"id_token": "token-1"}).json()
        second = client.post("/auth/google", json={"id_token": "token-2"}).json()

        first_user_id = decode_access_token(first["access_token"])["sub"]
        second_user_id = decode_access_token(second["access_token"])["sub"]

        assert first_user_id == second_user_id

    def test_invalid_google_token_returns_401(self, monkeypatch):
        def fake_verify_raises(token):
            raise ValueError("Invalid Google ID token: bad signature")

        monkeypatch.setattr(
            auth_router_module, "verify_google_id_token", fake_verify_raises
        )

        app = _make_test_app()
        client = TestClient(app)
        response = client.post("/auth/google", json={"id_token": "forged-token"})

        assert response.status_code == 401
        # Doesn't leak the specific internal failure reason to the client.
        assert "bad signature" not in response.json()["detail"].lower()

    def test_missing_id_token_in_body_returns_422(self):
        app = _make_test_app()
        client = TestClient(app)
        response = client.post("/auth/google", json={})
        assert response.status_code == 422  # FastAPI/Pydantic validation error

    def test_google_payload_missing_email_returns_400_not_500(self, monkeypatch):
        """
        Regression test: a Google payload with no "email" claim must
        produce a clean 400, not an unhandled ValueError from
        find_or_create_user() surfacing as a 500.
        """
        payload_without_email = {"sub": "google-sub-no-email"}
        monkeypatch.setattr(
            auth_router_module,
            "verify_google_id_token",
            lambda token: payload_without_email,
        )

        app = _make_test_app()
        client = TestClient(app)
        response = client.post("/auth/google", json={"id_token": "token-no-email"})

        assert response.status_code == 400
