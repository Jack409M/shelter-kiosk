from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import has_app_context

from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso

CHICAGO_TZ = ZoneInfo("America/Chicago")


def cleanup_deadline_from_expected_back(end_at: str | None, end_date: str | None) -> str | None:
    raw_end_at = (end_at or "").strip()
    if raw_end_at:
        try:
            return (datetime.fromisoformat(raw_end_at) + timedelta(hours=48)).isoformat(
                timespec="seconds"
            )
        except Exception:
            return None

    raw_end_date = (end_date or "").strip()
    if raw_end_date:
        try:
            local_dt = datetime.combine(
                datetime.fromisoformat(raw_end_date).date(),
                time(hour=23, minute=59, second=59),
                tzinfo=CHICAGO_TZ,
            )
            utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
            return (utc_dt + timedelta(hours=48)).isoformat(timespec="seconds")
        except Exception:
            return None

    return (datetime.utcnow() + timedelta(hours=48)).isoformat(timespec="seconds")


def _expected_back_deadline(end_at: str | None, end_date: str | None) -> str | None:
    raw_end_at = (end_at or "").strip()
    if raw_end_at:
        try:
            return datetime.fromisoformat(raw_end_at).isoformat(timespec="seconds")
        except Exception:
            return None

    raw_end_date = (end_date or "").strip()
    if raw_end_date:
        try:
            local_dt = datetime.combine(
                datetime.fromisoformat(raw_end_date).date(),
                time(hour=23, minute=59, second=59),
                tzinfo=CHICAGO_TZ,
            )
            utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
            return utc_dt.isoformat(timespec="seconds")
        except Exception:
            return None

    return None


def expire_overdue_approved_passes_for_shelter(shelter: str) -> int:
    if not has_app_context():
        return 0

    now_iso = utcnow_iso()
    rows = db_fetchall(
        """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND LOWER(TRIM(status)) = 'approved'
        """,
        (shelter,),
    )

    expired_count = 0

    for row in rows:
        expected_back_at = _expected_back_deadline(row.get("end_at"), row.get("end_date"))
        if expected_back_at and expected_back_at > now_iso:
            continue

        delete_after_at = cleanup_deadline_from_expected_back(
            row.get("end_at"),
            row.get("end_date"),
        )

        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                updated_at = %s,
                delete_after_at = COALESCE(delete_after_at, %s)
            WHERE id = %s
              AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
              AND LOWER(TRIM(status)) = 'approved'
            """,
            ("expired", now_iso, delete_after_at, row["id"], shelter),
        )
        expired_count += 1

    return expired_count


def backfill_missing_delete_after_at_for_shelter(shelter: str) -> int:
    rows = db_fetchall(
        """
        SELECT id, end_at, end_date
        FROM resident_passes
        WHERE LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND delete_after_at IS NULL
        """,
        (shelter,),
    )

    updated_count = 0

    for row in rows:
        delete_after_at = cleanup_deadline_from_expected_back(
            row.get("end_at"),
            row.get("end_date"),
        )

        db_execute(
            """
            UPDATE resident_passes
            SET delete_after_at = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (delete_after_at, utcnow_iso(), row["id"]),
        )
        updated_count += 1

    return updated_count


def delete_expired_passes_for_shelter(shelter: str) -> int:
    now_iso = utcnow_iso()

    expired_rows = db_fetchall(
        """
        SELECT id
        FROM resident_passes
        WHERE LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND delete_after_at IS NOT NULL
          AND delete_after_at <= %s
        """,
        (shelter, now_iso),
    )

    deleted_count = 0

    for row in expired_rows:
        pass_id = int(row["id"])

        db_execute("DELETE FROM resident_notifications WHERE related_pass_id = %s", (pass_id,))
        db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = %s", (pass_id,))
        db_execute("DELETE FROM resident_passes WHERE id = %s", (pass_id,))
        deleted_count += 1

    return deleted_count


def run_pass_retention_cleanup_for_shelter(shelter: str) -> dict[str, int | str]:
    normalized = str(shelter or "").strip()
    if not normalized:
        return {
            "shelter": "",
            "backfilled": 0,
            "deleted": 0,
        }

    backfilled = backfill_missing_delete_after_at_for_shelter(normalized)
    expire_overdue_approved_passes_for_shelter(normalized)
    deleted = delete_expired_passes_for_shelter(normalized)

    return {
        "shelter": normalized,
        "backfilled": backfilled,
        "deleted": deleted,
    }
