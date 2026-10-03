# Spec: Registration

## Overview
Make the existing `/register` page functional. Today `GET /register` only renders a static form; submitting it does nothing. This step adds server-side handling so a visitor can create a Spendly account: input is validated, the password is hashed, the user is stored in the `users` table, and the visitor is sent to the login page. It is the first step of the authentication flow and unblocks login/logout (Step 3) and everything that needs a signed-in user.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`) must be complete.

## Routes
- `GET /register` — render the registration form (already exists, unchanged) — public
- `POST /register` — validate input, create the user, redirect to `/login` on success; re-render the form with an error message on failure — public

No other new routes. `/login`, `/logout` remain as they are.

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email` UNIQUE, `password_hash`, `created_at`) already covers this feature.

Add one helper to `database/db.py`:
- `create_user(name, email, password_hash)` — inserts a row with a parameterised query and returns the new user id. Raises `sqlite3.IntegrityError` on a duplicate email (caught in the route).

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — keep the form, but re-fill `name` and `email` from `request.form` values after a failed submit (never the password); keep the existing `{{ error }}` block for messages; add a `minlength="8"` attribute to the password input.

## Files to change
- `app.py` — change `/register` to accept `GET` and `POST`; add the POST handling
- `database/db.py` — add `create_user()`
- `templates/register.html` — repopulate fields on error

## Files to create
- `tests/test_registration.py` — pytest tests for the registration route (pytest and pytest-flask are already in `requirements.txt`)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — no string formatting in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log the plain password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Trim whitespace from `name` and `email`; store `email` lowercased so uniqueness is case-insensitive
- Validation, in this order, each failure re-rendering the form with a clear `error`:
  1. `name`, `email` and `password` are all non-empty
  2. `email` contains an `@` with text on both sides
  3. `password` is at least 8 characters
  4. `email` is not already registered (rely on the UNIQUE constraint and catch `sqlite3.IntegrityError`, not a check-then-insert)
- On a validation or duplicate-email failure return HTTP 200 with the form, not a redirect, and never echo the password back
- On success redirect (`302`) to `url_for('login')`; do not log the user in (sessions arrive in Step 3)
- Use `get_db()` and close the connection in a `finally` block, as `db.py` does
- Do not touch the other placeholder routes

## Definition of done
- [ ] `GET /register` still renders the form with name, email and password fields
- [ ] Submitting valid details creates a row in `users` with a hashed password (value starts with a werkzeug hash prefix such as `scrypt:` or `pbkdf2:`, not the plain text) and redirects to `/login`
- [ ] The new user's email is stored lowercased and trimmed
- [ ] Submitting with any empty field shows an error and creates no row
- [ ] Submitting a password shorter than 8 characters shows an error and creates no row
- [ ] Submitting an invalid email (e.g. `abc`) shows an error and creates no row
- [ ] Registering an email that already exists (including `DEMO@spendly.com` against the seeded `demo@spendly.com`) shows an error and creates no second row
- [ ] After a failed submit, name and email are pre-filled and the password field is empty
- [ ] `pytest tests/test_registration.py` passes
- [ ] The app starts with `python app.py` and shows no errors on `/register`
