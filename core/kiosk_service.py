from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timezone
from typing import Any
from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso

CHICAGO_TZ = ZoneInfo("America/Chicago")


@dataclass(slots=True)
class CheckinResult:
    success: bool
    status_code: int
    errors: list[str] = field(default_factory=list)
    actual_end_required: bool = False
    prior_activity_label: str = ""
    resident_id: int | None = None
    log_note: str = ""
    needs_actual_end_prompt: bool = False


@dataclass(slots=True)
class CheckoutResult:
    success: bool
    status_code: int
    errors: list[str] = field(default_factory=list)
    resident_id: int | None = None
    destination_value: str = ""
    selected_activity_key: str = ""
    aa_na_meeting_1: str = ""
    aa_na_meeting_2: str = ""
    meeting_count: int = 0
    is_recovery_meeting_value: int = 0
    volunteer_community_service_option: str = ""
    obligation_start_value: str | None = None
    obligation_end_value: str | None = None
    expected_back_value: str | None = None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    raw_value = (value or "").strip()
    if not raw_value:
        return None

    try:
        return datetime.fromisoformat(raw_value)
    except Exception:
        return None


def active_resident_id_for_code(shelter: str, resident_code: str) -> int | None:
    normalized_shelter = (shelter or "").strip().lower()
    normalized_code = (resident_code or "").strip()

    row = db_fetchone(
        """
        SELECT id
        FROM residents
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND TRIM(COALESCE(resident_code, '')) = %s
          AND is_active = TRUE
        LIMIT 1
        """,
        (normalized_shelter, normalized_code),
    )

    if not row:
        return None

    resident_id = row.get("id")
    return int(resident_id) if resident_id is not None else None


def latest_open_checkout_row(resident_id: int, shelter: str) -> dict[str, Any] | None:
    row = db_fetchone(
        """
        SELECT
            id,
            event_type,
            event_time,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
        ORDER BY event_time DESC, id DESC
        LIMIT 1
        """,
        (resident_id, (shelter or "").strip().lower()),
    )

    if not row:
        return None

    if (row.get("event_type") or "").strip() != "check_out":
        return None

    return row


def checkout_requires_actual_end_time(checkout_row: dict[str, Any] | None) -> bool:
    if not checkout_row:
        return False

    destination = (checkout_row.get("destination") or "").strip()
    obligation_start = (checkout_row.get("obligation_start_time") or "").strip()
    obligation_end = (checkout_row.get("obligation_end_time") or "").strip()

    return bool(destination and obligation_start and obligation_end)


