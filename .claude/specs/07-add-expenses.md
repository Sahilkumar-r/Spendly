# Spec: Add Expenses

## Overview
Spendly can display expenses on the profile page but a user has no way to create one; the only data is the seeded demo set. This step replaces the `/expenses/add` stub with a real form: a logged-in user enters an amount, category, date and optional description, the expense is saved against their account, and they are sent back to the profile page where it appears in the transactions list, stats and category breakdown. It is the first write path for expense data and unlocks Steps 8 (edit) and 9 (delete).

## Depends on
- Step 1: Database setup (`expenses` table: `user_id`, `amount`, `category`, `date`, `description`)
- Step 3: Login + Logout (session `user_id`)
- Step 4: Profile page (redirect target, shows the new expense)
- Step 5: Backend connection (profile reads live data from `expenses`)

## Routes
- `GET /expenses/add` — render the empty add-expense form (date pre-filled with today) — logged-in only
- `POST /expenses/add` — validate the form, insert the expense, redirect to `/profile` on success; re-render the form with an error and the entered values on failure — logged-in only

Unauthenticated requests to either method redirect to `/login`. The existing stub route function `add_expense` is changed to accept `GET` and `POST`; its endpoint name stays `add_expense`. The Step 8 and Step 9 stubs are not touched.

## Database changes
No schema changes. The `expenses` table already has every column needed (`amount REAL NOT NULL`, `category TEXT NOT NULL`, `date TEXT NOT NULL`, `description TEXT`, `user_id` FK to `users`).

Add one helper to `database/db.py` (verified: it currently has `get_db`, `init_db`, `create_user`, `get_user_by_email`, `get_user_by_id`, `seed_db`, and no expense helpers):
- `create_expense(user_id, amount, category, date, description)` — inserts one row with a parameterised query, commits, returns `lastrowid`; opens its own connection and closes it in `finally`, matching `create_user`

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; the form, with heading and a Cancel link back to the profile
- **Modify:** `templates/profile.html` — add an "Add expense" link/button (`url_for('add_expense')`) in a sensible place near the transactions section, and in the empty state so a new user has an obvious next action

Form fields (POST to `url_for('add_expense')`):
- `amount` — `<input type="number" step="0.01" min="0.01">`, required
- `category` — `<select>` of the fixed category list, required
- `date` — `<input type="date">`, required, defaults to today
- `description` — `<input type="text" maxlength="200">`, optional

## Files to change
- `app.py` — implement `add_expense()` for GET and POST, add a `CATEGORIES` constant, import `create_expense`
- `database/db.py` — add `create_expense()`
- `templates/profile.html` — "Add expense" entry point
- `static/css/style.css` — styles for the expense form and the add button, reusing the existing `form-group` / `form-input` / `btn-submit` / `auth-error` patterns where possible (CSS variables only)

## Files to create
- `templates/add_expense.html`
- `tests/test_add_expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()`
- Parameterised queries only — never f-strings or concatenation with user values in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only; the route validates input, calls `create_expense`, redirects — nothing else
- Use `url_for()` for every link and the form action — never hardcode URLs
- Always take `user_id` from `session`, never from the form; ignore any `user_id` field a client posts
- Redirect to `login` when `session.get("user_id")` is missing, on both GET and POST
- Use the Post/Redirect/Get pattern: successful POST returns `redirect(url_for("profile"))`
- Server-side validation (never trust the HTML attributes):
  - `amount`: must parse as a number, be finite (reject `nan` / `inf`), be greater than 0; round to 2 decimals before storing
  - `category`: must be one of `CATEGORIES` = Food, Transport, Bills, Health, Entertainment, Shopping, Other (the categories used by the seed data)
  - `date`: must be a valid `YYYY-MM-DD` — reuse the existing `_is_iso_date` helper so lenient forms like `2026-1-5` are rejected and stored text dates keep sorting and filtering correctly
  - `description`: strip whitespace, optional, max 200 characters; store `None` when blank
- On a validation failure return HTTP 200, re-render the form with a single clear error message and keep the user's entered values; never raise a 500 or return a bare string
- Jinja autoescaping stays on; never mark user input `|safe`
- Do not implement Step 8 (edit) or Step 9 (delete) — leave those stubs unchanged
- No inline styles or inline `<style>` tags; vanilla JS only (none is required)
- Close connections in `finally`

## Definition of done
- [ ] Logged out, `GET /expenses/add` and `POST /expenses/add` both redirect to `/login`
- [ ] Logged in, `GET /expenses/add` returns 200 and shows amount, category, date and description fields with today's date pre-filled
- [ ] The profile page has an "Add expense" link that opens the form
- [ ] Submitting a valid expense redirects to `/profile`, and the new expense appears at the top of the transactions list (dated today) with the correct amount, category and description
- [ ] The profile total, transaction count and category breakdown update to include the new expense, and category percentages still sum to 100
- [ ] A new row exists in `expenses` with the logged-in user's `id` as `user_id`
- [ ] A blank description is accepted and stored as NULL
- [ ] Amount `0`, a negative amount, a non-numeric amount, `nan` and `inf` each re-render the form with an error and insert nothing
- [ ] A category not in the list (e.g. a hand-crafted POST with `category=Hacking`) is rejected with an error and inserts nothing
- [ ] A malformed date (e.g. `2026-1-5`, `abc`) or a missing date is rejected with an error and inserts nothing
- [ ] A description longer than 200 characters is rejected with an error and inserts nothing
- [ ] After a failed submit the entered values are still in the form
- [ ] A posted `user_id` field is ignored — the expense is saved under the session user
- [ ] A SQL-injection attempt in the description (e.g. `'); DROP TABLE expenses;--`) is stored as plain text and the table is intact
- [ ] An expense with `<script>` in the description renders escaped on the profile page
- [ ] The Step 8 and Step 9 stub routes behave exactly as before
- [ ] No hex colour values appear in `add_expense.html` or in the new CSS rules
- [ ] `pytest` passes
