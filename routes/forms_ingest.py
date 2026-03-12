from __future__ import annotations

import json
import os
from typing import Any

from flask import Blueprint, abort, current_app, g, request

from core.db import db_execute
from core.helpers import utcnow_iso


forms_ingest = Blueprint("forms_ingest", __name__)


def _init_db() -> None:
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return
    raise RuntimeError("INIT_DB_FUNC is not configured")


def _shared_secret() -> str:
    return (os.environ.get("JOTFORM_WEBHOOK_SECRET") or "").strip()


def _require_secret() -> None:
    expected = _shared_secret()
    if not expected:
        abort(500)

    provided = (
        (request.headers.get("X-Webhook-Secret") or "").strip()
        or (request.args.get("secret") or "").strip()
        or (request.form.get("secret") or "").strip()
    )

    if provided != expected:
        abort(403)


def _first_present(payload: dict[str, Any], keys: list[str]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in payload.items()}

    for key in keys:
        value = lowered.get(key.strip().lower())
        if value not in (None, "", []):
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip().replace(",", "")
        return float(text)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _normalize_payload() -> dict[str, Any]:
    if request.is_json:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            return body
        return {}

    payload: dict[str, Any] = {}

    for key in request.form.keys():
        values = request.form.getlist(key)
        if not values:
            payload[key] = ""
        elif len(values) == 1:
            payload[key] = values[0]
        else:
            payload[key] = values

    return payload


def _extract_weekly_summary(payload: dict[str, Any]) -> dict[str, Any]:
    productive_hours = _to_float(
        _first_present(
            payload,
            [
                "Total Productive Hours",
                "total productive hours",
                "total_productive_hours",
            ],
        )
    )

    work_hours = _to_float(
        _first_present(
            payload,
            [
                "Total Work Hours",
                "total work hours",
                "total_work_hours",
            ],
        )
    )

    meeting_count = _to_int(
        _first_present(
            payload,
            [
                "Total Meetings",
                "Total Number of Meetings for the Week",
                "total meetings",
                "total_number_of_meetings_for_the_week",
            ],
        )
    )

    week_start = _first_present(
        payload,
        [
            "Date",
            "date",
            "week_start",
            "week_start_date",
        ],
    )

    return {
        "productive_hours": productive_hours,
        "work_hours": work_hours,
        "meeting_count": meeting_count,
        "week_start": str(week_start).strip() if week_start not in (None, "") else None,
    }


@forms_ingest.route("/webhooks/jotform", methods=["POST"])
def jotform_webhook():
    """
    Receives Jotform submissions and stores the full payload safely.

    This route is intentionally flexible:
    - full payload is always stored
    - only a few stable fields are optionally extracted
    - form wording changes do not break ingestion
    """
    _require_secret()
    _init_db()

    payload = _normalize_payload()
    now = utcnow_iso()

    form_type = str(
        _first_present(
            payload,
            [
                "form_type",
                "Form Type",
                "form name",
                "formName",
                "Form Name",
            ],
        )
        or "unknown"
    ).strip()

    form_source = "jotform"
    source_form_id = _first_present(payload, ["formID", "form_id", "Form ID"])
    source_submission_id = _first_present(
        payload,
        ["submissionID", "submission_id", "Submission ID"],
    )
    submitted_at = _first_present(
        payload,
        ["created_at", "submitted_at", "Submission Date", "Date"],
    )

    resident_id = _to_int(
        _first_present(
            payload,
            [
                "resident_id",
                "Resident ID",
            ],
        )
    )

    enrollment_id = _to_int(
        _first_present(
            payload,
            [
                "enrollment_id",
                "Enrollment ID",
            ],
        )
    )

    kind = g.get("db_kind")
    insert_sql = (
        """
        INSERT INTO resident_form_submissions (
            resident_id,
            enrollment_id,
            form_type,
            form_source,
            source_form_id,
            source_submission_id,
            submitted_at,
            raw_payload_json,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if kind == "pg"
        else """
        INSERT INTO resident_form_submissions (
            resident_id,
            enrollment_id,
            form_type,
            form_source,
            source_form_id,
            source_submission_id,
            submitted_at,
            raw_payload_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    )

    db_execute(
        insert_sql,
        (
            resident_id,
            enrollment_id,
            form_type,
            form_source,
            str(source_form_id).strip() if source_form_id not in (None, "") else None,
            str(source_submission_id).strip() if source_submission_id not in (None, "") else None,
            str(submitted_at).strip() if submitted_at not in (None, "") else None,
            json.dumps(payload, ensure_ascii=False),
            now,
        ),
    )

    # Optional summary extraction only when we have an enrollment_id
    if enrollment_id:
        summary = _extract_weekly_summary(payload)

        if (
            summary["productive_hours"] is not None
            or summary["work_hours"] is not None
            or summary["meeting_count"] is not None
        ):
            summary_sql = (
                """
                INSERT INTO weekly_resident_summary (
                    enrollment_id,
                    week_start,
                    productive_hours,
                    work_hours,
                    meeting_count,
                    submitted_at,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                if kind == "pg"
                else """
                INSERT INTO weekly_resident_summary (
                    enrollment_id,
                    week_start,
                    productive_hours,
                    work_hours,
                    meeting_count,
                    submitted_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
            )

            db_execute(
                summary_sql,
                (
                    enrollment_id,
                    summary["week_start"],
                    summary["productive_hours"],
                    summary["work_hours"],
                    summary["meeting_count"],
                    str(submitted_at).strip() if submitted_at not in (None, "") else now,
                    now,
                    now,
                ),
            )

    return {"ok": True}, 200
