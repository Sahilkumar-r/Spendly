import re
from datetime import date
from pathlib import Path

import pytest

import app as app_module
from database import db

TEMPLATE = Path(app_module.app.root_path) / "templates" / "delete_expense.html"

TODAY = date.today().isoformat()
MISSING_ID = 99999


# ------------------------------------------------------------------ #
# Fixtures and helpers                                                #
# ------------------------------------------------------------------ #

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


@pytest.fixture
def new_user_client(client):
    """A freshly registered user with no expenses, logged in."""
    client.post(
        "/register",
        data={"name": "New User", "email": "new@example.com", "password": "password123"},
    )
    client.post("/login", data={"email": "new@example.com", "password": "password123"})
    return client


def _query(sql, params=()):
    conn = db.get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _count():
    return _query("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _user_id(email):
    return _query("SELECT id FROM users WHERE email = ?", (email,))[0]["id"]


def _demo_ids():
    return [
        r["id"]
        for r in _query(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id",
            (_user_id("demo@spendly.com"),),
        )
    ]


def _demo_expense_id():
    return _demo_ids()[0]


def _snapshot():
    return [dict(r) for r in _query("SELECT * FROM expenses ORDER BY id")]


def _exists(expense_id):
    return bool(_query("SELECT 1 FROM expenses WHERE id = ?", (expense_id,)))


def _set_description(expense_id, text):
    conn = db.get_db()
    try:
        conn.execute("UPDATE expenses SET description = ? WHERE id = ?", (text, expense_id))
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Auth guard and ownership                                            #
# ------------------------------------------------------------------ #

def test_get_delete_redirects_when_logged_out(client):
    resp = client.get(f"/expenses/{_demo_expense_id()}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_post_delete_redirects_when_logged_out_and_deletes_nothing(client):
    before = _snapshot()
    resp = client.post(f"/expenses/{_demo_expense_id()}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert _snapshot() == before


def test_other_users_expense_is_404_on_get_and_post(new_user_client):
    expense_id = _demo_expense_id()
    before = _snapshot()
    assert new_user_client.get(f"/expenses/{expense_id}/delete").status_code == 404
    assert new_user_client.post(f"/expenses/{expense_id}/delete").status_code == 404
    assert _snapshot() == before


def test_missing_expense_is_404_on_get_and_post(logged_in):
    before = _snapshot()
    assert logged_in.get(f"/expenses/{MISSING_ID}/delete").status_code == 404
    assert logged_in.post(f"/expenses/{MISSING_ID}/delete").status_code == 404
    assert _snapshot() == before


# ------------------------------------------------------------------ #
# Confirmation page (GET)                                             #
# ------------------------------------------------------------------ #

def test_get_shows_details_and_deletes_nothing(logged_in):
    expense_id = _demo_expense_id()
    stored = _query("SELECT * FROM expenses WHERE id = ?", (expense_id,))[0]
    before = _snapshot()

    resp = logged_in.get(f"/expenses/{expense_id}/delete")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert stored["date"] in html
    assert stored["description"] in html
    assert stored["category"] in html
    assert f"{stored['amount']:,.2f}" in html
    assert f'action="/expenses/{expense_id}/delete"' in html
    assert 'method="POST"' in html
    assert 'href="/profile"' in html, "Cancel link should return to the profile"
    assert _snapshot() == before, "GET must never modify data"


# ------------------------------------------------------------------ #
# Deleting (POST)                                                     #
# ------------------------------------------------------------------ #

def test_post_deletes_only_that_row_and_redirects(logged_in):
    expense_id = _demo_expense_id()
    before = _snapshot()

    resp = logged_in.post(f"/expenses/{expense_id}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    after = _snapshot()
    assert not _exists(expense_id)
    assert len(after) == len(before) - 1
    assert after == [row for row in before if row["id"] != expense_id]


def test_other_users_rows_untouched_by_delete(logged_in):
    # Give another user an expense, delete one of the demo user's own.
    logged_in.post(
        "/register",
        data={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = _user_id("other@example.com")
    db.create_expense(other_id, 5.0, "Food", TODAY, "Other's expense")
    other_before = [
        dict(r) for r in _query("SELECT * FROM expenses WHERE user_id = ?", (other_id,))
    ]

    assert logged_in.post(f"/expenses/{_demo_expense_id()}/delete").status_code == 302
    other_after = [
        dict(r) for r in _query("SELECT * FROM expenses WHERE user_id = ?", (other_id,))
    ]
    assert other_after == other_before


def test_second_post_for_same_id_is_404(logged_in):
    expense_id = _demo_expense_id()
    assert logged_in.post(f"/expenses/{expense_id}/delete").status_code == 302
    assert logged_in.post(f"/expenses/{expense_id}/delete").status_code == 404
    assert logged_in.get(f"/expenses/{expense_id}/delete").status_code == 404


def test_posted_user_id_and_id_are_ignored(logged_in):
    own_id = _demo_expense_id()
    other_user = _user_id("demo@spendly.com") + 100
    resp = logged_in.post(
        f"/expenses/{own_id}/delete",
        data={"user_id": str(other_user), "id": "999"},
    )
    assert resp.status_code == 302
    assert not _exists(own_id)


def test_cannot_delete_other_users_expense_by_posting_own_user_id(new_user_client):
    expense_id = _demo_expense_id()
    resp = new_user_client.post(
        f"/expenses/{expense_id}/delete",
        data={"user_id": str(_user_id("demo@spendly.com"))},
    )
    assert resp.status_code == 404
    assert _exists(expense_id)


# ------------------------------------------------------------------ #
# Effect on the profile page                                          #
# ------------------------------------------------------------------ #

def test_profile_updates_after_delete(logged_in):
    expense_id = _demo_expense_id()
    _set_description(expense_id, "Unique doomed expense")
    assert "Unique doomed expense" in logged_in.get("/profile").data.decode()

    logged_in.post(f"/expenses/{expense_id}/delete")
    html = logged_in.get("/profile").data.decode()
    assert "Unique doomed expense" not in html
    remaining = len(_demo_ids())
    assert re.search(rf'profile-stat-value">\s*{remaining}\s*<', html)
    percents = [int(p) for p in re.findall(r"(\d+)\s*%", html)]
    assert sum(percents) >= 100


def test_deleting_every_expense_shows_empty_state(logged_in):
    for expense_id in _demo_ids():
        assert logged_in.post(f"/expenses/{expense_id}/delete").status_code == 302
    html = logged_in.get("/profile").data.decode()
    assert "No transactions yet." in html
    assert _demo_ids() == []


def test_profile_has_delete_link_for_each_row(logged_in):
    html = logged_in.get("/profile").data.decode()
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    links = re.findall(r'href="/expenses/(\d+)/delete"', tbody)
    assert len(links) == tbody.count("<tr>") > 0
    assert str(_demo_expense_id()) in links or len(_demo_ids()) > 10


# ------------------------------------------------------------------ #
# Security                                                            #
# ------------------------------------------------------------------ #

def test_script_description_is_escaped_on_confirmation_page(logged_in):
    expense_id = _demo_expense_id()
    payload = "<script>alert(1)</script>"
    _set_description(expense_id, payload)
    html = logged_in.get(f"/expenses/{expense_id}/delete").data.decode()
    assert payload not in html
    assert "&lt;script&gt;" in html


# ------------------------------------------------------------------ #
# Regressions and hygiene                                             #
# ------------------------------------------------------------------ #

def test_edit_and_add_flows_still_work(logged_in):
    expense_id = _demo_expense_id()
    assert logged_in.get(f"/expenses/{expense_id}/edit").status_code == 200
    resp = logged_in.post(
        f"/expenses/{expense_id}/edit",
        data={"amount": "11.00", "category": "Food", "date": TODAY, "description": "x"},
    )
    assert resp.status_code == 302

    count = _count()
    resp = logged_in.post(
        "/expenses/add",
        data={"amount": "12.00", "category": "Food", "date": TODAY, "description": "y"},
    )
    assert resp.status_code == 302
    assert _count() == count + 1


def test_template_extends_base_and_has_no_hex_or_inline_style():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert '{% extends "base.html" %}' in source
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert "style=" not in source
    assert "<style" not in source
    assert "|safe" not in source
