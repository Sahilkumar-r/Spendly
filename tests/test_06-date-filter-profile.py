"""Tests for spec 06: date-range filter on /profile."""
import re
import sqlite3
from pathlib import Path

import pytest

import app as app_module
from database import db

EMAIL = "filter@example.com"
PASSWORD = "password123"
OTHER_EMAIL = "other@example.com"

# Known, fixed-date rows for the fresh test user: (amount, category, date, description)
ROWS = [
    (100.00, "Food", "2026-03-01", "desc-0301-food"),
    (50.00, "Transport", "2026-03-05", "desc-0305-transport"),
    (25.50, "Food", "2026-03-05", "desc-0305-food"),
    (10.00, "Food", "2026-03-10", "desc-0310-food"),
    (200.00, "Shopping", "2026-03-15", "desc-0315-shopping"),
    (300.00, "Bills", "2026-04-01", "desc-0401-bills"),
]
ALL_TIME_TOTAL = "₹685.50"


def _register_and_login(client, name, email):
    client.post("/register", data={"name": name, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})


def _user_id(email):
    conn = sqlite3.connect(db.DB_PATH)
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return row[0]
    finally:
        conn.close()


def _insert(user_id, rows):
    conn = sqlite3.connect(db.DB_PATH)
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, a, c, d, desc) for a, c, d, desc in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _count_expenses():
    conn = sqlite3.connect(db.DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


def _tbody_rows(html):
    if "<tbody>" not in html:
        return 0
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    return tbody.count("<tr>")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def user_client(client):
    """Logged in as a fresh user holding only the known ROWS."""
    _register_and_login(client, "Filter User", EMAIL)
    _insert(_user_id(EMAIL), ROWS)
    return client


def _get(client, **params):
    return client.get("/profile", query_string=params)


# ---------------------------------------------------------------- auth guard

@pytest.mark.parametrize(
    "qs",
    [
        "?start_date=2026-01-01",
        "?end_date=2026-12-31",
        "?start_date=2026-01-01&end_date=2026-12-31",
        "?start_date=abc",
    ],
)
def test_profile_with_filter_redirects_to_login_when_logged_out(client, qs):
    resp = client.get("/profile" + qs)
    assert resp.status_code == 302, "Expected redirect for unauthenticated user"
    assert resp.headers["Location"].endswith("/login")


# --------------------------------------------------------------- no filter

def test_profile_without_params_shows_all_seeded_demo_expenses(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    resp = client.get("/profile")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert _tbody_rows(html) == 8, "Demo user should see all 8 seeded expenses"
    assert "₹6,121.49" in html


def test_profile_without_params_shows_all_time_data_for_user(user_client):
    html = _get(user_client).data.decode()
    assert ALL_TIME_TOTAL in html
    assert _tbody_rows(html) == 6


@pytest.mark.parametrize("params", [{"start_date": ""}, {"end_date": ""},
                                    {"start_date": "", "end_date": ""}])
def test_blank_params_are_treated_as_not_supplied(user_client, params):
    resp = _get(user_client, **params)
    assert resp.status_code == 200
    html = resp.data.decode()
    assert ALL_TIME_TOTAL in html
    assert _tbody_rows(html) == 6


# ------------------------------------------------------------- filter form

def test_filter_form_has_inputs_apply_and_clear(user_client):
    html = _get(user_client).data.decode()
    assert 'type="date"' in html
    assert html.count('type="date"') >= 2
    assert 'name="start_date"' in html
    assert 'name="end_date"' in html
    assert "Apply" in html
    assert "Clear" in html
    assert re.search(r'<form[^>]*method="get"', html, re.IGNORECASE), "Form must use GET"
    assert re.search(r'<a[^>]*href="/profile"[^>]*>\s*Clear', html), \
        "Clear link must point to /profile"


def test_inputs_prefilled_with_applied_dates(user_client):
    html = _get(user_client, start_date="2026-03-05", end_date="2026-03-10").data.decode()
    assert 'value="2026-03-05"' in html
    assert 'value="2026-03-10"' in html


def test_inputs_empty_without_filter(user_client):
    html = _get(user_client).data.decode()
    assert 'value="2026-' not in html


# --------------------------------------------------------- filtering logic

def test_range_filters_stats_transactions_and_categories(user_client):
    resp = _get(user_client, start_date="2026-03-05", end_date="2026-03-10")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Inclusive on both bounds
    assert "desc-0305-transport" in html
    assert "desc-0305-food" in html
    assert "desc-0310-food" in html
    # Outside the range
    assert "desc-0301-food" not in html
    assert "desc-0315-shopping" not in html
    assert "desc-0401-bills" not in html
    assert _tbody_rows(html) == 3
    # Stats: total 85.50, 3 transactions, top category Food (35.50 vs 50 Transport -> Transport)
    assert "₹85.50" in html
    assert "₹685.50" not in html


def test_stats_total_and_top_category_for_filtered_range(user_client):
    # Range 2026-03-01..2026-03-10: Food 135.50, Transport 50.00 -> total 185.50, top Food
    html = _get(user_client, start_date="2026-03-01", end_date="2026-03-10").data.decode()
    assert "₹185.50" in html
    assert ">Food<" in html
    assert ">Shopping<" not in html
    assert ">Bills<" not in html
    # Stat block: transaction count of 4
    stats = re.findall(r'class="profile-stat"(.*?)</div>\s*</div>', html, re.DOTALL)
    assert len(stats) == 3 or html.count('class="profile-stat"') == 3
    assert ">4<" in html or "4" in html.split('class="profile-stat"')[2]


def test_top_category_changes_with_range(user_client):
    # Only Shopping and Bills rows: Bills (300) is the top category
    html = _get(user_client, start_date="2026-03-15", end_date="2026-04-01").data.decode()
    assert "₹500.00" in html
    stat_section = html.split('class="profile-stat"')
    assert ">Bills<" in "".join(stat_section[1:4]), "Top category should be Bills"


def test_start_date_only_filters_from_date_onward(user_client):
    html = _get(user_client, start_date="2026-03-15").data.decode()
    assert "desc-0315-shopping" in html
    assert "desc-0401-bills" in html
    assert "desc-0310-food" not in html
    assert _tbody_rows(html) == 2
    assert "₹500.00" in html


def test_end_date_only_filters_up_to_date(user_client):
    html = _get(user_client, end_date="2026-03-05").data.decode()
    assert "desc-0301-food" in html
    assert "desc-0305-transport" in html
    assert "desc-0305-food" in html
    assert "desc-0310-food" not in html
    assert "desc-0401-bills" not in html
    assert _tbody_rows(html) == 3
    assert "₹175.50" in html


def test_single_day_range_is_inclusive(user_client):
    html = _get(user_client, start_date="2026-03-05", end_date="2026-03-05").data.decode()
    assert _tbody_rows(html) == 2
    assert "₹75.50" in html


def test_category_percentages_sum_to_100_under_filter(user_client):
    html = _get(user_client, start_date="2026-03-01", end_date="2026-03-15").data.decode()
    # Each percentage also appears as <progress> fallback text, so read only
    # the visible "₹total · NN%" labels.
    pcts = [int(p) for p in re.findall(r"· (\d+)%", html)]
    assert pcts, "Expected category percentages in page"
    assert sum(pcts) == 100, f"Percentages {pcts} should sum to 100"


# ---------------------------------------------------------------- empty range

def test_range_with_no_expenses_shows_zero_stats_and_empty_states(user_client):
    resp = _get(user_client, start_date="2025-01-01", end_date="2025-01-31")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "₹0.00" in html
    assert "—" in html
    assert "No transactions in this period." in html
    assert "No spending in this period." in html
    # The empty state is a single placeholder row, not transaction rows
    assert "badge cat-" not in html
    assert _tbody_rows(html) == 1


def test_empty_state_without_filter_does_not_say_in_this_period(client):
    _register_and_login(client, "Empty User", "empty@example.com")
    html = client.get("/profile").data.decode()
    assert "in this period" not in html
    assert "₹0.00" in html


# ---------------------------------------------------------------- validation

@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "abc"},
        {"end_date": "abc"},
        {"start_date": "2026-13-45"},
        {"end_date": "2026-02-30"},
        {"start_date": "03/05/2026"},
        {"start_date": "2026-03-05", "end_date": "not-a-date"},
        {"start_date": "' OR 1=1 --"},
        {"end_date": "2026-03-05'; DROP TABLE expenses; --"},
    ],
)
def test_malformed_date_returns_200_with_error_and_all_time_data(user_client, params):
    resp = _get(user_client, **params)
    assert resp.status_code == 200, "Malformed date must never cause a 500"
    html = resp.data.decode()
    assert ALL_TIME_TOTAL in html, "Filter should be ignored (all-time data)"
    assert _tbody_rows(html) == 6
    assert re.search(r"invalid|error|valid date|format", html, re.IGNORECASE), \
        "Expected a validation error message"


