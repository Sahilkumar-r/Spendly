import re
import sqlite3
from datetime import date
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


# ------------------------------------------------------------------ #
# Date filter                                                         #
# ------------------------------------------------------------------ #

def _day(n):
    return date.today().replace(day=n).isoformat()


def _rows(html):
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    return tbody.count("<tr>")


def _filtered(client, **params):
    return client.get("/profile", query_string=params).data.decode()


def test_filter_form_renders_without_filter(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert 'name="start_date"' in html
    assert 'name="end_date"' in html
    assert "Apply" in html
    assert 'href="/profile">Clear' in html
    assert _rows(html) == 8


def test_filter_range_is_inclusive(logged_in):
    html = _filtered(logged_in, start_date=_day(4), end_date=_day(12))
    assert _rows(html) == 4
    assert date.today().replace(day=4).strftime("%d %b %Y") in html
    assert date.today().replace(day=12).strftime("%d %b %Y") in html


def test_filter_start_only(logged_in):
    assert _rows(_filtered(logged_in, start_date=_day(15))) == 3


def test_filter_end_only(logged_in):
    assert _rows(_filtered(logged_in, end_date=_day(4))) == 2


def test_filter_updates_stats_and_categories(logged_in):
    html = _filtered(logged_in, start_date=_day(4), end_date=_day(12))
    # 120.50 + 1800.00 + 350.75 + 600.00
    assert "₹2,871.25" in html
    assert "Shopping" not in html.split("Spending by category")[1]
    assert sum(int(p) for p in re.findall(r"· (\d+)%", html)) == 100


def test_filter_inputs_are_prefilled(logged_in):
    html = _filtered(logged_in, start_date=_day(4), end_date=_day(12))
    assert f'value="{_day(4)}"' in html
    assert f'value="{_day(12)}"' in html


def test_filter_empty_range(logged_in):
    html = _filtered(logged_in, start_date=_day(3), end_date=_day(3))
    assert "₹0.00" in html
    assert "No transactions in this period." in html
    assert "No spending in this period." in html
    assert "No transactions yet." not in html


def test_filter_start_after_end_shows_error(logged_in):
    resp = logged_in.get(
        "/profile", query_string={"start_date": _day(20), "end_date": _day(5)}
    )
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "Start date must be on or before end date." in html
    assert _rows(html) == 8


@pytest.mark.parametrize(
    "bad", ["abc", "2026-13-01", "2026-02-30", "2026-1-5", "01/02/2026",
            "2026-01-01' OR '1'='1"]
)
def test_filter_malformed_date_is_handled(logged_in, bad):
    resp = logged_in.get("/profile", query_string={"start_date": bad})
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "Enter valid dates in YYYY-MM-DD format." in html
    assert _rows(html) == 8


def test_filter_blank_params_are_ignored(logged_in):
    resp = logged_in.get("/profile?start_date=&end_date=")
    html = resp.data.decode()
    assert resp.status_code == 200
    assert "auth-error" not in html
    assert _rows(html) == 8


def test_filter_only_shows_own_expenses(client):
    client.post(
        "/register",
        data={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    conn = sqlite3.connect(db.DB_PATH)
    other_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("other@example.com",)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_id, 999.0, "Food", _day(6), "Other secret"),
    )
    conn.commit()
    conn.close()

    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    html = _filtered(client, start_date=_day(1), end_date=_day(28))
    assert "Other secret" not in html

    client.post("/logout")
    client.post("/login", data={"email": "other@example.com", "password": "password123"})
    html = _filtered(client, start_date=_day(1), end_date=_day(28))
    assert "Other secret" in html
    assert _rows(html) == 1


def test_filter_requires_login(client):
    resp = client.get("/profile?start_date=2026-01-01")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
