import pytest

import app as app_module
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def register(client, email="rahul@example.com", password="password123"):
    return client.post(
        "/register", data={"name": "Rahul Sharma", "email": email, "password": password}
    )


def login(client, email="rahul@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password})


def test_register_then_login_redirects_to_profile(client):
    register(client)
    resp = login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")
    with client.session_transaction() as sess:
        assert sess["user_id"]
        assert sess["user_name"] == "Rahul Sharma"


def test_seeded_demo_user_can_login(client):
    resp = login(client, "demo@spendly.com", "demo123")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


@pytest.mark.parametrize(
    "email,password",
    [
        ("rahul@example.com", "wrongpassword"),
        ("nobody@example.com", "password123"),
    ],
)
def test_bad_credentials_show_generic_error(client, email, password):
    register(client)
    resp = login(client, email, password)
    assert resp.status_code == 200
    assert b"Invalid email or password." in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_email_is_case_and_whitespace_insensitive(client):
    register(client)
    resp = login(client, "  RAHUL@Example.com ")
    assert resp.status_code == 302


def test_failed_login_prefills_email_not_password(client):
    register(client)
    resp = login(client, "rahul@example.com", "wrongpassword")
    assert b'value="rahul@example.com"' in resp.data
    assert b"wrongpassword" not in resp.data


def test_logged_in_visit_to_login_redirects_to_profile(client):
    register(client)
    login(client)
    resp = client.get("/login")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


def test_navbar_reflects_login_state(client):
    register(client)
    anon = client.get("/").data
    assert b"Sign in" in anon
    assert b"Get started" in anon
    assert b"Sign out" not in anon

    login(client)
    authed = client.get("/").data
    assert b"Rahul Sharma" in authed
    assert b"Sign out" in authed
    assert b"Get started" not in authed


def test_logout_clears_session_and_redirects_home(client):
    register(client)
    login(client)
    resp = client.post("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert b"Sign in" in client.get("/").data


def test_get_logout_not_allowed(client):
    register(client)
    login(client)
    assert client.get("/logout").status_code == 405
    with client.session_transaction() as sess:
        assert "user_id" in sess
