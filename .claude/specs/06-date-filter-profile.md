# Spec: Date Filter for Profile Page

## Overview
The profile page currently shows the logged-in user's all-time stats, latest 10 transactions and category breakdown. This step adds a date-range filter (start date and end date) to `/profile` so the user can narrow all three sections to a chosen period. The filter is submitted as a GET form with query parameters, so filtered views are bookmarkable and need no new routes or database changes.

## Depends on
- Step 1: Database setup (`expenses.date` stored as `YYYY-MM-DD` text, so range comparison works lexically)
- Step 3: Login + Logout (session `user_id`)
- Step 4: Profile page (`templates/profile.html`)
- Step 5: Backend connection (`_build_stats`, `_build_transactions`, `_build_categories`)

## Routes
No new routes. `GET /profile` (logged-in only) is modified to accept optional query parameters:
- `start_date` — `YYYY-MM-DD`, inclusive lower bound
- `end_date` — `YYYY-MM-DD`, inclusive upper bound

Either, both or neither may be supplied. With neither, behaviour is unchanged (all-time data).

## Database changes
No database changes. `expenses.date` is already `TEXT` in ISO format, so `date >= ?` / `date <= ?` work directly.

The existing `_build_stats`, `_build_transactions` and `_build_categories` helpers (currently private functions in `app.py`, from Step 5) gain optional `start_date=None, end_date=None` parameters and append `AND date >= ?` / `AND date <= ?` clauses (with bound parameters) only when a value is given. Their location is unchanged; moving them to `database/db.py` is out of scope here. A shared small helper may build the WHERE fragment and params list to avoid repeating it three times.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter form above the stats row: two `<input type="date">` fields (`start_date`, `end_date`), an "Apply" submit button, and a "Clear" link (to `url_for('profile')`)
  - Form uses `method="get"` and `action="{{ url_for('profile') }}"`
  - Pre-fill the inputs with the currently applied values
  - Show a validation error message when the input is invalid
  - Empty-state messages stay, but read "No transactions in this period." / "No spending in this period." when a filter is active

## Files to change
- `app.py` — parse and validate `start_date` / `end_date` in `profile()`, pass them to the three helpers, pass `filters` (and `filter_error`) to the template
- `templates/profile.html` — filter form, error message, filter-aware empty states
- `static/css/style.css` — styles for the filter form, next to the existing profile styles (CSS variables only)
- `tests/test_profile.py` — tests for filtering

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()`
- Parameterised queries only — dates are bound with `?`, never interpolated into SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles or inline `<style>` tags; vanilla JS only (none is required)
- Use `url_for()` for every link, including the Clear link
- All queries stay scoped by `user_id` from the session
- Validate dates server-side with `datetime.strptime(value, "%Y-%m-%d")`. On a malformed date, or when `start_date` is after `end_date`, ignore the filter (show all-time data), keep the page at HTTP 200 and show an error message. Never raise a 500 or use `abort(500)`
- Treat blank parameters (`?start_date=`) as not supplied
- The 10-row limit on transactions stays; stats and category breakdown cover the whole filtered range
- The category percentages must still sum to 100 and handle an empty range without division by zero
- Close connections in `finally`
- Keep existing context variable names (`user`, `stats`, `transactions`, `categories`)

## Definition of done
- [ ] `/profile` with no query parameters looks and behaves exactly as before (all 8 seeded expenses for `demo@spendly.com`)
- [ ] The filter form shows start and end date inputs, an Apply button and a Clear link
- [ ] Submitting a range updates the URL to `/profile?start_date=...&end_date=...` and the stats, transactions and categories all reflect only that range
- [ ] Both bounds are inclusive: an expense dated exactly on `start_date` or `end_date` is included
- [ ] Supplying only `start_date` filters from that date onward; supplying only `end_date` filters up to that date
- [ ] The inputs are pre-filled with the applied dates after submit
- [ ] A range with no expenses returns HTTP 200 with ₹0.00 / 0 / "—" stats and the "in this period" empty-state messages
- [ ] `start_date` later than `end_date` shows an error message and falls back to unfiltered data
- [ ] A malformed date (e.g. `?start_date=abc`) returns HTTP 200 with an error message, not a 500
- [ ] Clear returns to `/profile` with no filters applied
- [ ] A user only sees their own expenses within the filter (verified with two users)
- [ ] Unauthenticated access to `/profile?start_date=2026-01-01` still redirects to `/login`
- [ ] No hex colour values appear in `profile.html` or in the new CSS rules
- [ ] `pytest` passes
