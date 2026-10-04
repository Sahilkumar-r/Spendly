# Spec: Delete Expense

## Overview
Users can add (Step 7) and edit (Step 8) expenses but cannot remove one that was entered by mistake or is no longer wanted. This step replaces the `/expenses/<id>/delete` stub with a safe two-step delete: a logged-in user clicks "Delete" on a transaction in the profile page, lands on a confirmation page that shows the expense's details, and confirms with a POST that removes the row. Deleting never happens on a GET, so links, prefetching or crawlers cannot destroy data. After deletion the user returns to the profile page, where the transactions list, totals and category breakdown no longer include the expense. This completes the add / edit / delete expense CRUD set.

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login + Logout (session `user_id`; logout already uses POST)
- Step 4: Profile page (entry point and redirect target)
- Step 5: Backend connection (profile reads live data from `expenses`)
- Step 8: Edit expense (`get_expense`, the `.row-action` link style, the actions column in the transactions table)

## Routes
- `GET /expenses/<int:id>/delete` — render a confirmation page showing the expense (date, description, category, amount) with a "Delete" button and a Cancel link; changes no data — logged-in only
- `POST /expenses/<int:id>/delete` — delete the expense, redirect to `/profile` — logged-in only

Unauthenticated requests to either method redirect to `/login`. An expense that does not exist, or that belongs to another user, returns 404 via `abort(404)` on both methods. The existing stub function `delete_expense` is changed to accept `GET` and `POST`; its endpoint name stays `delete_expense`.

## Database changes
No schema changes.

Add one helper to `database/db.py` (verified: it currently has `get_db`, `init_db`, `create_user`, `get_user_by_email`, `get_user_by_id`, `create_expense`, `get_expense`, `update_expense`, `seed_db`, and no delete helper):
- `remove_expense(expense_id, user_id)` — `DELETE FROM expenses WHERE id = ? AND user_id = ?` with a parameterised query, commits, returns `cursor.rowcount` (0 means nothing matched); opens its own connection and closes it in `finally`, matching `update_expense`

The helper is named `remove_expense` (not `delete_expense`) so it does not clash with the route function `delete_expense` in `app.py`.

## Templates
- **Create:** `templates/delete_expense.html` — extends `base.html`; heading "Delete expense", a short "This cannot be undone" message, a read-only summary of the expense (date, description, category, amount), a `POST` form to `url_for('delete_expense', id=expense_id)` with a "Delete" submit button, and a Cancel link to `url_for('profile')`
- **Modify:** `templates/profile.html` — add a "Delete" link next to the existing "Edit" link in each transaction row (`url_for('delete_expense', id=t.id)`)

## Files to change
- `app.py` — implement `delete_expense()` for GET and POST with `@login_required`, import the new db helper
- `database/db.py` — add `remove_expense()`
- `templates/profile.html` — "Delete" link per row
- `static/css/style.css` — a danger variant of the row action link and a danger submit button, reusing `--danger` / `--danger-light` and the existing `.row-action`, `.btn-submit`, `.btn-ghost`, `.expense-form-actions` patterns (CSS variables only)
- `tests/test_add_expense.py` — remove the obsolete Step 7 test `test_delete_stub_unchanged`, which asserts the stub string

## Files to create
- `templates/delete_expense.html`
- `tests/test_delete_expense.py`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw sqlite3 via `get_db()`
- Parameterised queries only — never f-strings or concatenation with user values in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only; the route loads the expense, calls the delete helper, redirects — nothing else
- Use `url_for()` for every link and the form action — never hardcode URLs
- Deleting must only happen on `POST`; `GET` must never modify data
- Take `user_id` from `session`, never from the form; ignore any `user_id` or `id` a client posts
- Ownership is enforced in SQL (`WHERE id = ? AND user_id = ?`) on both load (`get_expense`) and delete; use `abort(404)` when the expense is missing or not the user's — never a bare string and never 403
- If the delete helper returns 0 rows on POST (e.g. already deleted in another tab), `abort(404)`
- Redirect to `login` when `session.get("user_id")` is missing, on both GET and POST (use `@login_required`)
- Use the Post/Redirect/Get pattern: successful POST returns `redirect(url_for("profile"))`
- The confirmation page shows user-supplied text (description); Jinja autoescaping stays on and nothing is marked `|safe`
- Do not hard-delete or change any other user's rows; do not touch the `users` table
- No inline styles or inline `<style>` tags; vanilla JS only (none is required — the confirmation page replaces a JS `confirm()` dialog)
- Remove the obsolete Step 7 stub test for delete; leave every other existing test unchanged and passing
- Close connections in `finally`

## Definition of done
- [ ] Logged out, `GET /expenses/1/delete` and `POST /expenses/1/delete` both redirect to `/login`, and the POST deletes nothing
- [ ] The profile transactions table has a "Delete" link on every row, and it opens `/expenses/<id>/delete` for that row's expense
- [ ] Logged in, `GET /expenses/<id>/delete` for your own expense returns 200 and shows its date, description, category and amount, and does not delete it
- [ ] Submitting the confirmation form redirects to `/profile` and the row is gone from the `expenses` table
- [ ] After deletion the expense no longer appears in the transactions list, and the profile total, transaction count and category breakdown update; category percentages still sum to 100 (or the breakdown is empty if no expenses remain)
- [ ] Only the chosen expense is deleted — all other expenses, for this user and others, are unchanged
- [ ] Deleting the last remaining expense shows the "No transactions yet." empty state
- [ ] The Cancel link returns to `/profile` without deleting anything
- [ ] `GET` and `POST /expenses/<id>/delete` for another user's expense return 404 and do not delete it
- [ ] `GET` and `POST /expenses/99999/delete` for a non-existent id return 404
- [ ] Posting the delete a second time for the same id returns 404
- [ ] A posted `user_id` field is ignored — only the session user's expense can be deleted
- [ ] An expense whose description contains `<script>` renders escaped on the confirmation page
- [ ] The Edit and Add expense flows still work unchanged
- [ ] No hex colour values appear in `delete_expense.html` or in the new CSS rules
- [ ] `pytest` passes
