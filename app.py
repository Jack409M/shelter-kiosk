from __future__ import annotations

import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional

from flask import Flask, g, redirect, render_template, request, session, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from zoneinfo import ZoneInfo

try:
    from twilio.rest import Client
except Exception:
    Client = None


SHELTERS = ["Abba", "Haven", "Gratitude"]
MAX_LEAVE_DAYS = 7

# User roles
USER_ROLES = {"admin", "staff", "case_manager", "ra"}

ROLE_LABELS = {
    "admin": "Admin",
    "staff": "Staff",
    "ra": "RA DESK",
    "case_manager": "Case Mgr",
}

# Any role allowed to use normal staff pages
STAFF_ROLES = {"admin", "staff", "case_manager", "ra"}

# Only these roles can perform permanent transfers
TRANSFER_ROLES = {"admin", "case_manager"}

APP_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_PATH = os.path.join(APP_DIR, "shelter_operations.db")

app = Flask(__name__)
secret = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
if not secret:
    raise RuntimeError("FLASK_SECRET_KEY is required and must be set in the environment.")
app.secret_key = secret
app.permanent_session_lifetime = timedelta(hours=8)
@app.context_processor
def inject_shelters():
    return {
        "all_shelters": SHELTERS,
        "current_shelter": session.get("shelter")
    }

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
ENABLE_DEBUG_ROUTES = (os.environ.get("ENABLE_DEBUG_ROUTES") or "").strip().lower() in {"1", "true", "yes", "on"}

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()

def resident_session_start(resident_row: Any, shelter: str, resident_code: str) -> None:
    session.permanent = True
    session["resident_id"] = resident_row["id"] if isinstance(resident_row, dict) else resident_row[0]
    session["resident_identifier"] = resident_row["resident_identifier"] if isinstance(resident_row, dict) else resident_row[1]
    session["resident_first"] = resident_row["first_name"] if isinstance(resident_row, dict) else resident_row[2]
    session["resident_last"] = resident_row["last_name"] if isinstance(resident_row, dict) else resident_row[3]
    session["resident_phone"] = (resident_row["phone"] if isinstance(resident_row, dict) else resident_row[4]) or ""
    session["resident_shelter"] = shelter
    session["resident_code"] = resident_code

def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def fmt_dt(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return dt_iso
def fmt_date(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%m/%d/%Y")
    except Exception:
        return dt_iso

def fmt_pretty_date(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%B %d, %Y")
    except Exception:
        return dt_iso

def fmt_time_only(dt_iso: Optional[str]) -> str:
    if not dt_iso:
        return ""
    try:
        dt = datetime.fromisoformat(dt_iso)
        dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
        return local_dt.strftime("%I:%M %p")
    except Exception:
        return ""


def send_sms(to_number: str, message: str) -> None:
    if not Client:
        return
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return

    raw = (to_number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if raw.startswith("+"):
        to_e164 = raw
    elif len(digits) == 10:
        to_e164 = "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        to_e164 = "+" + digits
    else:
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_e164)
    except Exception as e:
        print("SMS error:", e)


def get_db() -> Any:
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
    conn = get_db()
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


def log_action(
    entity_type: str,
    entity_id: Optional[int],
    shelter: Optional[str],
    staff_user_id: Optional[int],
    action_type: str,
    details: str = "",
) -> None:
    sql = (
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO audit_log (entity_type, entity_id, shelter, staff_user_id, action_type, action_details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    db_execute(sql, (entity_type, entity_id, shelter, staff_user_id, action_type, details, utcnow_iso()))

def record_resident_transfer(resident_id: int, from_shelter: str, to_shelter: str, note: str = ""):
    actor = session.get("username") or "unknown"

    if g.get("db_kind") == "pg":
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, note)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (resident_id, from_shelter, to_shelter, actor, note or None),
        )
    else:
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, transferred_at, note)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
            """,
            (resident_id, from_shelter, to_shelter, actor, note or None),
        )

    staff_id = session.get("staff_user_id")
    log_action(
        "resident",
        resident_id,
        from_shelter,
        staff_id,
        "resident_transfer",
        f"from={from_shelter} to={to_shelter} note={note}".strip(),
    )

def ensure_admin_bootstrap() -> None:
    row = db_fetchone("SELECT COUNT(1) AS c FROM staff_users WHERE role = 'admin'")
    count = int(row["c"] if isinstance(row, dict) else row[0])
    if count > 0:
        return

    admin_user = (os.environ.get("ADMIN_USERNAME") or "").strip()
    admin_pass = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if not admin_user or not admin_pass:
        return

    db_execute(
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        (admin_user, generate_password_hash(admin_pass), "admin", True, utcnow_iso()),
    )


def init_db() -> None:
    get_db()
    kind = g.get("db_kind")

    def create(sqlite_sql: str, pg_sql: str) -> None:
        db_execute(pg_sql if kind == "pg" else sqlite_sql)

    
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

    create(
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS residents (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            resident_code TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL
        )
        """,
    )

    try:
        if kind == "pg":
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS resident_code TEXT")
        else:
            db_execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass

    try:
        db_execute("CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq ON residents (resident_code)")
    except Exception:
        pass

    rows = db_fetchall(
        "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
        if kind == "pg"
        else "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
    )

    for r in rows:
        rid = r["id"] if isinstance(r, dict) else r[0]
        code = make_resident_code()
        for _ in range(10):
            exists = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if kind == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (code,),
            )
            if not exists:
                break
            code = make_resident_code()

        db_execute(
            "UPDATE residents SET resident_code = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET resident_code = ? WHERE id = ?",
            (code, rid),
        )
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_transfers (
              id SERIAL PRIMARY KEY,
              resident_id INTEGER NOT NULL REFERENCES residents(id),
              from_shelter TEXT NOT NULL,
              to_shelter TEXT NOT NULL,
              transferred_by TEXT NOT NULL,
              transferred_at TIMESTAMP NOT NULL DEFAULT NOW(),
              note TEXT
            );
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_transfers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              resident_id INTEGER NOT NULL,
              from_shelter TEXT NOT NULL,
              to_shelter TEXT NOT NULL,
              transferred_by TEXT NOT NULL,
              transferred_at TEXT NOT NULL,
              note TEXT,
              FOREIGN KEY(resident_id) REFERENCES residents(id)
            );
            """
        )
    create(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
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
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            resident_phone TEXT,
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
    # migration safety: add resident_phone if the table already existed
    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        pass
    
    # transport requests
    create(
        """
        CREATE TABLE IF NOT EXISTS transport_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
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
            resident_identifier TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
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
    # migration: remove dob column if it already exists (Postgres only)
    try:
        if g.get("db_kind") == "pg":
            db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")
    except Exception:
        pass
    
    create(
        """
        CREATE TABLE IF NOT EXISTS attendance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            shelter TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            staff_user_id INTEGER,
            note TEXT,
            expected_back_time TEXT
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
            note TEXT,
            expected_back_time TEXT
        )
        """,
    )

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


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "staff_user_id" not in session:
            return redirect(url_for("staff_login"))
        get_db()
        return fn(*args, **kwargs)

    return wrapper

