#!/usr/bin/env python3
"""Create a sanitized Postgres backup from a disposable restored database.

This script is intentionally conservative. It should be run only against a
local or disposable Postgres database that was restored from a production backup.
It must not be run against the live Railway production database.

Example:
    python scripts/sanitize_backup.py \
        --db-url postgresql://postgres:postgres@localhost:5432/backup_restore_test
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg


SANITIZED_TEXT = "SANITIZED"
FAKE_CITY = "FAKE_CITY"
FAKE_COUNTY = "FAKE_COUNTY"
FAKE_ZIP = "00000"
FAKE_PHONE = "5550000000"
CONFIRM_PHRASE = "SANITIZE DISPOSABLE DATABASE"

PRODUCTION_HOST_MARKERS = (
    "railway.app",
    "rlwy.net",
    "railway.internal",
    "proxy.rlwy.net",
)

SAFE_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "postgres",
}


@dataclass(frozen=True)
class UpdateRule:
    table: str
    assignments: tuple[str, ...]


SANITIZE_RULES: tuple[UpdateRule, ...] = (
    UpdateRule(
        "residents",
        (
            "resident_identifier = 'sanitized-' || id::text",
            "resident_code = 'SR' || lpad(id::text, 8, '0')",
            "first_name = 'Test'",
            "last_name = 'Resident' || lpad(id::text, 4, '0')",
            "phone = '555' || lpad(id::text, 7, '0')",
            "email = 'resident' || id::text || '@example.invalid'",
            "emergency_contact_name = 'Test Contact' || lpad(id::text, 4, '0')",
            "emergency_contact_relationship = 'SANITIZED'",
            "emergency_contact_phone = '555' || lpad((id + 1)::text, 7, '0')",
        ),
    ),
    UpdateRule("resident_children", ("child_name = 'Test Child' || lpad(id::text, 4, '0')", "notes = 'SANITIZED'")),
    UpdateRule("resident_child_income_supports", ("notes = 'SANITIZED'",)),
    UpdateRule("intake_drafts", ("resident_name = 'Test Resident'", "draft_data = '{}'::jsonb", "form_payload = 'SANITIZED'")),
    UpdateRule(
        "intake_assessments",
        (
            "city = 'FAKE_CITY'",
            "county = 'FAKE_COUNTY'",
            "last_zipcode_residence = '00000'",
            "notes_basic = 'SANITIZED'",
            "entry_notes = 'SANITIZED'",
            "initial_snapshot_notes = 'SANITIZED'",
            "trauma_notes = 'SANITIZED'",
            "barrier_notes = 'SANITIZED'",
            "place_staying_before_entry = 'SANITIZED'",
        ),
    ),
    UpdateRule(
        "exit_assessments",
        ("leave_amarillo_city = 'FAKE_CITY'",),
    ),
    UpdateRule("followups", ("notes = 'SANITIZED'",)),
    UpdateRule(
        "case_manager_updates",
        (
            "notes = 'SANITIZED'",
            "progress_notes = 'SANITIZED'",
            "setbacks_or_incidents = 'SANITIZED'",
            "action_items = 'SANITIZED'",
            "overall_summary = 'SANITIZED'",
            "blocker_reason = 'SANITIZED'",
            "override_or_exception = 'SANITIZED'",
            "staff_review_note = 'SANITIZED'",
        ),
    ),
    UpdateRule("case_manager_update_summary", ("old_value = 'SANITIZED'", "new_value = 'SANITIZED'", "detail = 'SANITIZED'")),
    UpdateRule("client_services", ("notes = 'SANITIZED'",)),
    UpdateRule(
        "transport_requests",
        (
            "resident_identifier = 'sanitized-' || id::text",
            "first_name = 'Test'",
            "last_name = 'Resident' || lpad(id::text, 4, '0')",
            "pickup_location = 'SANITIZED'",
            "destination = 'SANITIZED'",
            "reason = 'SANITIZED'",
            "resident_notes = 'SANITIZED'",
            "callback_phone = '555' || lpad(id::text, 7, '0')",
            "staff_notes = 'SANITIZED'",
        ),
    ),
    UpdateRule("resident_transfers", ("transferred_by = 'STAFF USER'", "note = 'SANITIZED'")),
    UpdateRule("attendance_events", ("note = 'SANITIZED'", "destination = 'SANITIZED'", "meeting_1 = 'SANITIZED'", "meeting_2 = 'SANITIZED'")),
    UpdateRule("resident_passes", ("destination = 'SANITIZED'", "reason = 'SANITIZED'", "resident_notes = 'SANITIZED'", "staff_notes = 'SANITIZED'")),
    UpdateRule(
        "resident_pass_request_details",
        (
            "resident_phone = '555' || lpad(id::text, 7, '0')",
            "requirements_not_met_explanation = 'SANITIZED'",
            "reason_for_request = 'SANITIZED'",
            "who_with = 'SANITIZED'",
            "destination_address = 'SANITIZED'",
            "destination_phone = '555' || lpad((id + 1)::text, 7, '0')",
            "companion_names = 'SANITIZED'",
            "companion_phone_numbers = 'SANITIZED'",
            "reviewed_by_name = 'STAFF USER'",
        ),
    ),
    UpdateRule("resident_notifications", ("title = 'SANITIZED'", "message = 'SANITIZED'")),
    UpdateRule("resident_writeups", ("summary = 'SANITIZED'", "full_notes = 'SANITIZED'", "action_taken = 'SANITIZED'", "resolution_notes = 'SANITIZED'")),
    UpdateRule("staff_users", ("username = 'user_' || id::text", "first_name = 'STAFF'", "last_name = 'USER'", "mobile_phone = '555' || lpad(id::text, 7, '0')", "email = 'staff' || id::text || '@example.invalid'")),
    UpdateRule("security_incidents", ("details = 'SANITIZED'", "related_ip = '0.0.0.0'", "related_username = 'SANITIZED'")),
    UpdateRule("security_config_history", ("old_value = 'SANITIZED'", "new_value = 'SANITIZED'")),
    UpdateRule("audit_log", ("action_details = 'SANITIZED'",)),
    UpdateRule("field_change_audit", ("old_value = 'SANITIZED'", "new_value = 'SANITIZED'", "change_reason = 'SANITIZED'")),
    UpdateRule("child_services", ("notes = 'SANITIZED'",)),
    UpdateRule("resident_needs", ("source_value = 'SANITIZED'", "resolution_note = 'SANITIZED'")),
    UpdateRule("resident_medications", ("medication_name = 'SANITIZED'", "dosage = 'SANITIZED'", "frequency = 'SANITIZED'", "purpose = 'SANITIZED'", "prescribed_by = 'SANITIZED'", "notes = 'SANITIZED'")),
    UpdateRule("resident_ua_log", ("substances_detected = 'SANITIZED'", "notes = 'SANITIZED'")),
    UpdateRule("resident_living_area_inspections", ("notes = 'SANITIZED'",)),
    UpdateRule("resident_budget_sessions", ("notes = 'SANITIZED'",)),
    UpdateRule("chore_templates", ("description = 'SANITIZED'",)),
    UpdateRule("chore_assignments", ("notes = 'SANITIZED'",)),
    UpdateRule("kiosk_activity_categories", ("notes = 'SANITIZED'",)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sanitize a disposable Postgres database and export it as .sql.gz."
    )
    parser.add_argument("--db-url", required=True, help="Disposable Postgres database URL to sanitize.")
    parser.add_argument(
        "--output-dir",
        default="backups/sanitized",
        help="Directory for sanitized backup output. Default: backups/sanitized",
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required safety phrase: {CONFIRM_PHRASE}",
    )
    return parser.parse_args()


def require_safe_db_url(db_url: str, confirm: str) -> None:
    if confirm != CONFIRM_PHRASE:
        raise SystemExit(f"ERROR: --confirm must exactly equal: {CONFIRM_PHRASE}")

    parsed = urlparse(db_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise SystemExit("ERROR: --db-url must be a Postgres URL.")

    host = (parsed.hostname or "").lower()
    if not host:
        raise SystemExit("ERROR: --db-url must include a hostname.")

    if host in SAFE_HOSTS:
        return

    if host.endswith(".local") or host.endswith(".internal"):
        return

    if any(marker in host for marker in PRODUCTION_HOST_MARKERS):
        raise SystemExit(f"ERROR: refusing production-like database host: {host}")

    raise SystemExit(
        "ERROR: refusing to sanitize a non-local database host. "
        "Restore the backup to localhost or a clearly disposable database first."
    )


def table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = %s
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def column_exists(conn: psycopg.Connection, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    return row is not None


def assignment_column(assignment: str) -> str:
    return assignment.split("=", 1)[0].strip()


def sanitize_database(db_url: str) -> None:
    with psycopg.connect(db_url) as conn:
        with conn.transaction():
            for rule in SANITIZE_RULES:
                if not table_exists(conn, rule.table):
                    print(f"[sanitize] skipping missing table: {rule.table}")
                    continue

                assignments = [
                    assignment
                    for assignment in rule.assignments
                    if column_exists(conn, rule.table, assignment_column(assignment))
                ]

                if not assignments:
                    print(f"[sanitize] no mapped columns present for table: {rule.table}")
                    continue

                sql = f"UPDATE {rule.table} SET " + ", ".join(assignments)
                conn.execute(sql)
                print(f"[sanitize] sanitized {rule.table}: {len(assignments)} columns")


def require_pg_dump() -> None:
    if not shutil.which("pg_dump"):
        raise SystemExit("ERROR: pg_dump was not found on PATH. Install PostgreSQL client tools first.")


def export_sanitized_backup(db_url: str, output_dir: Path) -> Path:
    require_pg_dump()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_file = output_dir / f"shelter-kiosk-sanitized-{timestamp}.sql.gz"

    print(f"[export] writing {output_file}")
    with gzip.open(output_file, "wb") as gz_file:
        process = subprocess.run(
            [
                "pg_dump",
                "--no-owner",
                "--no-privileges",
                "--format=plain",
                db_url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if process.returncode != 0:
            raise SystemExit(process.stderr.decode("utf-8", errors="replace"))
        gz_file.write(process.stdout)

    if output_file.stat().st_size <= 0:
        raise SystemExit("ERROR: sanitized backup file was empty.")

    return output_file


def write_sha256(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sha_path = path.with_suffix(path.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return sha_path


def main() -> int:
    args = parse_args()
    db_url = args.db_url.strip()
    require_safe_db_url(db_url, args.confirm)

    print("[safety] database target accepted as disposable")
    sanitize_database(db_url)
    output_file = export_sanitized_backup(db_url, Path(args.output_dir))
    sha_file = write_sha256(output_file)

    print("[complete] sanitized backup created")
    print(f"[complete] file: {output_file}")
    print(f"[complete] sha256: {sha_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
