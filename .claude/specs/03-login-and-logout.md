# Spec: Login and Logout

## Overview
Make `/login` and `/logout` functional. Today `GET /login` only renders a static form and `/logout` is a placeholder string. This step lets a registered user sign in with email and password, keeps them signed in with a Flask session cookie, and lets them sign out. It follows Registration (Step 2), which now redirects to `/login`, and is required by every later logged-in feature (profile, adding/editing/deleting expenses).

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`)
- Step 2 — Registration (users can be created; `/register` redirects to `/login`)

## Routes
- `GET /login` — render the sign-in form (already exists) — public. If the visitor is already signed in, redirect to `/profile`.
- `POST /login` — check credentials; on success store the user in the session and redirect to `/profile`; on failure re-render the form with an error — public
- `POST /logout` — clear the session and redirect to `/` — logged-in (a logged-out request just redirects to `/`)

`/profile` is still the Step 4 placeholder; redirecting to it after login is intentional.

## Database changes
No database changes. The existing `users` table already has `email` (UNIQUE) and `password_hash`.

Add one helper to `database/db.py`:
- `get_user_by_email(email)` — returns the matching `sqlite3.Row` (or `None`) using a parameterised query.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — re-fill the `email` field after a failed attempt (never the password); keep the existing `{{ error }}` block
  - `templates/base.html` — navbar: when `session.user_id` is set, replace "Sign in" / "Get started" with the user's name (linking to `/profile`) and a "Sign out" button inside a `<form method="POST" action="{{ url_for('logout') }}">`; otherwise keep the current links

## Files to change
- `app.py` — secret key, login/logout routes, session handling
- `database/db.py` — add `get_user_by_email()`
- `templates/login.html`
- `templates/base.html`
- `static/css/style.css` — style the sign-out button so it looks like the other nav links (CSS variables only)

## Files to create
- `tests/test_auth.py` — pytest tests for login and logout

## New dependencies
No new dependencies. Use Flask's built-in `session`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug — verify with `check_password_hash`, never compare plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Set `app.secret_key` from the `SECRET_KEY` environment variable; fall back to a clearly-named development value only when it is unset. Never commit a real secret
- Store only `user_id` and `user_name` in the session
- Trim and lowercase the submitted email before lookup, matching how Registration stores it
- Use one generic error for both an unknown email and a wrong password ("Invalid email or password.") so accounts cannot be enumerated
- On failure return HTTP 200 with the form, pre-filled email, empty password
- On success call `session.clear()` before setting the user id (avoids session fixation)
- Logout must be `POST`, not `GET`, so a link or image cannot sign a user out
- Do not touch the other placeholder routes

## Definition of done
- [ ] Registering a new user then signing in with the same credentials redirects to `/profile`
- [ ] The seeded user (`demo@spendly.com` / `demo123`) can sign in
- [ ] A wrong password and an unknown email both show "Invalid email or password." with HTTP 200
- [ ] Email is matched case-insensitively and with surrounding spaces ignored
- [ ] After a failed attempt the email is pre-filled and the password field is empty
- [ ] While signed in, the navbar shows the user's name and a "Sign out" button instead of "Sign in" / "Get started"
- [ ] While signed in, visiting `/login` redirects to `/profile`
- [ ] Clicking "Sign out" clears the session and redirects to `/`, and the navbar shows "Sign in" again
- [ ] `GET /logout` does not sign the user out (405)
- [ ] `pytest tests/test_auth.py` passes
- [ ] The app starts with `uv run python app.py` with no errors
