import re
from datetime import date
from pathlib import Path

import pytest

import app as app_module
from database import db

TEMPLATE = Path(app_module.app.root_path) / "templates" / "add_expense.html"

CATEGORIES = app_module.CATEGORIES
MAX_DESCRIPTION_LENGTH = app_module.MAX_DESCRIPTION_LENGTH
MAX_AMOUNT = app_module.MAX_AMOUNT

TODAY = date.today().isoformat()


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


def _valid(**overrides):
    data = {
        "amount": "10.00",
        "category": "Food",
        "date": TODAY,
        "description": "Lunch",
    }
    data.update(overrides)
    return data


def _rows(html):
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    return tbody.count("<tr>")


def _assert_rejected(client, data):
    before = _count()
    resp = client.post("/expenses/add", data=data)
    assert resp.status_code == 200, "Validation failure must re-render with 200"
    html = resp.data.decode()
    assert 'name="amount"' in html, "Form should be re-rendered"
    assert "error" in html.lower(), "An error message should be shown"
    assert _count() == before, "No row should be inserted on failure"
    return html


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

def test_get_add_expense_redirects_when_logged_out(client):
    resp = client.get("/expenses/add")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_post_add_expense_redirects_when_logged_out_and_inserts_nothing(client):
    before = _count()
    resp = client.post("/expenses/add", data=_valid())
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
    assert _count() == before, "Logged-out POST must not insert"


# ------------------------------------------------------------------ #
# GET form                                                            #
# ------------------------------------------------------------------ #

def test_get_form_renders_four_fields(logged_in):
    resp = logged_in.get("/expenses/add")
    html = resp.data.decode()
    assert resp.status_code == 200
    for name in ("amount", "category", "date", "description"):
        assert f'name="{name}"' in html, f"Missing field {name}"


def test_get_form_lists_all_seven_categories(logged_in):
    html = logged_in.get("/expenses/add").data.decode()
    for cat in CATEGORIES:
        assert cat in html, f"Missing category {cat}"


def test_get_form_prefills_today(logged_in):
    html = logged_in.get("/expenses/add").data.decode()
    assert f'value="{TODAY}"' in html


def test_profile_links_to_add_expense(logged_in):
    html = logged_in.get("/profile").data.decode()
    assert 'href="/expenses/add"' in html
    assert "Add expense" in html


def test_profile_empty_state_links_to_add_expense(new_user_client):
    html = new_user_client.get("/profile").data.decode()
    assert "No transactions yet." in html
    assert 'href="/expenses/add"' in html


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #

def test_valid_post_redirects_to_profile(logged_in):
    resp = logged_in.post("/expenses/add", data=_valid())
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/profile")


def test_valid_post_saves_row_under_session_user(logged_in):
    before = _count()
    logged_in.post(
        "/expenses/add",
        data=_valid(amount="42.50", category="Health", description="Pharmacy run"),
    )
    assert _count() == before + 1
    row = _query(
        "SELECT * FROM expenses WHERE description = ?", ("Pharmacy run",)
    )[0]
    assert row["user_id"] == _user_id("demo@spendly.com")
    assert row["amount"] == 42.5
    assert row["category"] == "Health"
    assert row["date"] == TODAY


def test_new_expense_appears_first_on_profile(new_user_client):
    new_user_client.post(
        "/expenses/add",
        data=_valid(amount="77.25", category="Transport", description="Cab ride"),
    )
    resp = new_user_client.get("/profile")
    html = resp.data.decode()
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    first_row = tbody.split("</tr>")[0]
    assert "Cab ride" in first_row
    assert "77.25" in first_row
    assert "Transport" in first_row
    assert date.today().strftime("%d %b %Y") in first_row


def test_profile_totals_and_breakdown_update(logged_in):
    before_total = _query("SELECT SUM(amount) AS t FROM expenses")[0]["t"]
    before_rows = _count()
    logged_in.post(
        "/expenses/add", data=_valid(amount="10.00", description="Extra snack")
    )
    html = logged_in.get("/profile").data.decode()
    assert f"₹{before_total + 10:,.2f}" in html
    assert _rows(html) == before_rows + 1
    assert "Extra snack" in html
    percents = [int(x) for x in re.findall(r"· (\d+)%", html)]
    assert percents and sum(percents) == 100


@pytest.mark.parametrize("description", ["", "    "])
def test_blank_description_stored_as_null(logged_in, description):
    logged_in.post("/expenses/add", data=_valid(description=description))
    rows = _query(
        "SELECT description FROM expenses WHERE user_id = ? AND amount = 10.0 "
        "AND date = ?",
        (_user_id("demo@spendly.com"), TODAY),
    )
    assert len(rows) == 1
    assert rows[0]["description"] is None


