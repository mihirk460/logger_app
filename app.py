import calendar
import os
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "logger.db")
KEY_PATH = os.path.join(DATA_DIR, "secret_key")

COLORS = ["#e53935", "#fb8c00", "#fdd835", "#43a047", "#00acc1",
          "#1e88e5", "#8e24aa", "#d81b60", "#6d4c41", "#546e7a"]
ICONS = ["⭐", "💪", "🏃", "🧘", "📚", "💧", "🍎", "💊", "😴", "🧹", "💰", "🎨",
         "🎵", "🌱", "❤️", "☕", "🚭", "🍺", "🧠", "✈️", "🐶", "📝", "🎮", "🛒"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  pin_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL,
  icon TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_logs_item_date ON logs(item_id, date);
"""

# --- app setup -------------------------------------------------------------

os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(KEY_PATH):
    with open(KEY_PATH, "w") as f:
        f.write(secrets.token_hex(32))
with sqlite3.connect(DB_PATH) as conn:
    conn.executescript(SCHEMA)

app = Flask(__name__)
with open(KEY_PATH) as f:
    app.secret_key = f.read().strip()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)


# --- db helpers ------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def parse_date(s, default=None):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return default or date.today()


def get_item(item_id):
    row = query("SELECT * FROM items WHERE id=? AND user_id=?",
                (item_id, g.user["id"]), one=True)
    if row is None:
        abort(404)
    return row


def get_log(log_id):
    row = query("""SELECT logs.*, items.name, items.icon, items.color
                   FROM logs JOIN items ON items.id = logs.item_id
                   WHERE logs.id=? AND items.user_id=?""",
                (log_id, g.user["id"]), one=True)
    if row is None:
        abort(404)
    return row


def user_items():
    return query("""SELECT items.*, COUNT(logs.id) AS count
                    FROM items LEFT JOIN logs ON logs.item_id = items.id
                    WHERE items.user_id=? GROUP BY items.id ORDER BY items.name""",
                 (g.user["id"],))


# --- auth ------------------------------------------------------------------

@app.before_request
def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


def valid_pin(pin):
    return pin is not None and len(pin) == 4 and pin.isdigit()


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pin = request.form.get("pin", "")
        user = query("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and check_password_hash(user["pin_hash"], pin):
            session.permanent = True
            session["user_id"] = user["id"]
            return redirect(url_for("home"))
        flash("Wrong username or PIN.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pin = request.form.get("pin", "")
        pin2 = request.form.get("pin2", "")
        if not username or len(username) > 30:
            flash("Username must be 1-30 characters.")
        elif not valid_pin(pin):
            flash("PIN must be exactly 4 digits.")
        elif pin != pin2:
            flash("PINs do not match.")
        elif query("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash("That username is taken.")
        else:
            uid = execute("INSERT INTO users (username, pin_hash) VALUES (?, ?)",
                          (username, generate_password_hash(pin)))
            session.clear()
            session.permanent = True
            session["user_id"] = uid
            return redirect(url_for("home"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- home / logging --------------------------------------------------------

@app.route("/")
@login_required
def home():
    d = request.args.get("date")
    return render_template("home.html", items=user_items(),
                           date=parse_date(d).isoformat(), fixed=bool(d))


@app.route("/log", methods=["POST"])
@login_required
def log():
    item = get_item(request.form.get("item_id", type=int))
    d = parse_date(request.form.get("date"))
    log_id = execute("INSERT INTO logs (item_id, date) VALUES (?, ?)",
                     (item["id"], d.isoformat()))
    flash(Markup('Logged {} {} for {}. <a href="{}">Change / undo</a>').format(
        item["icon"], escape(item["name"]), d.strftime("%a %b %-d"),
        url_for("edit_log", log_id=log_id)))
    return redirect(url_for("home", date=request.form.get("date")))


@app.route("/logs/<int:log_id>/edit", methods=["GET", "POST"])
@login_required
def edit_log(log_id):
    lg = get_log(log_id)
    if request.method == "POST":
        d = parse_date(request.form.get("date"), parse_date(lg["date"]))
        execute("UPDATE logs SET date=?, note=? WHERE id=?",
                (d.isoformat(), request.form.get("note", "").strip(), log_id))
        return redirect(url_for("day", d=d.isoformat()))
    return render_template("edit_log.html", log=lg)


@app.route("/logs/<int:log_id>/delete", methods=["POST"])
@login_required
def delete_log(log_id):
    lg = get_log(log_id)
    execute("DELETE FROM logs WHERE id=?", (log_id,))
    return redirect(url_for("day", d=lg["date"]))


# --- items -----------------------------------------------------------------

def item_form(item=None):
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        note = request.form.get("note", "").strip()
        color = request.form.get("color", "")
        icon = request.form.get("icon", "")
        if not name or len(name) > 40:
            flash("Name must be 1-40 characters.")
        elif color not in COLORS or icon not in ICONS:
            flash("Pick a color and an icon.")
        else:
            if item is None:
                execute("INSERT INTO items (user_id, name, note, color, icon) VALUES (?,?,?,?,?)",
                        (g.user["id"], name, note, color, icon))
            else:
                execute("UPDATE items SET name=?, note=?, color=?, icon=? WHERE id=?",
                        (name, note, color, icon, item["id"]))
            return redirect(url_for("home"))
    return render_template("item_form.html", item=item, colors=COLORS, icons=ICONS)


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def new_item():
    return item_form()


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    return item_form(get_item(item_id))


@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    get_item(item_id)
    execute("DELETE FROM items WHERE id=?", (item_id,))
    return redirect(url_for("home"))


# --- calendar --------------------------------------------------------------

@app.route("/calendar")
@login_required
def calendar_view():
    today = date.today()
    y = request.args.get("y", today.year, type=int)
    m = request.args.get("m", today.month, type=int)
    if not 1 <= m <= 12:
        y, m = today.year, today.month
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(y, m)
    start, end = weeks[0][0].isoformat(), weeks[-1][-1].isoformat()
    rows = query("""SELECT logs.date, items.icon, items.color
                    FROM logs JOIN items ON items.id = logs.item_id
                    WHERE items.user_id=? AND logs.date BETWEEN ? AND ?
                    ORDER BY logs.date, logs.id""", (g.user["id"], start, end))
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    prev_m = date(y, m, 1) - timedelta(days=1)
    next_m = date(y, m, calendar.monthrange(y, m)[1]) + timedelta(days=1)
    return render_template("calendar.html", weeks=weeks, by_day=by_day,
                           month=date(y, m, 1), today=today,
                           prev=(prev_m.year, prev_m.month),
                           next=(next_m.year, next_m.month))


@app.route("/day/<d>")
@login_required
def day(d):
    d = parse_date(d)
    logs = query("""SELECT logs.*, items.name, items.icon, items.color
                    FROM logs JOIN items ON items.id = logs.item_id
                    WHERE items.user_id=? AND logs.date=? ORDER BY logs.id""",
                 (g.user["id"], d.isoformat()))
    return render_template("day.html", d=d, logs=logs)


# --- chart -----------------------------------------------------------------

@app.route("/chart")
@login_required
def chart():
    items = user_items()
    today = date.today()
    item_id = request.args.get("item", "all")
    rng = request.args.get("range", "30")

    first = query("""SELECT MIN(logs.date) AS d FROM logs JOIN items ON items.id = logs.item_id
                     WHERE items.user_id=?""", (g.user["id"],), one=True)["d"]
    first = parse_date(first, today)
    months = []
    y, m = today.year, today.month
    while (y, m) >= (first.year, first.month):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)

    if rng in months:
        y, m = int(rng[:4]), int(rng[5:])
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])
        label_fmt = "%-d"
    else:
        rng = "30"
        start, end = today - timedelta(days=29), today
        label_fmt = "%b %-d"

    sql = """SELECT logs.date AS d, COUNT(*) AS n FROM logs JOIN items ON items.id = logs.item_id
             WHERE items.user_id=? AND logs.date BETWEEN ? AND ?"""
    args = [g.user["id"], start.isoformat(), end.isoformat()]
    if item_id != "all":
        sql += " AND items.id=?"
        args.append(item_id)
    counts = {r["d"]: r["n"] for r in query(sql + " GROUP BY logs.date", args)}

    labels, data = [], []
    d = start
    while d <= end:
        labels.append(d.strftime(label_fmt))
        data.append(counts.get(d.isoformat(), 0))
        d += timedelta(days=1)

    selected = next((i for i in items if str(i["id"]) == item_id), None)
    return render_template("chart.html", items=items, months=months, rng=rng,
                           item_id=item_id, labels=labels, data=data,
                           total=sum(data),
                           color=selected["color"] if selected else "#1e88e5")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