def manual_time_value(hour_text: str, minute_text: str, ampm_text: str) -> str:
    hour_int = int(hour_text)
    minute_int = int(minute_text)
    ampm_value = (ampm_text or "").strip().upper()

    if hour_int < 1 or hour_int > 12:
        raise ValueError("Invalid hour")

    if minute_int not in {0, 15, 30, 45}:
        raise ValueError("Invalid minute")

    if ampm_value not in {"AM", "PM"}:
        raise ValueError("Invalid AM or PM")

    if ampm_value == "PM" and hour_int != 12:
        hour_int += 12
    elif ampm_value == "AM" and hour_int == 12:
        hour_int = 0

    now_local = datetime.now(CHICAGO_TZ)
    local_dt = now_local.replace(
        hour=hour_int,
        minute=minute_int,
        second=0,
        microsecond=0,
    )

    return (
        local_dt.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def active_pass_row(resident_id: int, shelter: str) -> dict[str, Any] | None:
    normalized_shelter = (shelter or "").strip().lower()
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    return db_fetchone(
        """
        SELECT id, pass_type, destination, end_at, end_date
        FROM resident_passes
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s AND end_at >= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        ORDER BY
            CASE WHEN end_at IS NULL THEN 1 ELSE 0 END,
            end_at ASC,
            end_date ASC,
            id ASC
        LIMIT 1
        """,
        (resident_id, normalized_shelter, "approved", now_iso, now_iso, today_iso, today_iso),
    )


def pass_expected_back_value(pass_row: dict[str, Any]) -> str | None:
    end_at = (pass_row.get("end_at") or "").strip()
    if end_at:
        return end_at

    end_date = (pass_row.get("end_date") or "").strip()
    if not end_date:
        return None

    local_end = datetime.combine(
        date_cls.fromisoformat(end_date),
        time_cls(23, 59, 59),
        tzinfo=CHICAGO_TZ,
    )

    return (
        local_end.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def update_resident_rad_progress(
    resident_id: int,
    shelter: str,
    destination_label: str | None,
) -> None:
    if not resident_id:
        return

    if (destination_label or "").strip().lower() != "rad":
        return

    completed_at_value = utcnow_iso()

    db_execute(
        """
        UPDATE residents
        SET
            rad_classes_attended = COALESCE(rad_classes_attended, 0) + 1,
            rad_completed = CASE
                WHEN COALESCE(rad_classes_attended, 0) + 1 >= 30 THEN %s
                ELSE COALESCE(rad_completed, %s)
            END,
            rad_completed_at = CASE
                WHEN COALESCE(rad_classes_attended, 0) + 1 >= 30
                     AND (rad_completed_at IS NULL OR rad_completed_at = '')
                THEN %s
                ELSE rad_completed_at
            END
        WHERE id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
        """,
        (
            True,
            False,
            completed_at_value,
            resident_id,
            (shelter or "").strip().lower(),
        ),
    )


def handle_checkin(
    *,
    shelter: str,
    resident_code: str,
    actual_end_hour: str,
    actual_end_minute: str,
    actual_end_ampm: str,
) -> CheckinResult:
    normalized_shelter = (shelter or "").strip().lower()
    normalized_code = (resident_code or "").strip()

    errors: list[str] = []

    if (not normalized_code.isdigit()) or (len(normalized_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    resident_id = active_resident_id_for_code(normalized_shelter, normalized_code)
    if resident_id is None:
        errors.append("Invalid Resident Code.")

    if errors:
        return CheckinResult(
            success=False,
            status_code=400,
            errors=errors,
        )

    open_checkout = latest_open_checkout_row(resident_id, normalized_shelter)
    actual_end_required = checkout_requires_actual_end_time(open_checkout)
    prior_activity_label = (
        (open_checkout.get("destination") or "").strip()
        if open_checkout
        else ""
    )

    if actual_end_required and not (actual_end_hour and actual_end_minute and actual_end_ampm):
        return CheckinResult(
            success=False,
            status_code=200,
            actual_end_required=True,
            prior_activity_label=prior_activity_label,
            resident_id=resident_id,
            needs_actual_end_prompt=True,
        )

    checkin_time_value = utcnow_iso()
    checkin_time_dt = _parse_iso_datetime(checkin_time_value)
    actual_obligation_end_value: str | None = None

    if actual_end_required:
        try:
            actual_obligation_end_value = manual_time_value(
                actual_end_hour,
                actual_end_minute,
                actual_end_ampm,
            )
        except Exception:
            return CheckinResult(
                success=False,
                status_code=400,
                errors=["Invalid actual obligation end time."],
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_id=resident_id,
            )

        actual_obligation_end_dt = _parse_iso_datetime(actual_obligation_end_value)
        planned_start_dt = _parse_iso_datetime(
            (open_checkout or {}).get("obligation_start_time")
        )

        if (
            planned_start_dt is not None
            and actual_obligation_end_dt is not None
            and actual_obligation_end_dt < planned_start_dt
        ):
            return CheckinResult(
                success=False,
                status_code=400,
                errors=["Actual end time cannot be earlier than the scheduled start time."],
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_id=resident_id,
            )

        if (
            checkin_time_dt is not None
            and actual_obligation_end_dt is not None
            and actual_obligation_end_dt > checkin_time_dt
        ):
            return CheckinResult(
                success=False,
                status_code=400,
                errors=["Actual end time cannot be later than the time you are checking in."],
                actual_end_required=True,
                prior_activity_label=prior_activity_label,
                resident_id=resident_id,
            )

    from routes.attendance_parts.helpers import complete_active_passes

    with db_transaction():
        if actual_end_required and actual_obligation_end_value and open_checkout:
            checkout_id = int(open_checkout["id"])
            db_execute(
                """
                UPDATE attendance_events
                SET actual_obligation_end_time = %s
                WHERE id = %s
                  AND resident_id = %s
                  AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
                """,
                (actual_obligation_end_value, checkout_id, resident_id, normalized_shelter),
            )

        db_execute(
            """
            INSERT INTO attendance_events (
                resident_id,
                shelter,
                event_type,
                event_time,
                staff_user_id,
                note,
                expected_back_time,
                destination,
                obligation_start_time,
                obligation_end_time,
                meeting_count,
                meeting_1,
                meeting_2,
                is_recovery_meeting
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                normalized_shelter,
                "check_in",
                checkin_time_value,
                None,
                None,
                None,
                None,
                None,
                None,
                0,
                None,
                None,
                0,
            ),
        )

        complete_active_passes(resident_id, normalized_shelter)

    log_note = ""
    if actual_end_required and actual_obligation_end_value:
        log_note = f"actual_obligation_end_time={actual_obligation_end_value}"

    return CheckinResult(
        success=True,
        status_code=302,
        actual_end_required=actual_end_required,
        prior_activity_label=prior_activity_label,
        resident_id=resident_id,
        log_note=log_note,
    )


def handle_checkout(
    *,
    shelter: str,
    resident_code: str,
    destination: str,
    aa_na_meeting_1: str,
    aa_na_meeting_2: str,
    volunteer_community_service_option: str,
    start_time_hour: str,
    start_time_minute: str,
    start_time_ampm: str,
    end_time_hour: str,
    end_time_minute: str,
    end_time_ampm: str,
    expected_back_hour: str,
    expected_back_minute: str,
    expected_back_ampm: str,
    note: str,
    checkout_categories: list[dict[str, Any]],
    aa_na_child_options: list[dict[str, Any]],
    volunteer_child_options: list[dict[str, Any]],
    aa_na_parent_activity_key: str,
    volunteer_parent_activity_key: str,
) -> CheckoutResult:
    normalized_shelter = (shelter or "").strip().lower()
    normalized_code = (resident_code or "").strip()
    normalized_destination = (destination or "").strip()

    errors: list[str] = []

    if (not normalized_code.isdigit()) or (len(normalized_code) != 8):
        errors.append("Enter an 8 digit Resident Code.")

    if not normalized_destination:
        errors.append("Activity Category is required.")

    resident_id = active_resident_id_for_code(normalized_shelter, normalized_code)
    if resident_id is None:
        errors.append("Invalid Resident Code.")

    category_map = {
        (item.get("activity_label") or "").strip(): item
        for item in checkout_categories
        if (item.get("activity_label") or "").strip()
    }
    selected_category = category_map.get(normalized_destination)

    if normalized_destination and not selected_category:
        errors.append("Please select a valid Activity Category.")

    selected_activity_key = (
        (selected_category.get("activity_key") or "").strip()
        if selected_category
        else ""
    )

    child_option_labels = {
        (item.get("option_label") or "").strip()
        for item in aa_na_child_options
        if (item.get("option_label") or "").strip()
    }

    volunteer_option_labels = {
        (item.get("option_label") or "").strip()
        for item in volunteer_child_options
        if (item.get("option_label") or "").strip()
    }

    is_aa_na_meeting = selected_activity_key == aa_na_parent_activity_key
    is_volunteer_community_service = (
        selected_activity_key == volunteer_parent_activity_key
    )

    if is_aa_na_meeting:
        if not aa_na_meeting_1:
            errors.append("Meeting 1 is required for AA or NA Meeting.")
        elif aa_na_meeting_1 not in child_option_labels:
            errors.append("Please select a valid Meeting 1 option.")

        if aa_na_meeting_2 and aa_na_meeting_2 not in child_option_labels:
            errors.append("Please select a valid Meeting 2 option.")

        if aa_na_meeting_1 and aa_na_meeting_2 and aa_na_meeting_1 == aa_na_meeting_2:
            errors.append("Meeting 1 and Meeting 2 cannot be the same.")

    if is_volunteer_community_service:
        if not volunteer_community_service_option:
            errors.append("Volunteer or Community Service selection is required.")
        elif volunteer_community_service_option not in volunteer_option_labels:
            errors.append("Please select a valid Volunteer or Community Service option.")

    expected_back_value: str | None = None
    obligation_start_value: str | None = None
    obligation_end_value: str | None = None
    active_pass: dict[str, Any] | None = None

    requires_approved_pass = bool(
        selected_category.get("requires_approved_pass")
    ) if selected_category else False

    if resident_id is not None and requires_approved_pass:
        active_pass = active_pass_row(resident_id, normalized_shelter)

    if requires_approved_pass:
        if not active_pass:
            errors.append("No approved pass found for that Activity Category.")
        else:
            expected_back_value = pass_expected_back_value(active_pass)
    else:
        if not start_time_hour or not start_time_minute or not start_time_ampm:
            errors.append("Start Time is required.")
        else:
            try:
                obligation_start_value = manual_time_value(
                    start_time_hour,
                    start_time_minute,
                    start_time_ampm,
                )
            except Exception:
                errors.append("Invalid Start Time.")

        if not end_time_hour or not end_time_minute or not end_time_ampm:
            errors.append("End Time is required.")
        else:
            try:
                obligation_end_value = manual_time_value(
                    end_time_hour,
                    end_time_minute,
                    end_time_ampm,
                )
            except Exception:
                errors.append("Invalid End Time.")

        if not expected_back_hour or not expected_back_minute or not expected_back_ampm:
            errors.append("Expected Back to Shelter is required.")
        else:
            try:
                expected_back_value = manual_time_value(
                    expected_back_hour,
                    expected_back_minute,
                    expected_back_ampm,
                )
            except Exception:
                errors.append("Invalid Expected Back to Shelter.")

    if errors:
        return CheckoutResult(
            success=False,
            status_code=400,
            errors=errors,
        )

    meeting_count = 0
    meeting_1_value: str | None = None
    meeting_2_value: str | None = None
    is_recovery_meeting_value = 0

    if is_aa_na_meeting:
        meeting_1_value = aa_na_meeting_1 or None
        meeting_2_value = aa_na_meeting_2 or None

        if meeting_1_value:
            meeting_count += 1
        if meeting_2_value:
            meeting_count += 1

        is_recovery_meeting_value = 1

    note_parts: list[str] = []

    if normalized_destination:
        note_parts.append(f"Activity Category: {normalized_destination}")

    if is_aa_na_meeting and aa_na_meeting_1:
        note_parts.append(f"Meeting 1: {aa_na_meeting_1}")

    if is_aa_na_meeting and aa_na_meeting_2:
        note_parts.append(f"Meeting 2: {aa_na_meeting_2}")

    if is_volunteer_community_service and volunteer_community_service_option:
        note_parts.append(
            f"Volunteer or Community Service: {volunteer_community_service_option}"
        )

    if requires_approved_pass and active_pass:
        pass_id = active_pass.get("id")
        pass_type = (active_pass.get("pass_type") or "").strip()
        pass_destination = (active_pass.get("destination") or "").strip()

        if pass_id:
            note_parts.append(f"Pass ID: {pass_id}")
        if pass_type:
            note_parts.append(f"Pass Type: {pass_type}")
        if pass_destination:
            note_parts.append(f"Pass Destination: {pass_destination}")

    if note:
        note_parts.append(note)

    full_note = " | ".join(note_parts) if note_parts else None

    with db_transaction():
        db_execute(
            """
            INSERT INTO attendance_events (
                resident_id,
                shelter,
                event_type,
                event_time,
                staff_user_id,
                note,
                expected_back_time,
                destination,
                obligation_start_time,
                obligation_end_time,
                meeting_count,
                meeting_1,
                meeting_2,
                is_recovery_meeting
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resident_id,
                normalized_shelter,
                "check_out",
                utcnow_iso(),
                None,
                full_note,
                expected_back_value,
                normalized_destination,
                obligation_start_value,
                obligation_end_value,
                meeting_count,
                meeting_1_value,
                meeting_2_value,
                is_recovery_meeting_value,
            ),
        )

        update_resident_rad_progress(
            resident_id=resident_id,
            shelter=normalized_shelter,
            destination_label=normalized_destination,
        )

    return CheckoutResult(
        success=True,
        status_code=302,
        resident_id=resident_id,
        destination_value=normalized_destination,
        selected_activity_key=selected_activity_key,
        aa_na_meeting_1=aa_na_meeting_1,
        aa_na_meeting_2=aa_na_meeting_2,
        meeting_count=meeting_count,
        is_recovery_meeting_value=is_recovery_meeting_value,
        volunteer_community_service_option=volunteer_community_service_option,
        obligation_start_value=obligation_start_value,
        obligation_end_value=obligation_end_value,
        expected_back_value=expected_back_value,
    )
