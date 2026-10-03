# Spec: Backend Connection

## Overview
Step 4 built the profile page UI using hardcoded Python dicts. This step replaces that static data with real queries against the SQLite database, so `/profile` shows the logged-in user's actual expenses, summary stats and category breakdown. All SQL lives in helper functions in `database/db.py`; `app.py` only calls them and shapes the results for the existing template. No UI redesign is intended.

## Depends on
- Step 1: Database setup (`users` and `expenses` tables, `seed_db()`)
- Step 2: Registration
- Step 3: Login + Logout (session `user_id`)
- Step 4: Profile page (`templates/profile.html` and its context shape)

## Routes
No new routes. `GET /profile` (logged-in only) is modified to use real data.

## Database changes
No database changes. The existing `users` and `expenses` tables are sufficient. Query helpers live in `app.py` (private `_build_*` functions in marked sections, using `get_db()`), not in `database/db.py`:
- `_build_stats(user_id)` — returns total spent (sum of `amount`), transaction count, and top category (highest total; `None`/"—" when the user has no expenses)
- `_build_transactions(user_id)` (limit 10) — returns the user's expenses ordered by `date DESC, id DESC`
- `_build_categories(user_id)` — returns per-category totals ordered by total descending, with integer `percent` of overall spend (percentages should sum to 100)

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Amounts are now REAL (e.g. 2499.99); replace `"{:,}".format(...)` with a format that handles decimals (e.g. `"{:,.2f}"`)
  - Add an empty state for the transactions table and category list when the user has no expenses

## Files to change
- `app.py` — add the three query helpers above; remove hardcoded `stats`, `transactions`, `categories`; build them from the helpers; format `date` as `DD Mon YYYY`
- `templates/profile.html` — amount formatting and empty states
- `tests/test_profile.py` — update/add tests for real data

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()`
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- All queries must be scoped by `user_id` from the session — a user must never see another user's expenses
- Close connections in `finally` (match existing helpers in `db.py`)
- Keep the context variable names and shapes (`user`, `stats`, `transactions`, `categories`) so the template layout stays unchanged
- Category class names in the template stay `cat-<lowercase name>`; categories outside the known set fall back to the default colour
- Handle a user with zero expenses without errors (no division by zero)

## Definition of done
- [ ] Logging in as `demo@spendly.com` / `demo123` and visiting `/profile` shows the 8 seeded expenses, not the old hardcoded rows
- [ ] Total spent equals the sum of the seeded amounts (₹6,121.49), transaction count is 8, and top category is Shopping
- [ ] Transactions are listed newest first with dates formatted like `28 Sep 2026`
- [ ] Category breakdown totals match the transaction data and percentages sum to 100
- [ ] A newly registered user with no expenses sees `/profile` return HTTP 200 with ₹0.00 / 0 / "—" stats and empty-state messages
- [ ] A user only sees their own expenses (verified with two users)
- [ ] Unauthenticated access to `/profile` still redirects to `/login`
- [ ] No hex colour values appear in `profile.html`
- [ ] `pytest` passes