def test_malformed_end_date_ignored_even_with_valid_start_date(user_client):
    resp = _get(user_client, start_date="2026-03-15", end_date="garbage")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert _tbody_rows(html) == 6, "Whole filter ignored on invalid input"
    assert ALL_TIME_TOTAL in html


def test_start_after_end_shows_error_and_falls_back_to_all_time(user_client):
    resp = _get(user_client, start_date="2026-03-10", end_date="2026-03-01")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert ALL_TIME_TOTAL in html
    assert _tbody_rows(html) == 6
    assert re.search(r"before|after|earlier|later|invalid|error|range", html, re.IGNORECASE), \
        "Expected an error message about the range order"


def test_valid_filter_shows_no_error_message(user_client):
    html = _get(user_client, start_date="2026-03-01", end_date="2026-03-31").data.decode()
    assert not re.search(r"invalid date|filter-error|class=\"[^\"]*error", html, re.IGNORECASE)


def test_sql_injection_in_dates_does_not_modify_data(user_client):
    before = _count_expenses()
    _get(user_client, start_date="2026-01-01'; DELETE FROM expenses; --")
    assert _count_expenses() == before, "Injection attempt must not alter data"


# ------------------------------------------------------------ transaction cap

def test_transactions_limited_to_10_rows_under_filter_but_stats_cover_range(client):
    _register_and_login(client, "Busy User", "busy@example.com")
    uid = _user_id("busy@example.com")
    rows = [(10.00, "Food", f"2026-05-{day:02d}", f"busy-may-{day:02d}") for day in range(1, 13)]
    rows.append((999.00, "Bills", "2026-06-01", "busy-june-outside"))
    _insert(uid, rows)

    html = _get(client, start_date="2026-05-01", end_date="2026-05-31").data.decode()
    assert _tbody_rows(html) == 10, "Only 10 transactions should be listed"
    assert "busy-june-outside" not in html
    # Most recent first: the two oldest rows are cut off
    assert "busy-may-12" in html
    assert "busy-may-01" not in html
    assert "busy-may-02" not in html
    # Stats cover all 12 filtered rows, not just the 10 shown
    assert "₹120.00" in html


