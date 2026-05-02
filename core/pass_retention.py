from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from flask import has_app_context

from core.db import db_execute, db_fetchall, db_transaction
from core.time_utils import CHICAGO_TZ, parse_utc_naive_datetime, utc_naive_iso, utcnow_iso


def _dt_to_utc_naive_iso(value: datetime) -> str:
    normalized = utc_naive_iso(value)
    if normalized is None:
        raise ValueError("datetime value could not be normalized.")
    return normalized


def _utc_naive_now_plus(hours: int) -> str:
    return _dt_to_utc_naive_iso(datetime.now(UTC) + timedelta(hours=hours))


def cleanup_deadline_from_expected_back(end_at: str | None, end_date: str | None) -> str | None:
    raw_end_at = (end_at or "").strip()
    if raw_end_at:
        parsed_end_at = parse_utc_naive_datetime(raw_end_at)
        if parsed_end_at is None:
            return None
        return _dt_to_utc_naive_iso(parsed_end_at + timedelta(hours=48))

    raw_end_date = (end_date or "").strip()
    if raw_end_date:
        try:
            local_dt = datetime.combine(
                datetime.fromisoformat(raw_end_date).date(),
                time(hour=23, minute=59, second=59),
                tzinfo=CHICAGO_TZ,
            )
            utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
            return _dt_to_utc_naive_iso(utc_dt + timedelta(hours=48))
        except Exception:
            return None

    return _utc_naive_now_plus(48)


def _expected_back_deadline(end_at: str | None, end_date: str | None) -> str | None:
    raw_end_at = (end_at or "").strip()
    if raw_end_at:
        parsed_end_at = parse_utc_naive_datetime(raw_end_at)
        if parsed_end_at is None:
            return None
        return _dt_to_utc_naive_iso(parsed_end_at)

    raw_end_date = (end_date or "").strip()
    if raw_end_date:
        try:
            local_dt = datetime.combine(
                datetime.fromisoformat(raw_end_date).date(),
                time(hour=23, minute=59, second=59),
                tzinfo=CHICAGO_TZ,
            )
            utc_dt = local_dt.astimezone(UTC).replace(tzinfo=None)
            return _dt_to_utc_naive_iso(utc_dt)
        except Exception:
            return None

    return None


def expire_overdue_approved_passes_for_shelter(shelter: str) -> int:
    if not has_app_context():
        return 0

    now_iso = utcnow_iso()
    now_dt = parse_utc_naive_datetime(now_iso)

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
        expected_dt = parse_utc_naive_datetime(expected_back_at)

        if expected_dt and now_dt and expected_dt > now_dt:
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
    now_dt = parse_utc_naive_datetime(utcnow_iso())
    if now_dt is None:
        return 0

    rows = db_fetchall(
        """
        SELECT id, delete_after_at
        FROM resident_passes
        WHERE LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
          AND delete_after_at IS NOT NULL
        """,
        (shelter,),
    )

    expired_pass_ids: list[int] = []

    for row in rows:
        delete_after_dt = parse_utc_naive_datetime(row.get("delete_after_at"))
        if delete_after_dt is None or delete_after_dt > now_dt:
            continue

        expired_pass_ids.append(int(row["id"]))

    if not expired_pass_ids:
        return 0

    with db_transaction():
        for pass_id in expired_pass_ids:
            db_execute("DELETE FROM resident_notifications WHERE related_pass_id = %s", (pass_id,))
            db_execute("DELETE FROM resident_pass_request_details WHERE pass_id = %s", (pass_id,))
            db_execute("DELETE FROM resident_passes WHERE id = %s", (pass_id,))

    return len(expired_pass_ids)


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
