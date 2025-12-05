import os
import random
import sqlite3
from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("VERSFLIP_SECRET", "dev-secret-key")
DATABASE = os.getenv("VERSFLIP_DB", os.path.join(os.path.dirname(__file__), "versflip.db"))


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            balance INTEGER NOT NULL DEFAULT 1000,
            roblox_cookie_hash TEXT,
            roblox_username TEXT,
            roblox_profile_url TEXT
        )
        """
    )

    # Ensure roblox_cookie_hash exists for older databases.
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "roblox_cookie_hash" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN roblox_cookie_hash TEXT")
        db.commit()
    if "roblox_username" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN roblox_username TEXT")
        db.commit()
    if "roblox_profile_url" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN roblox_profile_url TEXT")
        db.commit()
    db.commit()


@app.before_request
def ensure_db():
    init_db()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    db = get_db()
    user = db.execute(
        "SELECT id, username, balance, roblox_username, roblox_profile_url FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        session.pop("user_id", None)
    return user


def get_balance() -> int:
    user = get_current_user()
    if user:
        return int(user["balance"])

    balance = session.get("balance")
    if balance is None:
        balance = 1000
        session["balance"] = balance
    return balance


def update_balance(amount: int) -> int:
    user = get_current_user()
    if user:
        new_balance = max(user["balance"] + amount, 0)
        db = get_db()
        db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user["id"]))
        db.commit()
        return new_balance

    balance = get_balance() + amount
    session["balance"] = max(balance, 0)
    return session["balance"]


def safe_int(value: str, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
@app.route("/")
def home():
    balance = get_balance()
    result = request.args.get("result")
    error = request.args.get("error")
    user = get_current_user()
    return render_template("index.html", balance=balance, result=result, error=error, user=user)


@app.post("/register")
def register():
    init_db()
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    if len(username) < 3 or len(password) < 6:
        return redirect(url_for("home", error="Username must be 3+ chars and password 6+ chars."))

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return redirect(url_for("home", error="Username already taken."))

    password_hash = generate_password_hash(password)
    cursor = db.execute(
        "INSERT INTO users (username, password_hash, balance) VALUES (?, ?, 1000)",
        (username, password_hash),
    )
    db.commit()
    session["user_id"] = cursor.lastrowid
    return redirect(url_for("home", result="Account created and logged in."))


@app.post("/login")
def login():
    init_db()
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    db = get_db()
    user = db.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return redirect(url_for("home", error="Invalid credentials."))

    session["user_id"] = user["id"]
    return redirect(url_for("home", result="Welcome back!"))


@app.post("/login/roblox")
def login_with_roblox_cookie():
    init_db()
    raw_cookie = (request.form.get("roblosecurity") or "").strip()
    roblox_username_input = (request.form.get("roblox_username") or "").strip()

    if len(raw_cookie) < 20:
        return redirect(url_for("home", error="Enter a valid .ROBLOSECURITY cookie value."))

    def build_profile_url(username: str) -> str:
        safe_username = username.strip()
        return f"https://www.roblox.com/users/profile?username={safe_username}"

    db = get_db()

    # Try matching existing linked accounts first.
    for user in db.execute(
        "SELECT id, username, roblox_cookie_hash, roblox_username, roblox_profile_url FROM users WHERE roblox_cookie_hash IS NOT NULL"
    ).fetchall():
        if user["roblox_cookie_hash"] and check_password_hash(user["roblox_cookie_hash"], raw_cookie):
            if roblox_username_input:
                db.execute(
                    "UPDATE users SET roblox_username = ?, roblox_profile_url = ? WHERE id = ?",
                    (roblox_username_input, build_profile_url(roblox_username_input), user["id"]),
                )
                db.commit()
            session["user_id"] = user["id"]
            display_name = user["roblox_username"] or user["username"]
            return redirect(url_for("home", result=f"Welcome back, {display_name}! Roblox cookie recognized."))

    if not roblox_username_input:
        return redirect(url_for("home", error="No linked account for that cookie. Provide your Roblox username to link."))

    if len(roblox_username_input) < 3:
        return redirect(url_for("home", error="Username must be at least 3 characters."))

    profile_url = build_profile_url(roblox_username_input)
    normalized_username = roblox_username_input.lower()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (normalized_username,)).fetchone()
    cookie_hash = generate_password_hash(raw_cookie)

    if existing:
        db.execute(
            "UPDATE users SET roblox_cookie_hash = ?, roblox_username = ?, roblox_profile_url = ? WHERE id = ?",
            (cookie_hash, roblox_username_input, profile_url, existing["id"]),
        )
        db.commit()
        session["user_id"] = existing["id"]
        return redirect(url_for("home", result="Roblox cookie linked and logged in."))

    temp_password_hash = generate_password_hash(os.urandom(16).hex())
    cursor = db.execute(
        "INSERT INTO users (username, password_hash, balance, roblox_cookie_hash, roblox_username, roblox_profile_url) VALUES (?, ?, 1000, ?, ?, ?)",
        (normalized_username, temp_password_hash, cookie_hash, roblox_username_input, profile_url),
    )
    db.commit()
    session["user_id"] = cursor.lastrowid
    return redirect(url_for("home", result="Account created from Roblox cookie and logged in."))


@app.get("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("balance", None)
    return redirect(url_for("home", result="Logged out."))


@app.post("/play/plinko")
def play_plinko():
    bet = safe_int(request.form.get("bet"), 0)
    risk = (request.form.get("risk") or "balanced").lower()
    balance = get_balance()

    if bet <= 0:
        return redirect(url_for("home", error="Enter a bet amount in F$."))
    if bet > balance:
        return redirect(url_for("home", error="Not enough F$ to cover that bet."))

    rows = 8
    slots = rows + 1
    position = slots // 2
    path = []

    for _ in range(rows):
        step = random.choice([-1, 1])
        position = min(max(position + step, 0), slots - 1)
        path.append("L" if step == -1 else "R")

    multipliers_by_risk = {
        "safe": [0.6, 0.75, 0.9, 1.05, 1.2, 1.05, 0.9, 0.75, 0.6],
        "balanced": [0.25, 0.55, 0.85, 1.1, 2.5, 1.1, 0.85, 0.55, 0.25],
        "risky": [0.0, 0.35, 0.7, 1.0, 4.0, 1.0, 0.7, 0.35, 0.0],
    }

    multipliers = multipliers_by_risk.get(risk, multipliers_by_risk["balanced"])
    multiplier = multipliers[position]
    payout = int(bet * multiplier)
    change = payout - bet
    update_balance(change)

    slot_number = position + 1
    path_display = " → ".join(path)

    if change > 0:
        message = f"Plinko chip landed in slot {slot_number} at {multiplier:.2f}x. Path: {path_display}. Won {change} F$."
    elif change == 0:
        message = f"Plinko chip landed in slot {slot_number} at {multiplier:.2f}x. Path: {path_display}. Broke even."
    else:
        message = f"Plinko chip landed in slot {slot_number} at {multiplier:.2f}x. Path: {path_display}. Lost {abs(change)} F$."

    return redirect(url_for("home", result=message))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
