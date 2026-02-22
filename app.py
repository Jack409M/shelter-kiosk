from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Optional

from flask import Flask, g, redirect, render_template, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

SHELTERS = ["Abba", "Haven", "Gratitude"]
MAX_LEAVE_DAYS = 7

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(APP_DIR, "shelter_operations.db")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_me")

# DATABASE_URL is present on Railway when you add Postgres
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def fmt_dt(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_iso


def get_db() -> Any:
    """
    Uses SQLite locally.
    Uses Postgres on Railway.
    We keep the interface simple with execute and fetch helpers.
    """
    if "db" in g:
        return g.db

    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        g.db = conn
        g.db_kind = "pg"
        return conn

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    g.db = conn
    g.db_kind = "sqlite"
    return conn


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def db_execute(sql: str, params: tuple = ()) -> None:
    conn = get_db()  # ensures g.db_kind is set for THIS request
    kind = g.get("db_kind", "sqlite")

    if kind == "pg":
        cur = conn.cursor()
        cur.execute(sql, params)
        cur.close()
        return

    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()

def db_fetchall(sql: str, params: tuple = ()) -> list[Any]:
    conn = get_db()
    kind = g.get("db_kind")
    if kind == "pg":
        import psycopg2.extras

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    return rows


def db_fetchone(sql: str, params: tuple = ()) -> Optional[Any]:
    rows = db_fetchall(sql, params)
    if not rows:
        return None
    return rows[0]

def init_db() -> None:
    """
    Creates tables if missing.
    Works on SQLite and Postgres.
    """
    # IMPORTANT: establish DB connection first so g.db_kind is set
    get_db()
    kind = g.get("db_kind")

    def create(sqlite_sql: str, pg_sql: str) -> None:
        db_execute(pg_sql if kind == "pg" else sqlite_sql)

    # staff users
    create(
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS staff_users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )

    # leave requests
    create(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            leave_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by INTEGER,
            decision_note TEXT,
            check_in_at TEXT,
            check_in_by INTEGER
        )
        """,
    )

    # transport requests
    create(
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            needed_at TEXT NOT NULL,
            pickup_location TEXT NOT NULL,
            destination TEXT NOT NULL,
            reason TEXT,
            resident_notes TEXT,
            callback_phone TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_by INTEGER,
            driver_name TEXT,
            staff_notes TEXT,
            completed_at TEXT,
            completed_by INTEGER,
            cancelled_at TEXT,
            cancelled_by INTEGER,
            cancel_reason TEXT
        )
        """,
    )

    # residents
    create(
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            dob TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )

    # attendance events
    create(
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT
        )
        """,
    )

        # add expected_back_time column if missing
    try:
        if kind == "pg":
            db_execute("ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS expected_back_time TEXT")
        else:
            db_execute("ALTER TABLE attendance_events ADD COLUMN expected_back_time TEXT")
    except Exception:
        # ok if it already exists
        pass
        
         # add resident_phone column to leave_requests if missing
    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        # ok if it already exists
        pass
    
    # audit log
    create(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            shelter TEXT,
            staff_user_id INTEGER,
            action_type TEXT NOT NULL,
            action_details TEXT,
            created_at TEXT NOT NULL
        )
        """,
    )

    ensure_admin_bootstrap()

def ensure_admin_bootstrap() -> None:
    """
    Creates an initial admin if none exists.
    Uses environment variables on Railway.
    Locally it will create admin if you set ADMIN_USERNAME and ADMIN_PASSWORD.
    """
    row = db_fetchone("SELECT COUNT(1) AS c FROM staff_users WHERE role = 'admin'")
    count = int(row["c"] if isinstance(row, dict) else row[0])

    if count > 0:
        return

    admin_user = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_pass = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not admin_user or not admin_pass:
        # Do nothing if not configured
        return

    db_execute(
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            admin_user,
            generate_password_hash(admin_pass),
            "admin",
            True,
            utcnow_iso(),
        ),
    )


