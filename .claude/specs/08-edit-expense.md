# Spec: Edit Expense

## Overview
Users can add expenses (Step 7) and see them on the profile page, but a typo in an amount, category, date or description can only be left as is. This step replaces the `/expenses/<id>/edit` stub with a real form: a logged-in user opens an existing expense from the profile transactions list, sees it pre-filled, changes any field, and saves. The update is validated with the same rules as the add form, applied only to an expense that belongs to the logged-in user, and the user is sent back to the profile page where the stats, transactions list and category breakdown reflect the change. It is the second write path for expense data and sits between Step 7 (add) and Step 9 (delete).

## Depends on
- Step 1: Database setup (`expenses` table: `id`, `user_id`, `amount`, `category`, `date`, `description`)
- Step 3: Login + Logout (session `user_id`)
- Step 4: Profile page (transactions list holds the entry point and is the redirect target)
- Step 5: Backend connection (profile reads live data from `expenses`)
- Step 7: Add expenses (`CATEGORIES`, `MAX_AMOUNT`, `MAX_DESCRIPTION_LENGTH`, `_validate_expense_form`, `_is_iso_date`, form styles)

## Routes
- `GET /expenses/<int:id>/edit` — render the expense form pre-filled with the stored values of that expense — logged-in only
- `POST /expenses/<int:id>/edit` — validate the form, update the expense, redirect to `/profile` on success; re-render the form with an error and the entered values on failure — logged-in only

