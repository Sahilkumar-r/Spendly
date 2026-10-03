import os
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_user,
    get_db,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

with app.app_context():
    init_db()
    seed_db()


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


# ==== SECTION 1: TRANSACTIONS (sub-agent-01) ====
def _build_transactions(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "date": datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": r["description"] or "",
            "category": r["category"],
            "amount": float(r["amount"]),
        }
        for r in rows
    ]


# ==== END SECTION 1 ====


# ==== SECTION 2: SUMMARY (sub-agent-02) ====
def _build_stats(user_id):
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "total_spent": float(totals["total"]),
        "transaction_count": int(totals["cnt"]),
        "top_category": top["category"] if top else "—",
    }


# ==== END SECTION 2 ====


# ==== SECTION 3: CATEGORIES (sub-agent-03) ====
def _build_categories(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC",
            (user_id,),
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


# ==== END SECTION 3 ====


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

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

    uid = session["user_id"]
    stats = _build_stats(uid)
    transactions = _build_transactions(uid)
    categories = _build_categories(uid)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