def log_action(entity_type: str, entity_id: Optional[int], shelter: Optional[str], staff_user_id: Optional[int], action_type: str, details: str = "") -> None:
    sql = (
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    db_execute(sql, (entity_type, entity_id, shelter, staff_user_id, action_type, details, utcnow_iso()))


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "staff_user_id" not in session:
            return redirect(url_for("staff_login"))
        get_db()  # ensures g.db_kind is set for this request
        return fn(*args, **kwargs)
    return wrapper
    
def require_shelter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "shelter" not in session:
            return redirect(url_for("staff_select_shelter"))
        return fn(*args, **kwargs)
    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)
    return wrapper

def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ["admin", "staff"]:
            flash("Staff or admin only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def public_home():
    return redirect(url_for("resident_leave"))
@app.route("/debug/db")
def debug_db():
    live_env = (os.environ.get("DATABASE_URL") or "").strip()

    try:
        init_db()
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "db_kind": g.get("db_kind"),
            "module_DATABASE_URL_set": bool(DATABASE_URL),
            "live_env_DATABASE_URL_set": bool(live_env),
            "railway_deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
        }, 500

    return {
        "ok": True,
        "db_kind": g.get("db_kind"),
        "module_DATABASE_URL_set": bool(DATABASE_URL),
        "live_env_DATABASE_URL_set": bool(live_env),
        "railway_deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID"),
    }


