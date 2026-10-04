import re
from datetime import date
from pathlib import Path

import pytest

import app as app_module
from database import db

TEMPLATE = Path(app_module.app.root_path) / "templates" / "edit_expense.html"

MAX_DESCRIPTION_LENGTH = app_module.MAX_DESCRIPTION_LENGTH
MAX_AMOUNT = app_module.MAX_AMOUNT

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


def _demo_expense_id():
    return _query(
        "SELECT id FROM expenses WHERE user_id = ? ORDER BY id LIMIT 1",
        (_user_id("demo@spendly.com"),),
    )[0]["id"]


def _row(expense_id):
    return dict(_query("SELECT * FROM expenses WHERE id = ?", (expense_id,))[0])


def _valid(**overrides):
    data = {
        "amount": "10.00",
        "category": "Food",
        "date": TODAY,
        "description": "Lunch",
    }
    data.update(overrides)
    return data


def _post(client, expense_id, **overrides):
    return client.post(f"/expenses/{expense_id}/edit", data=_valid(**overrides))


def _assert_rejected(client, expense_id, data):
    before = _row(expense_id)
    count = _count()
    resp = client.post(f"/expenses/{expense_id}/edit", data=data)
    assert resp.status_code == 200, "Validation failure must re-render with 200"
    html = resp.data.decode()
    assert 'name="amount"' in html, "Form should be re-rendered"
    assert "auth-error" in html, "An error message should be shown"
    assert _row(expense_id) == before, "Row must be unchanged on failure"
    assert _count() == count
    return html


# ------------------------------------------------------------------ #
# Auth guard and ownership                                            #
# ------------------------------------------------------------------ #

def test_get_edit_redirects_when_logged_out(client):
    resp = client.get(f"/expenses/{_demo_expense_id()}/edit")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_post_edit_redirects_when_logged_out_and_changes_nothing(client):
    expense_id = _demo_expense_id()
    before = _row(expense_id)
    resp = _post(client, expense_id, amount="1.00")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert _row(expense_id) == before


def test_get_other_users_expense_is_404(new_user_client):
    assert new_user_client.get(f"/expenses/{_demo_expense_id()}/edit").status_code == 404


def test_post_other_users_expense_is_404_and_unchanged(new_user_client):
    expense_id = _demo_expense_id()
    before = _row(expense_id)
    assert _post(new_user_client, expense_id, amount="1.00").status_code == 404
    # Invalid data must still 404 first, never reveal the expense exists.
    assert _post(new_user_client, expense_id, amount="abc").status_code == 404
    assert _row(expense_id) == before


def test_missing_expense_is_404_on_get_and_post(logged_in):
    assert logged_in.get(f"/expenses/{MISSING_ID}/edit").status_code == 404
    assert _post(logged_in, MISSING_ID).status_code == 404


# ------------------------------------------------------------------ #
# GET pre-fill                                                        #
# ------------------------------------------------------------------ #

def test_get_prefills_stored_values(logged_in):
    expense_id = _demo_expense_id()
    stored = _row(expense_id)
    resp = logged_in.get(f"/expenses/{expense_id}/edit")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert f'value="{stored["amount"]:.2f}"' in html
    assert f'value="{stored["date"]}"' in html
    assert f'value="{stored["description"]}"' in html
    assert re.search(
        rf'<option value="{stored["category"]}"\s+selected', html
    ), "Stored category should be selected"
    assert f"/expenses/{expense_id}/edit" in html, "Form should post to the edit URL"


# ------------------------------------------------------------------ #
# Successful edit                                                     #
# ------------------------------------------------------------------ #