# User roles
USER_ROLES = {"admin", "staff", "case_manager", "ra"}
STAFF_ROLES = {"admin", "staff", "case_manager", "ra"}
TRANSFER_ROLES = {"admin", "case_manager"}

def require_staff_or_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in STAFF_ROLES:
            flash("Staff only.", "error")
            return redirect(url_for("staff_home"))
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

def require_resident(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "resident_id" not in session:
            return redirect(url_for("resident_signin", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def require_transfer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in TRANSFER_ROLES:
            flash("Admin or case manager only.", "error")
            return redirect(url_for("staff_home"))
        return fn(*args, **kwargs)
    return wrapper
    
@app.get("/privacy")
def privacy_policy():
    return (
        "Privacy Policy – Downtown Women’s Center\n\n"
        "Downtown Women’s Center collects phone numbers only for operational communication "
        "related to shelter services, including leave approvals, transportation scheduling, "
        "and service notifications.\n\n"
        "We do not sell, rent, or share personal information with third parties for marketing purposes.\n\n"
        "SMS consent is not shared with third parties or affiliates for marketing purposes.\n\n"
        "If you have questions about this policy, please contact Downtown Women’s Center at 806-XXX-XXXX.\n"
    ), 200, {"Content-Type": "text/plain; charset=utf-8"}

@app.get("/terms")
def terms_and_conditions():
    return (
        "Terms and Conditions – Downtown Women’s Center\n\n"
        "By opting in to receive SMS messages from Downtown Women’s Center, "
        "you agree to receive operational notifications related to shelter services, "
        "including leave approvals, transportation scheduling, reminders, and service updates.\n\n"
        "Message frequency varies. Message and data rates may apply.\n\n"
        "You may opt out at any time by replying STOP.\n"
        "For assistance, reply HELP.\n\n"
        "Downtown Women’s Center is not responsible for delayed or undelivered messages.\n"
    ), 200, {"Content-Type": "text/plain; charset=utf-8"}

@app.route("/")
def public_home():
    return redirect(url_for("resident_leave"))


@app.route("/debug/db")
@require_login
@require_admin
def debug_db():
    if not ENABLE_DEBUG_ROUTES:
        abort(404)

    live_env = (os.environ.get("DATABASE_URL") or "").strip()
    try:
        init_db()
    except Exception as e:
        return {
            "ok": False,
            "error": "db init failed",
            "db_kind": g.get("db_kind"),
        }, 500

    return {
        "ok": True,
        "db_kind": g.get("db_kind"),
    }


def _find_active_resident_by_code(shelter: str, resident_code: str) -> Optional[dict[str, Any]]:
    res = db_fetchone(
        "SELECT resident_identifier, first_name, last_name, phone FROM residents WHERE shelter = %s AND resident_code = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT resident_identifier, first_name, last_name, phone FROM residents WHERE shelter = ? AND resident_code = ? AND is_active = 1",
        (shelter, resident_code),
    )
    if not res:
        return None

    if isinstance(res, dict):
        return {
            "resident_identifier": res.get("resident_identifier", ""),
            "first_name": res.get("first_name", ""),
            "last_name": res.get("last_name", ""),
            "phone": res.get("phone", "") or "",
        }

    return {
        "resident_identifier": res[0] or "",
        "first_name": res[1] or "",
        "last_name": res[2] or "",
        "phone": res[3] or "",
    }
@app.route("/resident", methods=["GET", "POST"])
def resident_signin():
    init_db()

    if request.method == "GET":
        shelter = (request.args.get("shelter") or "").strip()
        next_url = (request.args.get("next") or "").strip()
        return render_template(
            "resident_signin.html",
            shelters=SHELTERS,
            shelter=(shelter if shelter in SHELTERS else ""),
            next=next_url,
        )

    shelter = (request.form.get("shelter") or "").strip()
    resident_code = (request.form.get("resident_code") or "").strip()
    next_url = (request.form.get("next") or "").strip()

    if shelter not in SHELTERS:
        flash("Select a valid shelter.", "error")
        return redirect(url_for("resident_signin"))

    if (not resident_code.isdigit()) or (len(resident_code) != 8):
        flash("Enter your 8 digit Resident Code.", "error")
        return redirect(url_for("resident_signin", shelter=shelter))

    row = db_fetchone(
        "SELECT id, resident_identifier, first_name, last_name, phone FROM residents WHERE shelter = %s AND resident_code = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT id, resident_identifier, first_name, last_name, phone FROM residents WHERE shelter = ? AND resident_code = ? AND is_active = 1",
        (shelter, resident_code),
    )

    if not row:
        flash("Invalid Resident Code.", "error")
        return redirect(url_for("resident_signin", shelter=shelter))

    resident_session_start(row, shelter, resident_code)

    # NEW BLOCK STARTS HERE
    if not next_url or not next_url.startswith("/"):
        next_url = url_for("resident_leave")

    if not session.get("sms_consent_done"):
        return redirect(url_for("resident_consent", next=next_url))

    return redirect(next_url)
  
@app.get("/resident/home")
@require_resident
def resident_home():
    return render_template("resident_home.html")

@app.get("/resident/logout")
def resident_logout():
    for k in [
        "resident_id",
        "resident_identifier",
        "resident_first",
        "resident_last",
        "resident_phone",
        "resident_shelter",
        "resident_code",
        "sms_consent_done",
        "sms_opt_in",
    ]:
        session.pop(k, None)
    return redirect(url_for("resident_signin"))

@app.route("/leave", methods=["GET", "POST"])
@require_resident
def resident_leave():
    init_db()

    if request.method == "GET":
        shelter = session.get("resident_shelter") or ""
        return render_template(
            "resident_leave.html",
            shelter=shelter,
            max_days=MAX_LEAVE_DAYS,
        )

    # POST
    shelter = session.get("resident_shelter") or ""
    resident_identifier = session.get("resident_identifier") or ""
    first = session.get("resident_first") or ""
    last = session.get("resident_last") or ""
    resident_phone = (request.form.get("resident_phone") or "").strip()
    if resident_phone:
        db_execute(
            "UPDATE residents SET phone = %s WHERE shelter = %s AND resident_identifier = %s"
            if g.get("db_kind") == "pg"
            else "UPDATE residents SET phone = ? WHERE shelter = ? AND resident_identifier = ?",
            (resident_phone, shelter, resident_identifier),
        )

    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    leave_at_raw = (request.form.get("leave_at") or "").strip()
    return_at_raw = (request.form.get("return_at") or "").strip()
    agreed = request.form.get("agreed") == "on"

    errors: list[str] = []

    if not agreed:
        errors.append("You must accept the agreement.")
        
    if not first or not last or not destination or not leave_at_raw or not return_at_raw:
        errors.append("Complete all required fields.")
    if not resident_phone:
        errors.append("A phone number is required for text updates.")

    try:
        leave_dt = parse_dt(leave_at_raw)
        return_dt = parse_dt(return_at_raw)
        if return_dt <= leave_dt:
            errors.append("Return must be after leave.")
        if return_dt > leave_dt + timedelta(days=MAX_LEAVE_DAYS):
            errors.append(f"Maximum leave is {MAX_LEAVE_DAYS} days.")
    except Exception:
        errors.append("Invalid date.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template(
            "resident_leave.html",
            shelters=SHELTERS,
            shelter=shelter,
            max_days=MAX_LEAVE_DAYS,
        ), 400

    sql = (
        """
        INSERT INTO leave_requests
        (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO leave_requests
        (shelter, resident_identifier, first_name, last_name, resident_phone, destination, reason, resident_notes, leave_at, return_at, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    leave_iso = leave_dt.replace(microsecond=0).isoformat()
    return_iso = return_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    params = (
        shelter,
        resident_identifier or "",
        first,
        last,
        resident_phone,
        destination,
        reason or None,
        resident_notes or None,
        leave_iso,
        return_iso,
        submitted,
    )

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        req_id = cur.lastrowid

    log_action("leave", req_id, shelter, None, "create", "Resident submitted leave request")
    return render_template("resident_submitted.html", request_id=req_id, kind="Leave request submitted")


@app.route("/transport", methods=["GET", "POST"])
@require_resident
def resident_transport():
    init_db()

    if request.method == "GET":
        shelter = session.get("resident_shelter") or ""
        return render_template("resident_transport.html", shelter=shelter)

    # POST
    shelter = session.get("resident_shelter") or ""
    resident_identifier = session.get("resident_identifier") or ""
    first = session.get("resident_first") or ""
    last = session.get("resident_last") or ""

    needed_raw = (request.form.get("needed_at") or "").strip()
    pickup = (request.form.get("pickup_location") or "").strip()
    destination = (request.form.get("destination") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    resident_notes = (request.form.get("resident_notes") or "").strip()
    callback_phone = (request.form.get("callback_phone") or "").strip()

   
    errors: list[str] = []
    if not first or not last or not needed_raw or not pickup or not destination:
        errors.append("Complete all required fields.")

    try:
        needed_local = parse_dt(needed_raw)
        needed_dt = (
            needed_local
            .replace(tzinfo=ZoneInfo("America/Chicago"))
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        if needed_dt < datetime.utcnow() - timedelta(minutes=1):
            errors.append("Needed time cannot be in the past.")
    except Exception:
        errors.append("Invalid needed date or time.")

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("resident_transport.html", shelter=shelter), 400

    sql = (
        """
        INSERT INTO transport_requests
        (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
        RETURNING id
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO transport_requests
        (shelter, resident_identifier, first_name, last_name, needed_at, pickup_location, destination, reason, resident_notes, callback_phone, status, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """
    )

    needed_iso = needed_dt.replace(microsecond=0).isoformat()
    submitted = utcnow_iso()

    params = (
        shelter,
        resident_identifier or "",
        first,
        last,
        needed_iso,
        pickup,
        destination,
        reason or None,
        resident_notes or None,
        callback_phone or None,
        submitted,
    )

    if g.get("db_kind") == "pg":
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        req_id = cur.fetchone()[0]
        cur.close()
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        req_id = cur.lastrowid

    log_action("transport", req_id, shelter, None, "create", "Resident submitted transport request")
    return render_template("resident_submitted.html", request_id=req_id, kind="Transportation request submitted")

@app.get("/resident/sms-consent")
def sms_consent():
    return """
    <html>
        <head>
            <title>SMS Consent - Downtown Women’s Center</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
            <h2>SMS Updates from Downtown Women’s Center</h2>

            <p>
                To receive SMS updates regarding shelter leave approvals, transportation notifications,
                and service reminders, text <strong>JOIN</strong> to <strong>+1 806 639 4503</strong>.
            </p>

            <p>
                Message frequency varies. Message and data rates may apply.
                Reply STOP to opt out. Reply HELP for help.
            </p>

            <p>
                <a href="/privacy">Privacy Policy</a><br>
                <a href="/terms">Terms and Conditions</a>
            </p>
        </body>
    </html>
    """


@app.route("/resident/consent", methods=["GET", "POST"])
def resident_consent():
    next_url = (request.args.get("next") or request.form.get("next") or "").strip()
    if not next_url or not next_url.startswith("/"):
        next_url = url_for("resident_leave")

    if request.method == "GET":
        return render_template("resident_consent.html", next=next_url)

    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in ["accept", "decline"]:
        flash("Select accept or decline.", "error")
        return render_template("resident_consent.html", next=next_url), 400

    session["sms_consent_done"] = True
    session["sms_opt_in"] = True if choice == "accept" else False

    return redirect(next_url)

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

    # NEW: go back to the page you were on
    nxt = (request.form.get("next") or "").strip()
    if nxt and nxt.startswith("/staff"):
        return redirect(nxt)

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
    return render_template("staff_leave_pending.html", rows=rows, fmt_dt=fmt_dt, fmt_date=fmt_date, shelter=shelter)


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

    # pull approved leaves not yet checked in
    rows = db_fetchall(
        """
        SELECT * FROM leave_requests
        WHERE status = %s AND shelter = %s AND check_in_at IS NULL
        ORDER BY return_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT * FROM leave_requests
        WHERE status = ? AND shelter = ? AND check_in_at IS NULL
        ORDER BY return_at ASC
        """,
        ("approved", shelter),
    )

    now_local = datetime.now(ZoneInfo("America/Chicago"))
    overdue_rows = []

    for r in rows:
        # sqlite Row and pg dict both support r["return_at"]
        return_iso = r["return_at"] if isinstance(r, dict) or hasattr(r, "__getitem__") else None
        if not return_iso:
            continue

        try:
            rt_utc = datetime.fromisoformat(return_iso).replace(tzinfo=timezone.utc)
            rt_local = rt_utc.astimezone(ZoneInfo("America/Chicago"))
            cutoff_local = rt_local.replace(hour=22, minute=0, second=0, microsecond=0)

            if now_local > cutoff_local:
                overdue_rows.append(r)
        except Exception:
            continue

    return render_template(
        "staff_leave_overdue.html",
        rows=overdue_rows,
        fmt_dt=fmt_dt,
        fmt_date=fmt_date,
        shelter=shelter,
    )


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

    req = db_fetchone(
        "SELECT first_name, last_name, leave_at, return_at, resident_phone FROM leave_requests WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT first_name, last_name, leave_at, return_at, resident_phone FROM leave_requests WHERE id = ? AND shelter = ?",
        (req_id, shelter),
    )

    if req:
        first_name = req["first_name"] if isinstance(req, dict) else req[0]
        last_name = req["last_name"] if isinstance(req, dict) else req[1]
        leave_at = req["leave_at"] if isinstance(req, dict) else req[2]
        return_at = req["return_at"] if isinstance(req, dict) else req[3]
        phone = req["resident_phone"] if isinstance(req, dict) else req[4]

        msg = (
    f"Leave approved for {first_name} {last_name}. "
    f"Leave {fmt_pretty_date(leave_at)}. "
    f"Return {fmt_pretty_date(return_at)} by 10 PM."
)
        try:
            if phone:
                send_sms(phone, msg)
        except Exception as e:
            log_action("leave", req_id, shelter, staff_id, "sms_failed", str(e))

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


@app.route("/staff/transport/board")
@require_login
@require_shelter
def staff_transport_board():
    shelter = session["shelter"]

    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = %s
          AND status IN (%s, %s)
        ORDER BY needed_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = ?
          AND status IN (?, ?)
        ORDER BY needed_at ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if day:
        filtered = []
        for r in rows:
            try:
                needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
                dt = parse_dt(needed_at_val)
                if dt.strftime("%Y-%m-%d") == day:
                    filtered.append(r)
            except Exception:
                pass
        rows = filtered

    return render_template("staff_transport_board.html", rows=rows, shelter=shelter, fmt_dt=fmt_dt)


@app.route("/staff/transport/print")
@require_login
@require_shelter
def staff_transport_print():
    import html as _html

    shelter = session["shelter"]
    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = %s
          AND status IN (%s, %s)
        ORDER BY needed_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = ?
          AND status IN (?, ?)
        ORDER BY needed_at ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if not day:
        day = datetime.utcnow().strftime("%Y-%m-%d")

    filtered = []
    for r in rows:
        try:
            needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
            dt = parse_dt(needed_at_val)
            if dt.strftime("%Y-%m-%d") == day:
                filtered.append(r)
        except Exception:
            pass

    rows = filtered

    def _cell(v):
        return _html.escape("" if v is None else str(v))

    trs = []
    for r in rows:
        needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
        needed_at = fmt_dt(needed_at_val)
        first = r.get("first_name") if isinstance(r, dict) else r["first_name"]
        last = r.get("last_name") if isinstance(r, dict) else r["last_name"]
        pickup = r.get("pickup_location") if isinstance(r, dict) else r["pickup_location"]
        dest = r.get("destination") if isinstance(r, dict) else r["destination"]
        status = r.get("status") if isinstance(r, dict) else r["status"]

        name = f"{last}, {first}"

        trs.append(
            "<tr>"
            f"<td>{_cell(needed_at)}</td>"
            f"<td>{_cell(name)}</td>"
            f"<td>{_cell(pickup)}</td>"
            f"<td>{_cell(dest)}</td>"
            f"<td>{_cell(status)}</td>"
            "</tr>"
        )

    table_rows = "\n".join(trs) if trs else '<tr><td colspan="5">No rides found.</td></tr>'

    html_doc = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Transportation Sheet</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; }}
    h1 {{ margin: 0 0 10px 0; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #999; padding: 8px; font-size: 12px; vertical-align: top; }}
    th {{ text-align: left; }}
    .toolbar {{ margin-bottom: 12px; display:flex; gap:10px; }}
    @media print {{
      .toolbar {{ display:none; }}
      body {{ margin: 0.5in; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar">
    <button onclick="window.print()">Print</button>
    <button onclick="window.close()">Close</button>
  </div>

  <h1>Transportation Sheet, {_cell(shelter)} | {_cell(day)}</h1>

  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Name</th>
        <th>Pickup</th>
        <th>Destination</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
""".strip()

    return html_doc


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
    shelter = session["shelter"]
    init_db()

    residents = db_fetchall(
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
        (shelter,),
    )

    out_rows: list[dict[str, Any]] = []
    in_rows: list[dict[str, Any]] = []

    for r in residents:
        rid = int(r["id"] if isinstance(r, dict) else r[0])
        first = r["first_name"] if isinstance(r, dict) else r[4]
        last = r["last_name"] if isinstance(r, dict) else r[5]

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

        last_event_type = ""
        last_event_time = ""
        if last_event:
            last_event_type = last_event["event_type"] if isinstance(last_event, dict) else last_event[0]
            last_event_time = last_event["event_time"] if isinstance(last_event, dict) else last_event[1]

        last_checkout = db_fetchone(
            """
            SELECT event_time, expected_back_time
            FROM attendance_events
            WHERE resident_id = %s AND shelter = %s AND event_type = %s
            ORDER BY event_time DESC
            LIMIT 1
            """
            if g.get("db_kind") == "pg"
            else
            """
            SELECT event_time, expected_back_time
            FROM attendance_events
            WHERE resident_id = ? AND shelter = ? AND event_type = ?
            ORDER BY event_time DESC
            LIMIT 1
            """,
            (rid, shelter, "check_out"),
        )

        checkout_time = ""
        expected_back_time = ""
        if last_checkout:
            checkout_time = last_checkout["event_time"] if isinstance(last_checkout, dict) else last_checkout[0]
            expected_back_time = last_checkout["expected_back_time"] if isinstance(last_checkout, dict) else (last_checkout[1] or "")

        checkin_after_checkout_time = ""
        if checkout_time:
            checkin_after = db_fetchone(
                """
                SELECT event_time
                FROM attendance_events
                WHERE resident_id = %s AND shelter = %s AND event_type = %s AND event_time > %s
                ORDER BY event_time DESC
                LIMIT 1
                """
                if g.get("db_kind") == "pg"
                else
                """
                SELECT event_time
                FROM attendance_events
                WHERE resident_id = ? AND shelter = ? AND event_type = ? AND event_time > ?
                ORDER BY event_time DESC
                LIMIT 1
                """,
                (rid, shelter, "check_in", checkout_time),
            )
            if checkin_after:
                checkin_after_checkout_time = checkin_after["event_time"] if isinstance(checkin_after, dict) else checkin_after[0]

        is_out = last_event_type == "check_out"
        is_overdue = False
        if is_out and expected_back_time:
            try:
                is_overdue = parse_dt(expected_back_time) < datetime.utcnow()
            except Exception:
                is_overdue = False

        date_source = checkout_time or (last_event_time or "")
        date_value = ""
        if date_source:
            try:
                dt = parse_dt(date_source).replace(tzinfo=timezone.utc)
                local_dt = dt.astimezone(ZoneInfo("America/Chicago"))
                date_value = local_dt.strftime("%Y-%m-%d")
            except Exception:
                date_value = date_source[:10]

        row = {
            "resident_id": rid,
            "first_name": first,
            "last_name": last,
            "name": f"{last}, {first}",
            "date": date_value,
            "checked_out_at": checkout_time,
            "expected_back_at": expected_back_time,
            "checked_in_at": checkin_after_checkout_time,
            "is_out": is_out,
            "is_overdue": is_overdue,
        }

        if is_out:
            out_rows.append(row)
        else:
            in_rows.append(row)

    out_rows.sort(key=lambda x: (x["last_name"].lower(), x["first_name"].lower()))
    in_rows.sort(key=lambda x: (x["last_name"].lower(), x["first_name"].lower()))

    return render_template(
        "staff_attendance.html",
        out_rows=out_rows,
        in_rows=in_rows,
        fmt_time=fmt_time_only,
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
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    db_execute(sql, (resident_id, shelter, "check_in", utcnow_iso(), staff_id, note or None, None))
    log_action("attendance", resident_id, shelter, staff_id, "check_in", note or "")
    return redirect(url_for("staff_attendance"))


@app.route("/staff/attendance/check-out", methods=["POST"], endpoint="staff_attendance_check_out_global")
@require_login
@require_shelter
def staff_attendance_check_out_global():
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    rid_raw = (request.form.get("resident_id") or "").strip()
    note = (request.form.get("note") or "").strip()
    expected_back = (request.form.get("expected_back_time") or "").strip()

    if not rid_raw.isdigit():
        flash("Select a resident.", "error")
        return redirect(url_for("staff_attendance"))

    resident_id = int(rid_raw)

    resident = db_fetchone(
        "SELECT id FROM residents WHERE id = %s AND shelter = %s AND is_active = TRUE"
        if g.get("db_kind") == "pg"
        else "SELECT id FROM residents WHERE id = ? AND shelter = ? AND is_active = 1",
        (resident_id, shelter),
    )
    if not resident:
        flash("Invalid resident.", "error")
        return redirect(url_for("staff_attendance"))

    expected_back_value = None
    if expected_back:
        try:
            hh, mm = expected_back.split(":")
            now_chi = datetime.now(ZoneInfo("America/Chicago"))
            local_dt = now_chi.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if local_dt <= now_chi:
                local_dt = local_dt + timedelta(days=1)
            expected_back_value = (
                local_dt.astimezone(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds")
            )
        except Exception:
            expected_back_value = None

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(sql, (resident_id, shelter, "check_out", utcnow_iso(), staff_id, note or None, expected_back_value))

    log_action(
        "attendance",
        resident_id,
        shelter,
        staff_id,
        "check_out",
        f"expected_back={expected_back_value or ''} {note or ''}".strip(),
    )

    return redirect(url_for("staff_attendance"))


@app.route("/staff/attendance/resident/<int:resident_id>/print")
@require_login
@require_shelter
def staff_attendance_resident_print(resident_id: int):
    init_db()
    shelter = session["shelter"]

    resident = db_fetchone(
        "SELECT * FROM residents WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE id = ? AND shelter = ?",
        (resident_id, shelter),
    )
    if not resident:
        flash("Resident not found for this shelter.", "error")
        return redirect(url_for("staff_attendance"))

    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    if not end:
        end = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    if not start:
        start_dt = datetime.now(ZoneInfo("America/Chicago")) - timedelta(days=30)
        start = start_dt.strftime("%Y-%m-%d")

    try:
        start_local = datetime.fromisoformat(start + "T00:00:00").replace(tzinfo=ZoneInfo("America/Chicago"))
        end_local = datetime.fromisoformat(end + "T23:59:59").replace(tzinfo=ZoneInfo("America/Chicago"))
        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        flash("Invalid date range. Use YYYY-MM-DD.", "error")
        return redirect(url_for("staff_attendance"))

    events = db_fetchall(
        """
        SELECT
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username AS staff_username
        FROM attendance_events ae
        LEFT JOIN staff_users su ON su.id = ae.staff_user_id
        WHERE ae.resident_id = %s
          AND ae.shelter = %s
          AND ae.event_time >= %s
          AND ae.event_time <= %s
        ORDER BY ae.event_time ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username AS staff_username
        FROM attendance_events ae
        LEFT JOIN staff_users su ON su.id = ae.staff_user_id
        WHERE ae.resident_id = ?
          AND ae.shelter = ?
          AND ae.event_time >= ?
          AND ae.event_time <= ?
        ORDER BY ae.event_time ASC
        """,
        (resident_id, shelter, start_utc, end_utc),
    )

    trip_rows = []
    current_trip = None

    for e in events:
        et = e["event_type"] if isinstance(e, dict) else e[0]
        tm = e["event_time"] if isinstance(e, dict) else e[1]
        eb = e.get("expected_back_time") if isinstance(e, dict) else e[2]
        note_val = e.get("note") if isinstance(e, dict) else e[3]

        if et == "check_out":
            current_trip = {
                "date": tm,
                "checked_out_at": tm,
                "expected_back_at": eb,
                "checked_in_at": "",
                "late": None,
                "note": note_val,
            }
        elif et == "check_in" and current_trip:
            current_trip["checked_in_at"] = tm
            if current_trip["expected_back_at"]:
                try:
                    current_trip["late"] = parse_dt(tm) > parse_dt(current_trip["expected_back_at"])
                except Exception:
                    current_trip["late"] = None
            trip_rows.append(current_trip)
            current_trip = None

    events = trip_rows

    first = resident["first_name"] if isinstance(resident, dict) else resident[4]
    last = resident["last_name"] if isinstance(resident, dict) else resident[5]

    return render_template(
        "staff_attendance_resident_print.html",
        shelter=shelter,
        resident_id=resident_id,
        resident_name=f"{first} {last}",
        start=start,
        end=end,
        events=events,
        fmt_dt=fmt_dt,
    )


@app.route("/kiosk/<shelter>/checkout", methods=["GET"])
def kiosk_checkout(shelter: str):
    if shelter not in SHELTERS:
        return "Invalid shelter", 404

    init_db()

    residents = db_fetchall(
        "SELECT * FROM residents WHERE shelter = %s AND is_active = TRUE ORDER BY last_name, first_name"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE shelter = ? AND is_active = 1 ORDER BY last_name, first_name",
        (shelter,),
    )

    return render_template("kiosk_checkout.html", residents=residents, shelter=shelter)


@app.route("/kiosk/<shelter>/checkout/<int:resident_id>/out", methods=["POST"])
def kiosk_checkout_out(shelter: str, resident_id: int):
    if shelter not in SHELTERS:
        return "Invalid shelter", 404

    init_db()

    note = (request.form.get("note") or "").strip() or None
    expected_back = (request.form.get("expected_back_time") or "").strip()

    expected_back_value = None
    if expected_back:
        try:
            local_dt = datetime.fromisoformat(expected_back).replace(tzinfo=ZoneInfo("America/Chicago"))
            expected_back_value = (
                local_dt.astimezone(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds")
            )
        except Exception:
            expected_back_value = None

    sql = (
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else
        "INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note, expected_back_time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    db_execute(sql, (resident_id, shelter, "check_out", utcnow_iso(), None, note, expected_back_value))
    return redirect(url_for("kiosk_checkout", shelter=shelter))


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

        if role not in USER_ROLES:
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
    return render_template(
    "admin_users.html",
    users=users,
    fmt_dt=fmt_dt,
    roles=sorted(USER_ROLES),
    ROLE_LABELS=ROLE_LABELS
)



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
        first = (request.form.get("first_name") or "").strip()[:15]
        last  = (request.form.get("last_name") or "").strip()[:25]
        phone = (request.form.get("phone") or "").strip()

        if not first or not last:
            flash("First name and last name are required.", "error")
            return redirect(url_for("staff_residents"))

        resident_code = make_resident_code()
        for _ in range(10):
            existing_code = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if g.get("db_kind") == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (resident_code,),
            )
            if not existing_code:
                break
            resident_code = make_resident_code()
        else:
            flash("Could not generate a unique Resident Code. Try again.", "error")
            return redirect(url_for("staff_residents"))

        resident_identifier = secrets.token_urlsafe(12)

        sql = (
            "INSERT INTO residents (shelter, resident_identifier, resident_code, first_name, last_name, phone, is_active, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)"
            if g.get("db_kind") == "pg"
            else
            "INSERT INTO residents (shelter, resident_identifier, resident_code, first_name, last_name, phone, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)"
        )

        db_execute(sql, (shelter, resident_identifier, resident_code, first, last, phone or None, utcnow_iso()))

        log_action("resident", None, shelter, session["staff_user_id"], "create", f"code={resident_code} {first} {last}")

        flash(f"Resident added. Code: {resident_code}", "ok")
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

@app.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
@require_transfer
def staff_resident_transfer(resident_id: int):
    init_db()

    # fetch resident
    resident = db_fetchone(
        "SELECT * FROM residents WHERE id = %s" if g.get("db_kind") == "pg" else "SELECT * FROM residents WHERE id = ?",
        (resident_id,),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("staff_residents"))

    from_shelter = resident["shelter"] if isinstance(resident, dict) else resident[1]
    first_name = resident["first_name"] if isinstance(resident, dict) else resident[4]
    last_name = resident["last_name"] if isinstance(resident, dict) else resident[5]

    if request.method == "POST":
        to_shelter = (request.form.get("to_shelter") or "").strip()
        note = (request.form.get("note") or "").strip()

        if to_shelter not in SHELTERS:
            flash("Select a valid shelter.", "error")
            return redirect(url_for("staff_resident_transfer", resident_id=resident_id))

        if to_shelter == from_shelter:
            flash("Resident is already at that shelter.", "error")
            return redirect(url_for("staff_resident_transfer", resident_id=resident_id))

        # 1) record transfer + audit log (from Step 2 helper)
        record_resident_transfer(
            resident_id=resident_id,
            from_shelter=from_shelter,
            to_shelter=to_shelter,
            note=note,
        )

        # 2) close out attendance at old shelter (force OUT)
        db_execute(
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resident_id,
                from_shelter,
                "check_out",
                utcnow_iso(),
                session.get("staff_user_id"),
                f"Transferred to {to_shelter}. {note}".strip(),
            ),
        )

        # 3) move pending leave + transport to new shelter (match by resident_identifier)
        resident_identifier = resident["resident_identifier"] if isinstance(resident, dict) else resident[2]

        db_execute(
            """
            UPDATE leave_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE leave_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            """
            UPDATE transport_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE transport_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )
        
        # 4) update resident home shelter (resident code stays untouched automatically)
        db_execute(
            "UPDATE residents SET shelter = %s WHERE id = %s" if g.get("db_kind") == "pg" else "UPDATE residents SET shelter = ? WHERE id = ?",
            (to_shelter, resident_id),
        )

        flash(f"Resident transferred from {from_shelter} to {to_shelter}.", "ok")
        return redirect(url_for("staff_residents"))

    # GET
    return render_template(
        "staff_resident_transfer.html",
        resident=resident,
        from_shelter=from_shelter,
        shelters=[s for s in SHELTERS if s != from_shelter],
    )

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
        db_execute("UPDATE residents SET is_active = %s WHERE id = %s AND shelter = %s", (active == "1", resident_id, shelter))
    else:
        db_execute("UPDATE residents SET is_active = ? WHERE id = ? AND shelter = ?", (1 if active == "1" else 0, resident_id, shelter))

    log_action("resident", resident_id, shelter, staff_id, "set_active", f"active={active}")
    flash("Updated.", "ok")
    return redirect(url_for("staff_residents"))


@app.route("/admin/wipe-all-data", methods=["POST"])
@require_login
@require_admin
def wipe_all_data():
    init_db()

    db_execute("TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM attendance_events")
    db_execute("TRUNCATE TABLE leave_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM leave_requests")
    db_execute("TRUNCATE TABLE transport_requests RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM transport_requests")
    db_execute("TRUNCATE TABLE residents RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM residents")
    db_execute("TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE" if g.get("db_kind") == "pg" else "DELETE FROM audit_log")

    log_action("admin", None, None, session.get("staff_user_id"), "wipe_all_data", "Wiped attendance, leave, transport, residents, audit_log")
    return "All non staff data wiped."


@app.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_admin
def recreate_schema():
    init_db()

    if g.get("db_kind") == "pg":
        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS leave_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")

    init_db()
    log_action("admin", None, None, session.get("staff_user_id"), "recreate_schema", "Dropped and recreated tables")
    return "Schema recreated."


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000)

































