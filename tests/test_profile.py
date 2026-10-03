import re
from pathlib import Path

import pytest

import app as app_module
from database import db

TEMPLATE = Path(app_module.app.root_path) / "templates" / "profile.html"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


def test_profile_redirects_when_logged_out(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_ok_when_logged_in(logged_in):
    assert logged_in.get("/profile").status_code == 200


def test_profile_shows_user_card(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "Member since" in html
    assert ">DU<" in html


def test_profile_shows_the_signed_in_user_not_the_demo_user(client):
    client.post(
        "/register",
        data={"name": "Priya Reddy", "email": "priya@example.com", "password": "password123"},
    )
    client.post("/login", data={"email": "priya@example.com", "password": "password123"})
    html = client.get("/profile").data.decode()
    assert "Priya Reddy" in html
    assert "priya@example.com" in html
    assert ">PR<" in html
    assert "Demo User" not in html


def test_profile_shows_summary_stats(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert html.count('class="profile-stat"') == 3
    assert "₹6,121.49" in html
    assert ">Shopping<" in html


def test_profile_shows_transaction_rows(logged_in):
    html = logged_in.get("/profile").data.decode()
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    assert tbody.count("<tr>") == 8
    assert "Electricity bill" in tbody


def test_profile_shows_category_breakdown(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert html.count('class="profile-cat ') >= 3


def test_profile_percentages_sum_to_100(logged_in):
    html = logged_in.get("/profile").data.decode()
    percents = [int(x) for x in re.findall(r"· (\d+)%", html)]
    assert sum(percents) == 100


def test_profile_empty_state_for_new_user(client):
    client.post(
        "/register",
        data={"name": "New User", "email": "new@example.com", "password": "password123"},
    )
    client.post("/login", data={"email": "new@example.com", "password": "password123"})
    resp = client.get("/profile")
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "No transactions yet." in html
    assert "No spending to break down yet." in html
    assert "₹0.00" in html


def test_profile_only_shows_own_expenses(client):
    client.post(
        "/register",
        data={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    client.post("/login", data={"email": "other@example.com", "password": "password123"})
    html = client.get("/profile").data.decode()
    assert "Electricity bill" not in html


def test_navbar_shows_logged_in_state(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert "Sign out" in html


def test_template_has_no_hex_colours_or_inline_styles():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert "style=" not in source