Unauthenticated requests to either method redirect to `/login`. An expense that does not exist, or that belongs to another user, returns 404 via `abort(404)` on both methods (never reveal that another user's id exists). The existing stub function `edit_expense` is changed to accept `GET` and `POST`; its endpoint name stays `edit_expense`. The Step 9 delete stub is not touched.

## Database changes
No schema changes. The `expenses` table already has every column needed.

Add two helpers to `database/db.py` (verified: it currently has `get_db`, `init_db`, `create_user`, `get_user_by_email`, `get_user_by_id`, `create_expense`, `seed_db`, and no get-one or update expense helpers):
- `get_expense(expense_id, user_id)` — returns the row where `id = ?` AND `user_id = ?`, or `None`; so ownership is enforced in SQL
- `update_expense(expense_id, user_id, amount, category, date, description)` — `UPDATE ... WHERE id = ? AND user_id = ?` with a parameterised query, commits, returns `cursor.rowcount` (0 means nothing matched); `description` may be `None`

Both open their own connection and close it in `finally`, matching `create_expense`. `created_at` is left unchanged by an update.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`; the same fields and layout as `add_expense.html` with heading "Edit expense", a "Save changes" submit button, and a Cancel link back to the profile; form action is `url_for('edit_expense', id=expense_id)`
- **Modify:** `templates/profile.html` — add an "Edit" link per transaction row (`url_for('edit_expense', id=t.id)`), which needs a new actions column in the table header and rows, and the empty-state `colspan` updated to match

Form fields (POST to `url_for('edit_expense', id=expense_id)`):
- `amount` — `<input type="number" step="0.01" min="0.01">`, required
- `category` — `<select>` of `CATEGORIES`, required, current value selected
- `date` — `<input type="date">`, required
- `description` — `<input type="text" maxlength="200">`, optional

## Files to change
- `app.py` — implement `edit_expense()` for GET and POST with `@login_required`, import `get_expense` and `update_expense`, include the expense `id` in the dicts returned by `_build_transactions` (add `id` to its SELECT), and let the shared form renderer accept the template name and expense id (or add a small sibling helper) so add and edit do not duplicate the render call
- `database/db.py` — add `get_expense()` and `update_expense()`
- `templates/profile.html` — "Edit" link per row
- `static/css/style.css` — styles for the row edit link and the new table column, reusing existing `btn-ghost` / `profile-table` / `expense-form-actions` patterns where possible (CSS variables only)

## Files to create
- `templates/edit_expense.html`
- `tests/test_edit_expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()`
- Parameterised queries only — never f-strings or concatenation with user values in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only; the route loads the expense, validates input, calls `update_expense`, redirects — nothing else
- Use `url_for()` for every link and the form action — never hardcode URLs
- Take `user_id` from `session`, never from the form; ignore any `user_id` (or `id`) field a client posts
- Ownership is enforced in SQL (`WHERE id = ? AND user_id = ?`) on both load and update; use `abort(404)` when the expense is missing or not the user's — never a bare string and never 403 (do not confirm that other users' ids exist)
- Redirect to `login` when `session.get("user_id")` is missing, on both GET and POST (use `@login_required`)
- If `update_expense` returns 0 rows on POST (e.g. deleted in another tab), `abort(404)`
- Use the Post/Redirect/Get pattern: successful POST returns `redirect(url_for("profile"))`
- Reuse `_validate_expense_form` and the existing constants — do not copy the validation rules; the rules are the same as Step 7: amount numeric, finite, > 0 and <= `MAX_AMOUNT`, rounded to 2 decimals; category in `CATEGORIES`; date valid `YYYY-MM-DD` via `_is_iso_date`; description stripped, max 200 characters, stored as `None` when blank
- On GET pre-fill the date from the stored ISO value (not the "15 Mar 2026" display format used in the profile table), and an empty stored description as an empty string
- On a validation failure return HTTP 200, re-render the form with a single clear error message and keep the user's entered values; never raise a 500 or return a bare string
- Jinja autoescaping stays on; never mark user input `|safe`
- Do not implement Step 9 (delete) — leave that stub unchanged
- No inline styles or inline `<style>` tags; vanilla JS only (none is required)
- Close connections in `finally`

## Definition of done
- [ ] Logged out, `GET /expenses/1/edit` and `POST /expenses/1/edit` both redirect to `/login`
- [ ] The profile transactions table has an "Edit" link on every row, and it opens `/expenses/<id>/edit` for that row's expense
- [ ] Logged in, `GET /expenses/<id>/edit` for your own expense returns 200 with amount, category, date and description pre-filled with the stored values (date in `YYYY-MM-DD`, the correct category selected)
- [ ] Changing any one or all fields and submitting redirects to `/profile`, and the transactions list shows the updated values
- [ ] The profile total and category breakdown update to match the edit (e.g. changing the category moves the amount between categories) and percentages still sum to 100
- [ ] The `expenses` row is updated in place — same `id`, same `user_id`, same `created_at`, no new row created
- [ ] Clearing the description is accepted and stored as NULL
- [ ] Amount `0`, a negative amount, a non-numeric amount, `nan` and `inf` each re-render the form with an error and leave the stored row unchanged
- [ ] A category not in the list (e.g. a hand-crafted POST with `category=Hacking`) is rejected with an error and leaves the row unchanged
- [ ] A malformed date (e.g. `2026-1-5`, `abc`) or a missing date is rejected with an error and leaves the row unchanged
- [ ] A description longer than 200 characters is rejected with an error and leaves the row unchanged
- [ ] After a failed submit the entered values are still in the form
- [ ] `GET` and `POST /expenses/<id>/edit` for another user's expense return 404 and do not modify it
- [ ] `GET` and `POST /expenses/99999/edit` for a non-existent id return 404
- [ ] A posted `user_id` field is ignored — the expense stays under the session user
- [ ] A SQL-injection attempt in the description (e.g. `'); DROP TABLE expenses;--`) is stored as plain text and the table is intact
- [ ] An expense edited to contain `<script>` in the description renders escaped on both the profile page and the edit form
- [ ] The Cancel link returns to `/profile` without changing anything
- [ ] The Step 9 stub route behaves exactly as before
- [ ] The Step 7 add-expense flow still works unchanged
- [ ] No hex colour values appear in `edit_expense.html` or in the new CSS rules
- [ ] `pytest` passes