def test_description_of_200_chars_accepted(logged_in):
    desc = "a" * MAX_DESCRIPTION_LENGTH
    before = _count()
    resp = logged_in.post("/expenses/add", data=_valid(description=desc))
    assert resp.status_code == 302
    assert _count() == before + 1
    rows = _query("SELECT description FROM expenses WHERE description = ?", (desc,))
    assert len(rows) == 1


def test_description_of_201_chars_rejected(logged_in):
    _assert_rejected(logged_in, _valid(description="a" * (MAX_DESCRIPTION_LENGTH + 1)))


def test_amount_rounded_to_two_decimals(logged_in):
    logged_in.post(
        "/expenses/add", data=_valid(amount="12.345", description="Rounding")
    )
    row = _query("SELECT amount FROM expenses WHERE description = ?", ("Rounding",))[0]
    assert row["amount"] == round(12.345, 2)


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_listed_category_is_accepted(logged_in, category):
    before = _count()
    resp = logged_in.post("/expenses/add", data=_valid(category=category))
    assert resp.status_code == 302
    assert _count() == before + 1


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "amount", ["0", "-5", "abc", "nan", "inf", "", "0.001"]
)
def test_bad_amount_rejected(logged_in, amount):
    _assert_rejected(logged_in, _valid(amount=amount))


def test_amount_above_maximum_rejected(logged_in):
    _assert_rejected(logged_in, _valid(amount=str(MAX_AMOUNT + 1)))


def test_amount_at_maximum_accepted(logged_in):
    before = _count()
    resp = logged_in.post("/expenses/add", data=_valid(amount=str(MAX_AMOUNT)))
    assert resp.status_code == 302
    assert _count() == before + 1


def test_bad_category_rejected(logged_in):
    _assert_rejected(logged_in, _valid(category="Hacking"))


def test_missing_category_rejected(logged_in):
    data = _valid()
    del data["category"]
    _assert_rejected(logged_in, data)


@pytest.mark.parametrize("bad_date", ["2026-1-5", "abc", ""])
def test_bad_date_rejected(logged_in, bad_date):
    _assert_rejected(logged_in, _valid(date=bad_date))


def test_missing_date_rejected(logged_in):
    data = _valid()
    del data["date"]
    _assert_rejected(logged_in, data)


def test_entered_values_retained_after_failure(logged_in):
    html = _assert_rejected(
        logged_in,
        _valid(
            amount="42.5",
            category="Hacking",
            date="2026-02-03",
            description="keepme please",
        ),
    )
    assert 'value="42.5"' in html
    assert 'value="2026-02-03"' in html
    assert "keepme please" in html


# ------------------------------------------------------------------ #
# Security                                                            #
# ------------------------------------------------------------------ #

def test_posted_user_id_is_ignored(client):
    client.post(
        "/register",
        data={"name": "Second", "email": "second@example.com", "password": "password123"},
    )
    client.post("/login", data={"email": "second@example.com", "password": "password123"})
    second_id = _user_id("second@example.com")
    assert second_id != 1
    data = _valid(description="Spoofed owner")
    data["user_id"] = "1"
    resp = client.post("/expenses/add", data=data)
    assert resp.status_code == 302
    row = _query(
        "SELECT user_id FROM expenses WHERE description = ?", ("Spoofed owner",)
    )[0]
    assert row["user_id"] == second_id, "Expense must belong to session user"


def test_session_cookie_is_samesite_lax(client):
    resp = client.post(
        "/login", data={"email": "demo@spendly.com", "password": "demo123"}
    )
    assert "samesite=lax" in resp.headers["Set-Cookie"].lower()


def test_sql_injection_description_stored_verbatim(logged_in):
    payload = "'); DROP TABLE expenses;--"
    before = _count()
    resp = logged_in.post("/expenses/add", data=_valid(description=payload))
    assert resp.status_code == 302
    assert _count() == before + 1, "Table must be intact and row inserted"
    rows = _query("SELECT description FROM expenses WHERE description = ?", (payload,))
    assert len(rows) == 1


def test_script_description_escaped_on_profile(logged_in):
    payload = "<script>alert(1)</script>"
    logged_in.post("/expenses/add", data=_valid(description=payload))
    html = logged_in.get("/profile").data.decode()
    assert payload not in html, "Raw script tag must not be rendered"
    assert "&lt;script&gt;" in html


# ------------------------------------------------------------------ #
# Other steps unchanged, template hygiene                             #
# ------------------------------------------------------------------ #

def test_edit_stub_unchanged(logged_in):
    resp = logged_in.get("/expenses/1/edit")
    assert resp.status_code == 200
    assert resp.data.decode() == "Edit expense — coming in Step 8"


def test_delete_stub_unchanged(logged_in):
    resp = logged_in.get("/expenses/1/delete")
    assert resp.status_code == 200
    assert resp.data.decode() == "Delete expense — coming in Step 9"


def test_template_has_no_hex_colours_or_inline_styles():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source), "Hex colour found"
    assert "style=" not in source
    assert "<style" not in source
