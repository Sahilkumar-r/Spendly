import math
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_expense,
    create_user,
    get_db,
    get_expense,
    get_user_by_email,
    get_user_by_id,
    init_db,
    remove_expense,
    seed_db,
    update_expense,
)

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]
MAX_DESCRIPTION_LENGTH = 200
MAX_AMOUNT = 10_000_000
EXPENSE_FIELDS = ("amount", "category", "date", "description")

app = Flask(__name__)
# Without SECRET_KEY set, fall back to a random per-process key: sessions
# reset on restart, but there is no guessable key in the source.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

with app.app_context():
    init_db()
    seed_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def fail(error):
        return render_template("register.html", error=error, name=name, email=email)

    if not name or not email or not password:
        return fail("All fields are required.")

    local, _, domain = email.partition("@")
    if not local or not domain:
        return fail("Please enter a valid email address.")

    if len(password) < 8:
        return fail("Password must be at least 8 characters.")

    try:
        create_user(name, email, generate_password_hash(password))
    except sqlite3.IntegrityError:
        return fail("An account with that email already exists.")

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        )

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# --- Profile page helpers ---

def _date_clause(start_date=None, end_date=None):
    # SECURITY: only fixed SQL literals go in `sql`; user values go in `params`
    # and are always bound with `?`. Never interpolate a date into the SQL.
    sql, params = "", []
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    return sql, params


def _is_iso_date(value):
    # The round trip rejects lenient input such as "2026-1-5", which strptime
    # accepts but which would not compare correctly against stored text dates.
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        return False


def _parse_date_filters(args):
    """Return (filters, error). `filters` holds the raw form values and
    whether a valid filter is active; on error nothing is applied."""
    start = args.get("start_date", "").strip()
    end = args.get("end_date", "").strip()
    filters = {"start_date": start, "end_date": end, "active": False}

    if any(v and not _is_iso_date(v) for v in (start, end)):
        return filters, "Enter valid dates in YYYY-MM-DD format."
    if start and end and start > end:
        return filters, "Start date must be on or before end date."

    filters["active"] = bool(start or end)
    return filters, None


def _build_transactions(user_id, start_date=None, end_date=None):
    clause, extra = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?"
            + clause
            + " ORDER BY date DESC, id DESC LIMIT 10",
            (user_id, *extra),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "date": datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": r["description"] or "",
            "category": r["category"],
            "amount": float(r["amount"]),
        }
        for r in rows
    ]


def _build_stats(user_id, start_date=None, end_date=None):
    clause, extra = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?" + clause,
            (user_id, *extra),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id, *extra),
        ).fetchone()
    finally:
        conn.close()
    return {
        "total_spent": float(totals["total"]),
        "transaction_count": int(totals["cnt"]),
        "top_category": top["category"] if top else "—",
    }


def _build_categories(user_id, start_date=None, end_date=None):
    clause, extra = _date_clause(start_date, end_date)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id, *extra),
        ).fetchall()
    finally:
        conn.close()

    grand = sum(float(r[1] or 0) for r in rows)
    if not rows or grand <= 0:
        return []

    cats = []
    for r in rows:
        total = float(r[1] or 0)
        exact = total * 100 / grand
        cats.append({"name": r[0], "total": total, "percent": int(exact),
                     "_rem": exact - int(exact)})

    leftover = 100 - sum(c["percent"] for c in cats)
    for c in sorted(cats, key=lambda c: c["_rem"], reverse=True)[:max(leftover, 0)]:
        c["percent"] += 1
    for c in cats:
        del c["_rem"]
    return cats


@app.route("/profile")
@login_required
def profile():
    row = get_user_by_id(session["user_id"])
    if row is None:
        session.clear()
        return redirect(url_for("login"))

    user = {
        "name": row["name"],
        "email": row["email"],
        "member_since": datetime.strptime(
            row["created_at"], "%Y-%m-%d %H:%M:%S"
        ).strftime("%B %Y"),
    }

    user_id = session["user_id"]
    filters, filter_error = _parse_date_filters(request.args)
    start_date = filters["start_date"] if filters["active"] else None
    end_date = filters["end_date"] if filters["active"] else None

    stats = _build_stats(user_id, start_date, end_date)
    transactions = _build_transactions(user_id, start_date, end_date)
    categories = _build_categories(user_id, start_date, end_date)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        filters=filters,
        filter_error=filter_error,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


def _render_expense_form(
    values, error=None, template="add_expense.html", expense_id=None
):
    return render_template(
        template,
        categories=CATEGORIES,
        values=values,
        error=error,
        max_description_length=MAX_DESCRIPTION_LENGTH,
        expense_id=expense_id,
    )


def _read_expense_form():
    return {key: request.form.get(key, "").strip() for key in EXPENSE_FIELDS}


def _expense_to_form_values(expense):
    return {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }


def _validate_expense_form(values):
    """Return (amount, error). `error` is None when the form is valid."""
    try:
        amount = float(values["amount"])
    except ValueError:
        return None, "Enter a valid amount."
    if not math.isfinite(amount):
        return None, "Enter a valid amount."
    amount = round(amount, 2)
    if amount <= 0:
        return None, "Amount must be greater than zero."
    if amount > MAX_AMOUNT:
        return None, f"Amount must be {MAX_AMOUNT:,} or less."

    if values["category"] not in CATEGORIES:
        return None, "Please choose a category."

    if not _is_iso_date(values["date"]):
        return None, "Enter a valid date."

    if len(values["description"]) > MAX_DESCRIPTION_LENGTH:
        return None, (
            f"Description must be {MAX_DESCRIPTION_LENGTH} characters or fewer."
        )

    return amount, None


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return _render_expense_form(
            {
                "amount": "",
                "category": "",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "description": "",
            }
        )

    values = _read_expense_form()
    amount, error = _validate_expense_form(values)
    if error:
        return _render_expense_form(values, error)

    create_expense(
        session["user_id"],
        amount,
        values["category"],
        values["date"],
        values["description"] or None,
    )
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    user_id = session["user_id"]
    expense = get_expense(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return _render_expense_form(
            _expense_to_form_values(expense),
            template="edit_expense.html",
            expense_id=id,
        )

    values = _read_expense_form()
    amount, error = _validate_expense_form(values)
    if error:
        return _render_expense_form(
            values, error, template="edit_expense.html", expense_id=id
        )

    updated = update_expense(
        id,
        user_id,
        amount,
        values["category"],
        values["date"],
        values["description"] or None,
    )
    if updated == 0:
        abort(404)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
@login_required
def delete_expense(id):
    user_id = session["user_id"]
    expense = get_expense(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "POST":
        if remove_expense(id, user_id) == 0:
            abort(404)
        return redirect(url_for("profile"))

    return render_template("delete_expense.html", expense=expense, expense_id=id)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5001)