def test_valid_edit_updates_row_in_place_and_redirects(logged_in):
    expense_id = _demo_expense_id()
    before = _row(expense_id)
    count = _count()

    resp = _post(
        logged_in, expense_id,
        amount="123.456", category="Health", date="2026-01-15", description="  Checkup  ",
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")

    after = _row(expense_id)
    assert after["amount"] == 123.46
    assert after["category"] == "Health"
    assert after["date"] == "2026-01-15"
    assert after["description"] == "Checkup"
    assert after["id"] == before["id"]
    assert after["user_id"] == before["user_id"]
    assert after["created_at"] == before["created_at"]
    assert _count() == count, "Edit must not create a row"


def test_edit_shows_on_profile_and_percentages_sum_to_100(logged_in):
    expense_id = _demo_expense_id()
    _post(logged_in, expense_id, amount="777.00", category="Other",
          date=TODAY, description="Edited thing")
    html = logged_in.get("/profile").data.decode()
    assert "Edited thing" in html
    assert "777.00" in html
    percents = [int(p) for p in re.findall(r"(\d+)\s*%", html)]
    assert sum(percents) >= 100


def test_blank_description_is_stored_as_null(logged_in):
    expense_id = _demo_expense_id()
    resp = _post(logged_in, expense_id, description="   ")
    assert resp.status_code == 302
    assert _row(expense_id)["description"] is None


def test_posted_user_id_and_id_are_ignored(logged_in):
    expense_id = _demo_expense_id()
    owner = _row(expense_id)["user_id"]
    other_user = owner + 100
    resp = logged_in.post(
        f"/expenses/{expense_id}/edit",
        data=_valid(user_id=str(other_user), id="999"),
    )
    assert resp.status_code == 302
    after = _row(expense_id)
    assert after["user_id"] == owner
    assert after["id"] == expense_id


# ------------------------------------------------------------------ #
# Validation failures                                                 #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "amount",
    ["0", "-5", "abc", "", "nan", "inf", "-inf", str(MAX_AMOUNT + 1)],
)
def test_invalid_amount_rejected(logged_in, amount):
    _assert_rejected(logged_in, _demo_expense_id(), _valid(amount=amount))


def test_unknown_category_rejected(logged_in):
    _assert_rejected(logged_in, _demo_expense_id(), _valid(category="Hacking"))


def test_missing_category_rejected(logged_in):
    data = _valid()
    del data["category"]
    _assert_rejected(logged_in, _demo_expense_id(), data)


@pytest.mark.parametrize("bad_date", ["2026-1-5", "abc", "2026-02-30", ""])
def test_invalid_date_rejected(logged_in, bad_date):
    _assert_rejected(logged_in, _demo_expense_id(), _valid(date=bad_date))


def test_missing_date_rejected(logged_in):
    data = _valid()
    del data["date"]
    _assert_rejected(logged_in, _demo_expense_id(), data)


def test_description_too_long_rejected(logged_in):
    _assert_rejected(
        logged_in, _demo_expense_id(),
        _valid(description="x" * (MAX_DESCRIPTION_LENGTH + 1)),
    )


def test_description_at_limit_accepted(logged_in):
    expense_id = _demo_expense_id()
    resp = _post(logged_in, expense_id, description="x" * MAX_DESCRIPTION_LENGTH)
    assert resp.status_code == 302


def test_entered_values_retained_after_failed_submit(logged_in):
    html = _assert_rejected(
        logged_in, _demo_expense_id(),
        _valid(amount="-5", description="Keep me", date="2026-03-04", category="Bills"),
    )
    assert 'value="-5"' in html
    assert 'value="Keep me"' in html
    assert 'value="2026-03-04"' in html
    assert re.search(r'<option value="Bills"\s+selected', html)


# ------------------------------------------------------------------ #
# Security                                                            #
# ------------------------------------------------------------------ #

def test_sql_injection_description_stored_as_text(logged_in):
    expense_id = _demo_expense_id()
    payload = "'); DROP TABLE expenses;--"
    assert _post(logged_in, expense_id, description=payload).status_code == 302
    assert _row(expense_id)["description"] == payload
    assert _count() > 0, "expenses table must be intact"


def test_script_description_is_escaped_on_profile_and_form(logged_in):
    expense_id = _demo_expense_id()
    payload = "<script>alert(1)</script>"
    assert _post(logged_in, expense_id, description=payload).status_code == 302

    profile = logged_in.get("/profile").data.decode()
    assert payload not in profile
    assert "&lt;script&gt;" in profile

    form = logged_in.get(f"/expenses/{expense_id}/edit").data.decode()
    assert payload not in form
    assert "&lt;script&gt;" in form


# ------------------------------------------------------------------ #
# Profile entry point and regressions                                 #
# ------------------------------------------------------------------ #

def test_profile_has_edit_link_for_each_row(logged_in):
    html = logged_in.get("/profile").data.decode()
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    links = re.findall(r'href="/expenses/(\d+)/edit"', tbody)
    assert len(links) == tbody.count("<tr>") > 0
    assert str(_demo_expense_id()) in links


def test_empty_profile_state_still_renders(new_user_client):
    resp = new_user_client.get("/profile")
    assert resp.status_code == 200
    assert 'colspan="5"' in resp.data.decode()


def test_add_expense_still_works(logged_in):
    count = _count()
    assert logged_in.get("/expenses/add").status_code == 200
    resp = logged_in.post("/expenses/add", data=_valid())
    assert resp.status_code == 302
    assert _count() == count + 1


def test_template_extends_base_and_has_no_hex_or_inline_style():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert '{% extends "base.html" %}' in source
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)
    assert "style=" not in source
    assert "<style" not in source