@app.route("/leave", methods=["GET", "POST"])
def resident_leave():
    init_db()

    if request.method == "GET":
        shelter = (request.args.get("shelter") or "").strip()
        shelter_value = shelter if shelter in SHELTERS else ""
        return render_template(
            "resident_leave.html",
            shelters=SHELTERS,
            shelter=shelter_value,
            max_days=MAX_LEAVE_DAYS,
        )

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("resident_leave"))

    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()
    dob = (request.form.get("dob") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    leave_at_raw = (request.form.get("leave_at") or "").strip()
    return_at_raw = (request.form.get("return_at") or "").strip()
    agreed = request.form.get("agreed") == "on"

    errors: list[str] = []
    if not agreed:
        errors.append("You must accept the agreement.")
    if not first or not last or not dob or not destination or not leave_at_raw or not return_at_raw:
        errors.append("Complete all required fields.")

    try:
        leave_dt = parse_dt(leave_at_raw)
        return_dt = parse_dt(return_at_raw)
        if return_dt <= leave_dt:
            errors.append("Return must be after leave.")
        if return_dt > leave_dt + timedelta(days=MAX_LEAVE_DAYS):
            errors.append(f"Maximum leave is {MAX_LEAVE_DAYS} days.")
    except Exception:
        errors.append("Invalid date or time.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("resident_leave.html", shelters=SHELTERS, shelter=shelter, max_days=MAX_LEAVE_DAYS), 400

    sql = (
        """
        INSERT INTO leave_requests
        (shelter, first_name, last_name, dob, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO leave_requests
        (shelter, first_name, last_name, dob, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    leave_iso = leave_dt.replace(microsecond=0).isoformat()
    return_iso = return_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, (shelter, first, last, dob, destination, reason or None, resident_notes or None, leave_iso, return_iso, submitted))
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, (shelter, first, last, dob, destination, reason or None, resident_notes or None, leave_iso, return_iso, submitted))
        conn.commit()
        req_id = cur.lastrowid

    log_action("leave", req_id, shelter, None, "create", "Resident submitted leave request")
    return render_template("resident_submitted.html", request_id=req_id, kind="Leave request submitted")


@app.route("/transport", methods=["GET", "POST"])
def resident_transport():
    init_db()

    if request.method == "GET":
        shelter = (request.args.get("shelter") or "").strip()
        shelter_value = shelter if shelter in SHELTERS else ""
        return render_template("resident_transport.html", shelters=SHELTERS, shelter=shelter_value)

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("resident_transport"))

    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()
    dob = (request.form.get("dob") or "").strip()
    needed_raw = (request.form.get("needed_at") or "").strip()
    pickup = (request.form.get("pickup_location") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    callback_phone = (request.form.get("callback_phone") or "").strip()

    errors: list[str] = []
    if not first or not last or not dob or not needed_raw or not pickup or not destination:
        errors.append("Complete all required fields.")

    try:
        needed_dt = parse_dt(needed_raw)
        if needed_dt < datetime.utcnow() - timedelta(minutes=1):
            errors.append("Needed time cannot be in the past.")
    except Exception:
        errors.append("Invalid needed date or time.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("resident_transport.html", shelters=SHELTERS, shelter=shelter), 400

    sql = (
        """
        INSERT INTO transport_requests
        (shelter, first_name, last_name, dob, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO transport_requests
        (shelter, first_name, last_name, dob, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    needed_iso = needed_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            sql,
            (shelter, first, last, dob, needed_iso, pickup, destination, reason or None, resident_notes or None, callback_phone or None, submitted),
        )
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            sql,
            (shelter, first, last, dob, needed_iso, pickup, destination, reason or None, resident_notes or None, callback_phone or None, submitted),
        )
        conn.commit()
        req_id = cur.lastrowid

    log_action("transport", req_id, shelter, None, "create", "Resident submitted transportation request")
    return render_template("resident_submitted.html", request_id=req_id, kind="Transportation request submitted")


@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    init_db()

    if request.method == "GET":
        return render_template("staff_login.html")

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()

    row = db_fetchone(
        "SELECT * FROM staff_users WHERE username = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM staff_users WHERE username = ?",
        (username,),
    )

    if not row:
        flash("Invalid login.", "error")
        return render_template("staff_login.html"), 401

    is_active = bool(row["is_active"] if isinstance(row, dict) else row[4])
    pw_hash = row["password_hash"] if isinstance(row, dict) else row[2]

    if not is_active or not check_password_hash(pw_hash, password):
        flash("Invalid login.", "error")
        return render_template("staff_login.html"), 401

    session["staff_user_id"] = row["id"] if isinstance(row, dict) else row[0]
    session["username"] = row["username"] if isinstance(row, dict) else row[1]
    session["role"] = row["role"] if isinstance(row, dict) else row[3]
    session.pop("shelter", None)

    log_action("staff", session["staff_user_id"], None, session["staff_user_id"], "login", f"Login {session['username']}")
    return redirect(url_for("staff_select_shelter"))


@app.route("/staff/logout")
@require_login
def staff_logout():
    staff_id = session.get("staff_user_id")
    username = session.get("username", "")
    session.clear()
    if staff_id:
        log_action("staff", staff_id, None, staff_id, "logout", f"Logout {username}")
    return redirect(url_for("staff_login"))


@app.route("/staff/select-shelter", methods=["GET", "POST"])
@require_login
def staff_select_shelter():
    if request.method == "GET":
        return render_template("staff_select_shelter.html", shelters=SHELTERS)

    shelter = (request.form.get("shelter") or "").strip()
    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("staff_select_shelter"))

    session["shelter"] = shelter
    return redirect(url_for("staff_home"))


@app.route("/staff")
@require_login
@require_shelter
def staff_home():
    return redirect(url_for("staff_leave_pending"))


@app.route("/staff/leave/pending")
@require_login
@require_shelter
def staff_leave_pending():
    shelter = session["shelter"]
    rows = db_fetchall(
        "SELECT * FROM leave_requests WHERE status = %s AND shelter = %s ORDER BY submitted_at DESC"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM leave_requests WHERE status = ? AND shelter = ? ORDER BY submitted_at DESC",
        ("pending", shelter),
    )
    return render_template("staff_leave_pending.html", rows=rows, fmt_dt=fmt_dt, shelter=shelter)


@app.route("/staff/leave/away-now")
@require_login
@require_shelter
def staff_leave_away_now():
    shelter = session["shelter"]
    now = utcnow_iso()
    rows = db_fetchall(
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND leave_at <= %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND leave_at <= ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """,
        ("approved", shelter, now),
    )
    return render_template("staff_leave_away_now.html", rows=rows, fmt_dt=fmt_dt, shelter=shelter)


@app.route("/staff/leave/overdue")
@require_login
@require_shelter
def staff_leave_overdue():
    shelter = session["shelter"]
    now = utcnow_iso()
    rows = db_fetchall(
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND return_at < %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND return_at < ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """,
        ("approved", shelter, now),
    )
    return render_template("staff_leave_overdue.html", rows=rows, fmt_dt=fmt_dt, shelter=shelter)


@app.route("/staff/leave/<int:req_id>/approve", methods=["POST"])
@require_login
@require_shelter
def staff_leave_approve(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    row = db_fetchone(
        "SELECT * FROM leave_requests WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM leave_requests WHERE id = ? AND shelter = ?",
        (req_id, shelter),
    )
    if not row or (row["status"] if isinstance(row, dict) else row[10]) != "pending":
        flash("Not pending.", "error")
        return redirect(url_for("staff_leave_pending"))

    decided_at = utcnow_iso()
    db_execute(
        """
        UPDATE leave_requests
        SET status = %s, decided_at = %s, decided_by = %s, decision_note = %s
        WHERE id = %s AND shelter = %s
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE leave_requests
        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
        WHERE id = ? AND shelter = ?
        """,
        ("approved", decided_at, staff_id, note or None, req_id, shelter),
    )

    log_action("leave", req_id, shelter, staff_id, "approve", note or "")
    flash("Approved.", "ok")
    return redirect(url_for("staff_leave_pending"))


@app.route("/staff/leave/<int:req_id>/deny", methods=["POST"])
@require_login
@require_shelter
def staff_leave_deny(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()
    if not note:
        flash("Denial note required.", "error")
        return redirect(url_for("staff_leave_pending"))

    db_execute(
        """
        UPDATE leave_requests
        SET status = %s, decided_at = %s, decided_by = %s, decision_note = %s
        WHERE id = %s AND shelter = %s AND status = %s
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE leave_requests
        SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?
        WHERE id = ? AND shelter = ? AND status = ?
        """,
        ("denied", utcnow_iso(), staff_id, note, req_id, shelter, "pending"),
    )

    log_action("leave", req_id, shelter, staff_id, "deny", note)
    flash("Denied.", "ok")
    return redirect(url_for("staff_leave_pending"))


@app.route("/staff/leave/<int:req_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_leave_check_in(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    db_execute(
        """
        UPDATE leave_requests
        SET status = %s, check_in_at = %s, check_in_by = %s
        WHERE id = %s AND shelter = %s AND status = %s AND check_in_at IS NULL
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE leave_requests
        SET status = ?, check_in_at = ?, check_in_by = ?
        WHERE id = ? AND shelter = ? AND status = ? AND check_in_at IS NULL
        """,
        ("checked_in", utcnow_iso(), staff_id, req_id, shelter, "approved"),
    )

    log_action("leave", req_id, shelter, staff_id, "check_in", note or "")
    flash("Checked in.", "ok")
    return redirect(url_for("staff_leave_away_now"))


@app.route("/staff/transport/pending")
@require_login
@require_shelter
def staff_transport_pending():
    shelter = session["shelter"]
    rows = db_fetchall(
        "SELECT * FROM transport_requests WHERE status = %s AND shelter = %s ORDER BY submitted_at DESC"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM transport_requests WHERE status = ? AND shelter = ? ORDER BY submitted_at DESC",
        ("pending", shelter),
    )
    return render_template("staff_transport_pending.html", rows=rows, fmt_dt=fmt_dt, shelter=shelter)


@app.route("/staff/transport/<int:req_id>/schedule", methods=["POST"])
@require_login
@require_shelter
def staff_transport_schedule(req_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    driver_name = (request.form.get("driver_name") or "").strip()
    staff_notes = (request.form.get("staff_notes") or "").strip()

    if not driver_name:
        flash("Driver name required.", "error")
        return redirect(url_for("staff_transport_pending"))

    db_execute(
        """
        UPDATE transport_requests
        SET status = %s, scheduled_at = %s, scheduled_by = %s, driver_name = %s, staff_notes = %s
        WHERE id = %s AND shelter = %s AND status = %s
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE transport_requests
        SET status = ?, scheduled_at = ?, scheduled_by = ?, driver_name = ?, staff_notes = ?
        WHERE id = ? AND shelter = ? AND status = ?
        """,
        ("scheduled", utcnow_iso(), staff_id, driver_name, staff_notes or None, req_id, shelter, "pending"),
    )

    log_action("transport", req_id, shelter, staff_id, "schedule", f"Driver {driver_name}")
    flash("Scheduled.", "ok")
    return redirect(url_for("staff_transport_pending"))


@app.route("/staff/attendance")
@require_login
@require_shelter
def staff_attendance():
    """
    Shows all active residents for the selected shelter.
    Shows current in or out based on last attendance event.
    """
    shelter = session["shelter"]

    residents = db_fetchall(
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
        (shelter,),
    )

    status_map: dict[int, dict[str, Any]] = {}

    for r in residents:
        rid = int(r["id"] if isinstance(r, dict) else r[0])

        last_event = db_fetchone(
            """
            SELECT event_type, event_time, expected_back_time
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s
            ORDER BY event_time DESC
            LIMIT 1
            """
            if g.get("db_kind") == "pg"
            else
            """
            SELECT event_type, event_time, expected_back_time
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ?
            ORDER BY event_time DESC
            LIMIT 1
            """,
            (rid, shelter),
        )

        if last_event:
            et = last_event["event_type"] if isinstance(last_event, dict) else last_event[0]
            tm = last_event["event_time"] if isinstance(last_event, dict) else last_event[1]
            eb = last_event["expected_back_time"] if isinstance(last_event, dict) else last_event[2]
        else:
            et = "check_in"
            tm = ""
            eb = ""

        is_overdue = False
        if et == "check_out" and eb:
            try:
                is_overdue = parse_dt(eb) < datetime.utcnow()
            except Exception:
                is_overdue = False

        status_map[rid] = {
            "status": et,
            "time": tm,
            "expected_back_time": eb or "",
            "is_overdue": is_overdue,
        }

    return render_template(
        "staff_attendance.html",
        residents=residents,
        status_map=status_map,
        fmt_dt=fmt_dt,
        shelter=shelter,
    )
@app.route("/staff/attendance/<int:resident_id>/check-in", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_in(resident_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    note = (request.form.get("note") or "").strip()

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note) VALUES (%s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note) VALUES (?, ?, ?, ?, ?, ?)"
    )
    db_execute(sql, (resident_id, shelter, "check_in", utcnow_iso(), staff_id, note or None))
    log_action("attendance", resident_id, shelter, staff_id, "check_in", note or "")
    return redirect(url_for("staff_attendance"))


@app.route("/staff/attendance/<int:resident_id>/check-out", methods=["POST"])
@require_login
@require_shelter
def staff_attendance_check_out(resident_id: int):
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    note = (request.form.get("note") or "").strip()
    expected_back = (request.form.get("expected_back_time") or "").strip()
    expected_back_value = expected_back or None

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(
        sql,
        (resident_id, shelter, "check_out", utcnow_iso(), staff_id, note or None, expected_back_value),
    )
    log_action("attendance", resident_id, shelter, staff_id, "check_out", f"expected_back={expected_back_value or ''} {note or ''}".strip())
    return redirect(url_for("staff_attendance"))

@app.route("/staff/admin/users", methods=["GET", "POST"])
@require_login
@require_admin
def admin_users():
    init_db()

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or "staff").strip()

        if not username or not password:
            flash("Username and password required.", "error")
            return redirect(url_for("admin_users"))

        if role not in ["staff", "admin"]:
            flash("Invalid role.", "error")
            return redirect(url_for("admin_users"))

        try:
            db_execute(
                "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
                if g.get("db_kind") == "pg"
                else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash(password), role, True, utcnow_iso()),
            )
            flash("User created.", "ok")
        except Exception:
            flash("Username already exists.", "error")

        return redirect(url_for("admin_users"))

    users = db_fetchall("SELECT id, username, role, is_active, created_at FROM staff_users ORDER BY created_at DESC")
    return render_template("admin_users.html", users=users, fmt_dt=fmt_dt)
@app.route("/admin/delete-user/<username>", methods=["POST"])
@require_login
@require_admin
def delete_user(username):
    if username == session.get("username"):
        flash("You cannot delete yourself.", "error")
        return redirect(url_for("admin_users"))

    db_execute(
        "DELETE FROM staff_users WHERE username = %s"
        if g.get("db_kind") == "pg"
        else "DELETE FROM staff_users WHERE username = ?",
        (username,),
    )

    flash(f"User '{username}' deleted.", "ok")
    return redirect(url_for("admin_users"))
@app.route("/staff/residents", methods=["GET", "POST"])
@require_login
@require_shelter
@require_staff_or_admin
def staff_residents():
    init_db()
    shelter = session["shelter"]

    if request.method == "POST":
        first = (request.form.get("first_name") or "").strip()
        last = (request.form.get("last_name") or "").strip()
        dob = (request.form.get("dob") or "").strip()

        if not first or not last or not dob:
            flash("First name, last name, and date of birth are required.", "error")
            return redirect(url_for("staff_residents"))

        sql = (
            "INSERT INTO residents (shelter, first_name, last_name, dob, is_active, created_at) VALUES (%s, %s, %s, %s, TRUE, %s)"
            if g.get("db_kind") == "pg"
            else
            "INSERT INTO residents (shelter, first_name, last_name, dob, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)"
        )
        db_execute(sql, (shelter, first, last, dob, utcnow_iso()))
        log_action("resident", None, shelter, session["staff_user_id"], "create", f"{first} {last} {dob}")
        flash("Resident added.", "ok")
        return redirect(url_for("staff_residents"))

    show = (request.args.get("show") or "active").strip()
    only_active = show != "all"

    if g.get("db_kind") == "pg":
        if only_active:
            residents = db_fetchall(
                "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name",
                (shelter,),
            )
        else:
            residents = db_fetchall(
                "SELECT * FROM residents WHERE shelter = %s ORDER BY is_active DESC, last_name, first_name",
                (shelter,),
            )
    else:
        if only_active:
            residents = db_fetchall(
                "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
                (shelter,),
            )
        else:
            residents = db_fetchall(
                "SELECT * FROM residents WHERE shelter = ? ORDER BY is_active DESC, last_name, first_name",
                (shelter,),
            )

    return render_template("staff_residents.html", residents=residents, shelter=shelter, show=show)


@app.route("/staff/residents/<int:resident_id>/set-active", methods=["POST"])
@require_login
@require_shelter
@require_staff_or_admin
def staff_resident_set_active(resident_id: int):
    init_db()
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    active = (request.form.get("active") or "").strip()

    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return redirect(url_for("staff_residents"))

    if g.get("db_kind") == "pg":
        db_execute(
            "UPDATE residents SET is_active = %s WHERE id = %s AND shelter = %s",
            (active == "1", resident_id, shelter),
        )
    else:
        db_execute(
            "UPDATE residents SET is_active = ? WHERE id = ? AND shelter = ?",
            (1 if active == "1" else 0, resident_id, shelter),
        )

    log_action("resident", resident_id, shelter, staff_id, "set_active", f"active={active}")
    flash("Updated.", "ok")
    return redirect(url_for("staff_residents"))
     
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000)






