# ------------------------------------------------------------ user scoping

def test_filter_only_shows_own_expenses(client):
    _register_and_login(client, "User A", "a@example.com")
    _insert(_user_id("a@example.com"), [(111.00, "Food", "2026-03-05", "a-private-expense")])
    # /register and /login redirect while a session is active, so sign out first
    client.post("/logout")
    _register_and_login(client, "User B", "b@example.com")
    _insert(_user_id("b@example.com"), [(222.00, "Bills", "2026-03-05", "b-private-expense")])

    # Currently logged in as B
    html = _get(client, start_date="2026-03-01", end_date="2026-03-31").data.decode()
    assert "b-private-expense" in html
    assert "a-private-expense" not in html
    assert "₹222.00" in html
    assert "₹111.00" not in html

    client.post("/logout")
    client.post("/login", data={"email": "a@example.com", "password": PASSWORD})
    html = _get(client, start_date="2026-03-01", end_date="2026-03-31").data.decode()
    assert "a-private-expense" in html
    assert "b-private-expense" not in html
    assert "₹111.00" in html


def test_filter_excludes_other_users_even_with_wide_range(user_client):
    _insert(_user_id("demo@spendly.com"), [(777.00, "Food", "2026-03-05", "demo-marker-row")])
    html = _get(user_client, start_date="2000-01-01", end_date="2099-12-31").data.decode()
    assert "demo-marker-row" not in html
    assert ALL_TIME_TOTAL in html
    assert _tbody_rows(html) == 6


# ------------------------------------------------------------ no side effects

def test_filtering_does_not_modify_database(user_client):
    conn = sqlite3.connect(db.DB_PATH)
    before = conn.execute(
        "SELECT id, user_id, amount, category, date, description FROM expenses ORDER BY id"
    ).fetchall()
    conn.close()

    _get(user_client, start_date="2026-03-05", end_date="2026-03-10")
    _get(user_client, start_date="bad")
    _get(user_client, start_date="2026-04-01", end_date="2026-03-01")

    conn = sqlite3.connect(db.DB_PATH)
    after = conn.execute(
        "SELECT id, user_id, amount, category, date, description FROM expenses ORDER BY id"
    ).fetchall()
    conn.close()
    assert before == after, "Filtering must be read-only"


def test_filter_is_stateless_between_requests(user_client):
    _get(user_client, start_date="2026-03-05", end_date="2026-03-05")
    html = _get(user_client).data.decode()
    assert _tbody_rows(html) == 6, "Filter must not persist across requests"
    assert ALL_TIME_TOTAL in html


# ------------------------------------------------------------------ template

def test_profile_template_has_no_hex_colours():
    template = Path(app_module.app.root_path) / "templates" / "profile.html"
    content = template.read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", content), "No hex colours in profile.html"


def test_profile_template_has_no_inline_style_tags():
    template = Path(app_module.app.root_path) / "templates" / "profile.html"
    content = template.read_text(encoding="utf-8")
    assert "<style" not in content
