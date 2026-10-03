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

    # Stats, transactions and categories are hardcoded for Step 4 —
    # replaced by real queries via get_db() in Step 5.
    stats = {
        "total_spent": 8049,
        "transaction_count": 8,
        "top_category": "Bills",
    }
    transactions = [
        {"date": "28 Sep 2026", "description": "Swiggy dinner", "category": "Food", "amount": 420},
        {"date": "26 Sep 2026", "description": "Metro card recharge", "category": "Transport", "amount": 500},
        {"date": "24 Sep 2026", "description": "Electricity bill", "category": "Bills", "amount": 1800},
        {"date": "21 Sep 2026", "description": "Groceries from DMart", "category": "Food", "amount": 1250},
        {"date": "18 Sep 2026", "description": "Myntra order", "category": "Shopping", "amount": 2150},
        {"date": "15 Sep 2026", "description": "Movie tickets at PVR", "category": "Entertainment", "amount": 600},
        {"date": "12 Sep 2026", "description": "Ola cab", "category": "Transport", "amount": 330},
        {"date": "10 Sep 2026", "description": "Broadband bill", "category": "Bills", "amount": 999},
    ]
    categories = [
        {"name": "Bills", "total": 2799, "percent": 35},
        {"name": "Shopping", "total": 2150, "percent": 27},
        {"name": "Food", "total": 1670, "percent": 21},
        {"name": "Transport", "total": 830, "percent": 10},
        {"name": "Entertainment", "total": 600, "percent": 7},
    ]

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
