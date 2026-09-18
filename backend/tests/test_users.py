"""
backend/tests/test_users.py

Part D — tests for auth/users.py
"""

import pytest

import auth.users as users_module
from auth.users import find_or_create_user


@pytest.fixture(autouse=True)
def clean_db(monkeypatch, tmp_path):
    """Fresh SQLite DB per test, isolated from the real uploads/ dir."""
    db_path = tmp_path / "test_users.db"
    monkeypatch.setattr(users_module, "_DB_PATH", str(db_path))
    users_module._init_db()
    yield


class TestFindOrCreateUser:
    def test_new_google_account_creates_new_user(self):
        user_id = find_or_create_user(
            google_sub="google-sub-123", email="alice@example.com", name="Alice"
        )
        assert user_id is not None
        assert isinstance(user_id, str)

    def test_same_google_sub_returns_same_user_id(self):
        """
        The core guarantee: the same Google account always maps to the
        same internal user_id, across every login -- this is what keeps
        ownership checks elsewhere in the app working correctly.
        """
        first_login = find_or_create_user(
            google_sub="google-sub-456", email="bob@example.com", name="Bob"
        )
        second_login = find_or_create_user(
            google_sub="google-sub-456", email="bob@example.com", name="Bob"
        )
        assert first_login == second_login

    def test_different_google_accounts_get_different_user_ids(self):
        user_a = find_or_create_user(google_sub="sub-a", email="a@example.com")
        user_b = find_or_create_user(google_sub="sub-b", email="b@example.com")
        assert user_a != user_b

    def test_email_change_does_not_change_user_id(self):
        """
        google_sub is the durable key, not email -- a user changing
        their Google account's email must keep the same internal
        user_id and therefore keep all their existing documents/threads.
        """
        original_user_id = find_or_create_user(
            google_sub="sub-durable", email="old-email@example.com"
        )
        after_email_change = find_or_create_user(
            google_sub="sub-durable", email="new-email@example.com"
        )
        assert original_user_id == after_email_change

    def test_email_is_updated_on_repeat_login(self):
        find_or_create_user(google_sub="sub-update", email="old@example.com")
        find_or_create_user(google_sub="sub-update", email="new@example.com")

        conn = users_module._get_db()
        row = conn.execute(
            "SELECT email FROM users WHERE google_sub = ?", ("sub-update",)
        ).fetchone()
        conn.close()
        assert row["email"] == "new@example.com"

    def test_missing_google_sub_raises_value_error(self):
        with pytest.raises(ValueError):
            find_or_create_user(google_sub="", email="x@example.com")

    def test_missing_email_raises_value_error(self):
        with pytest.raises(ValueError):
            find_or_create_user(google_sub="sub-x", email="")

    def test_name_is_optional(self):
        user_id = find_or_create_user(
            google_sub="sub-noname", email="noname@example.com"
        )
        assert user_id is not None

    def test_repeated_calls_for_new_sub_never_crash_on_unique_constraint(self):
        """
        Regression test for a check-then-act race: find_or_create_user
        must be safe to call multiple times in a row for the SAME
        brand-new google_sub without raising sqlite3.IntegrityError on
        the UNIQUE(google_sub) constraint. This simulates what would
        happen under concurrent first-time logins (double-click, two
        tabs) even though this test itself runs sequentially -- the
        underlying atomic upsert is what actually prevents the crash,
        not test timing.
        """
        results = [
            find_or_create_user(google_sub="sub-concurrent", email="race@example.com")
            for _ in range(5)
        ]
        assert len(set(results)) == 1  # all five calls agree on one user_id
