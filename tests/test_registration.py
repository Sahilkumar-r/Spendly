import sqlite3

import pytest
from werkzeug.security import check_password_hash

import app as app_module
from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def all_users():
    conn = db.get_db()
    try:
        return conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()


def register(client, name="Rahul Sharma", email="rahul@example.com", password="password123"):
    return client.post("/register", data={"name": name, "email": email, "password": password})


def test_get_renders_form(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert b'name="name"' in resp.data
    assert b'name="email"' in resp.data
    assert b'name="password"' in resp.data


def test_valid_registration_redirects_and_stores_hashed_user(client):
    resp = register(client, name="  Rahul Sharma ", email="  Rahul@Example.COM ")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    users = all_users()
    assert len(users) == 1
    assert users[0]["name"] == "Rahul Sharma"
    assert users[0]["email"] == "rahul@example.com"
    assert users[0]["password_hash"] != "password123"
    assert check_password_hash(users[0]["password_hash"], "password123")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"email": ""},
        {"password": ""},
        {"name": "   "},
    ],
)
def test_empty_field_rejected(client, kwargs):
    resp = register(client, **kwargs)
    assert resp.status_code == 200
    assert b"All fields are required" in resp.data
    assert all_users() == []


def test_short_password_rejected(client):
    resp = register(client, password="short")
    assert resp.status_code == 200
    assert b"at least 8 characters" in resp.data
    assert all_users() == []


@pytest.mark.parametrize("email", ["abc", "@example.com", "rahul@"])
def test_invalid_email_rejected(client, email):
    resp = register(client, email=email)
    assert resp.status_code == 200
    assert b"valid email" in resp.data
    assert all_users() == []


def test_duplicate_email_rejected_case_insensitive(client):
    assert register(client).status_code == 302
    resp = register(client, name="Other", email="RAHUL@example.com")
    assert resp.status_code == 200
    assert b"already exists" in resp.data
    assert len(all_users()) == 1


def test_failed_submit_prefills_name_and_email_but_not_password(client):
    resp = register(client, name="Rahul Sharma", email="rahul@example.com", password="short")
    assert b'value="Rahul Sharma"' in resp.data
    assert b'value="rahul@example.com"' in resp.data
    assert b"short" not in resp.data.replace(b"Password must be at least 8 characters.", b"")
