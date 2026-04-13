from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import current_app, flash, request, session

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.data_integrity import check_resident_integrity
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.pass_rules import CHICAGO_TZ, is_late_standard_pass_request


@dataclass(slots=True)
class PassRequestContext:
    shelter: str
    resident_id: int
    resident_identifier: str
    first_name: str
    last_name: str
    resident_level: str
    resident_phone_from_db: str
    hour_summary: object | None


@dataclass(slots=True)
class PassRequestFormData:
    pass_type: str
    destination: str
    reason: str
    resident_notes: str
    request_date: str
    requirements_acknowledged: str
    requirements_not_met_explanation: str
    who_with: str
    destination_address: str
    destination_phone: str
    companion_names: str
    companion_phone_numbers: str
    budgeted_amount: str
    resident_phone: str
    start_at_raw: str
    end_at_raw: str
    start_date_raw: str
    end_date_raw: str
    special_reason: str

    def as_form_dict(self) -> dict[str, str]:
        return {
            "pass_type": self.pass_type,
            "destination": self.destination,
            "reason": self.reason,
            "resident_notes": self.resident_notes,
            "request_date": self.request_date,
            "requirements_acknowledged": self.requirements_acknowledged,
            "requirements_not_met_explanation": self.requirements_not_met_explanation,
            "who_with": self.who_with,
            "destination_address": self.destination_address,
            "destination_phone": self.destination_phone,
            "companion_names": self.companion_names,
            "companion_phone_numbers": self.companion_phone_numbers,
            "budgeted_amount": self.budgeted_amount,
            "resident_phone": self.resident_phone,
            "start_at": self.start_at_raw,
            "end_at": self.end_at_raw,
            "start_date": self.start_date_raw,
            "end_date": self.end_date_raw,
            "special_reason": self.special_reason,
        }


@dataclass(slots=True)
class PassRequestValidationResult:
    errors: list[str]
    start_at_iso: str | None
    end_at_iso: str | None
    start_date_iso: str | None
    end_date_iso: str | None
    late_submission_flag: bool

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalized_pass_type(value: object) -> str:
    return _clean_text(value).lower()


def _normalized_yes_no(value: object) -> str:
    normalized = _clean_text(value).lower()
    if normalized in {"yes", "no"}:
        return normalized
    return normalized


def _digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _money_or_none(value: object) -> Decimal | None:
    text = _clean_text(value)
    if not text:
        return None

    normalized = text.replace("$", "").replace(",", "")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation:
        return None

    return parsed.quantize(Decimal("0.01"))


def today_chicago_iso() -> str:
    return datetime.now(CHICAGO_TZ).date().isoformat()


def parse_date_only(value: str | None) -> date | None:
    text = _clean_text(value)
    if not text:
        return None

    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def status_is_open_for_discipline(value: str | None) -> bool:
    return _clean_text(value).lower() == "open"


def load_resident_profile(resident_id: int) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT
            id,
            shelter,
            program_level,
            phone
        FROM residents
        WHERE id = %s
        LIMIT 1
        """,
        (resident_id,),
    )


def load_active_writeup_restrictions(resident_id: int) -> list[dict[str, Any]]:
    rows = db_fetchall(
        """
        SELECT
            id,
            incident_date,
            category,
            severity,
            summary,
            status,
            disciplinary_outcome,
            probation_start_date,
            probation_end_date,
            pre_termination_date,
            blocks_passes
        FROM resident_writeups
        WHERE resident_id = %s
          AND COALESCE(blocks_passes, 0) IN (1, TRUE)
        ORDER BY incident_date DESC, id DESC
        """,
        (resident_id,),
    )

    today = datetime.now(CHICAGO_TZ).date()
    active_restrictions: list[dict[str, Any]] = []

    for source_row in rows:
        item = dict(source_row)
        outcome = _clean_text(item.get("disciplinary_outcome")).lower()
        is_open = status_is_open_for_discipline(item.get("status"))

        if outcome == "program_probation":
            start_date = parse_date_only(item.get("probation_start_date"))
            end_date = parse_date_only(item.get("probation_end_date"))
            is_active = bool(
                is_open
                and start_date is not None
                and end_date is not None
                and start_date <= today <= end_date
            )
            if is_active:
                item["restriction_label"] = "Program Probation"
                item["restriction_detail"] = (
                    f"{item.get('probation_start_date') or '—'} to "
                    f"{item.get('probation_end_date') or '—'}"
                )
                active_restrictions.append(item)

        elif outcome == "pre_termination":
            scheduled_date = parse_date_only(item.get("pre_termination_date"))
            is_active = bool(
                is_open
                and scheduled_date is not None
                and today <= scheduled_date
            )
            if is_active:
                item["restriction_label"] = "Pre Termination Scheduled"
                item["restriction_detail"] = (
                    f"Scheduled for {item.get('pre_termination_date') or '—'}"
                )
                active_restrictions.append(item)

    return active_restrictions


def load_pass_request_context() -> PassRequestContext | None:
    shelter = _clean_text(session.get("resident_shelter"))
    resident_id_value = session.get("resident_id")

    try:
        resident_id = int(resident_id_value)
    except (TypeError, ValueError):
        return None

    resident_identifier = _clean_text(session.get("resident_identifier"))
    first_name = _clean_text(session.get("resident_first"))
    last_name = _clean_text(session.get("resident_last"))

    if not shelter or not resident_identifier or not first_name or not last_name:
        return None

    integrity_result = check_resident_integrity(resident_id)
    if not integrity_result.ok:
        error_messages = [
            issue.message
            for issue in integrity_result.issues
            if issue.severity == "error"
        ]
        current_app.logger.error(
            "pass request context integrity failure resident_id=%s errors=%s",
            resident_id,
            error_messages,
        )
        return None

    resident_row = load_resident_profile(resident_id)
    if resident_row is None:
        return None

    resident_row_shelter = _clean_text(resident_row.get("shelter"))
    if resident_row_shelter.lower() != shelter.lower():
        current_app.logger.error(
            "pass request context shelter mismatch resident_id=%s session_shelter=%s row_shelter=%s",
            resident_id,
            shelter,
            resident_row_shelter,
        )
        return None

    resident_level = _clean_text(resident_row.get("program_level"))
    resident_phone_from_db = _clean_text(resident_row.get("phone"))

    hour_summary = None
    try:
        hour_summary = calculate_prior_week_attendance_hours(resident_id, shelter)
    except Exception:
        current_app.logger.exception(
            "pass request hour summary failed resident_id=%s shelter=%s",
            resident_id,
            shelter,
        )
        hour_summary = None

    return PassRequestContext(
        shelter=shelter,
        resident_id=resident_id,
        resident_identifier=resident_identifier,
        first_name=first_name,
        last_name=last_name,
        resident_level=resident_level,
        resident_phone_from_db=resident_phone_from_db,
        hour_summary=hour_summary,
    )


def flash_pass_request_restriction_if_blocked(resident_id: int) -> bool:
    active_restrictions = load_active_writeup_restrictions(resident_id)
    if not active_restrictions:
        return False

    first_block = active_restrictions[0]
    flash(
        (
            "Pass requests are disabled because you are under "
            f"{first_block.get('restriction_label')}. "
            f"{first_block.get('restriction_detail')}"
        ).strip(),
        "error",
    )
    return True


def extract_pass_form_data(resident_phone_from_db: str) -> PassRequestFormData:
    return PassRequestFormData(
        pass_type=_normalized_pass_type(request.form.get("pass_type")),
        destination=_clean_text(request.form.get("destination")),
        reason=_clean_text(request.form.get("reason")),
        resident_notes=_clean_text(request.form.get("resident_notes")),
        request_date=_clean_text(request.form.get("request_date")) or today_chicago_iso(),
        requirements_acknowledged=_normalized_yes_no(
            request.form.get("requirements_acknowledged")
        ),
        requirements_not_met_explanation=_clean_text(
            request.form.get("requirements_not_met_explanation")
        ),
        who_with=_clean_text(request.form.get("who_with")),
        destination_address=_clean_text(request.form.get("destination_address")),
        destination_phone=_clean_text(request.form.get("destination_phone")),
        companion_names=_clean_text(request.form.get("companion_names")),
        companion_phone_numbers=_clean_text(request.form.get("companion_phone_numbers")),
        budgeted_amount=_clean_text(request.form.get("budgeted_amount")),
        resident_phone=_clean_text(request.form.get("resident_phone") or resident_phone_from_db),
        start_at_raw=_clean_text(request.form.get("start_at")),
        end_at_raw=_clean_text(request.form.get("end_at")),
        start_date_raw=_clean_text(request.form.get("start_date")),
        end_date_raw=_clean_text(request.form.get("end_date")),
        special_reason=_clean_text(request.form.get("special_reason")),
    )


def validate_pass_request_form(
    *,
    context: PassRequestContext,
    form: PassRequestFormData,
) -> PassRequestValidationResult:
    errors: list[str] = []

    if not context.first_name or not context.last_name or not context.shelter:
        errors.append("Resident session is incomplete. Please sign in again.")

    if form.pass_type not in {"pass", "overnight", "special"}:
        errors.append("Select a valid pass type.")

    if not form.destination:
        errors.append("Destination is required.")

    if not context.resident_level:
        errors.append("Resident level is missing. Please contact staff.")

    if form.pass_type in {"pass", "overnight"} and form.requirements_acknowledged not in {
        "yes",
        "no",
    }:
        errors.append("Please answer whether you will meet all requirements for this pass.")

    if (
        form.pass_type in {"pass", "overnight"}
        and form.requirements_acknowledged == "no"
        and not form.requirements_not_met_explanation
    ):
        errors.append("Please explain why requirements will not be met.")

    if form.pass_type == "special" and not form.special_reason:
        errors.append("Special pass reason is required.")

    if form.destination_phone and len(_digits_only(form.destination_phone)) < 10:
        errors.append("Destination phone must contain at least 10 digits.")

    if form.resident_phone and len(_digits_only(form.resident_phone)) < 10:
        errors.append("Resident phone must contain at least 10 digits.")

    budgeted_amount = _money_or_none(form.budgeted_amount)
    if form.budgeted_amount and budgeted_amount is None:
        errors.append("Budgeted amount must be a valid number.")
    elif budgeted_amount is not None and budgeted_amount < Decimal("0.00"):
        errors.append("Budgeted amount cannot be negative.")

    start_at_iso: str | None = None
    end_at_iso: str | None = None
    start_date_iso: str | None = None
    end_date_iso: str | None = None
    late_submission_flag = False

    now_local = datetime.now(CHICAGO_TZ)

    if form.pass_type in {"pass", "overnight"}:
        if not form.start_at_raw or not form.end_at_raw:
            errors.append("Leave date and time and return date and time are required.")
        else:
            try:
                local_start = datetime.fromisoformat(form.start_at_raw).replace(tzinfo=CHICAGO_TZ)
                local_end = datetime.fromisoformat(form.end_at_raw).replace(tzinfo=CHICAGO_TZ)

                if local_end <= local_start:
                    errors.append("Return time must be after leave time.")

                if local_start < now_local:
                    errors.append("Leave time cannot be in the past.")

                if form.pass_type == "pass" and local_start.date() != local_end.date():
                    errors.append("A normal Pass must begin and end on the same day.")

                if form.pass_type == "overnight" and local_end.date() <= local_start.date():
                    errors.append("An Overnight Pass must return on a later day.")

                late_submission_flag = is_late_standard_pass_request(
                    now_local,
                    local_start,
                    shelter=context.shelter,
                )

                start_at_iso = (
                    local_start.astimezone(timezone.utc)
                    .replace(tzinfo=None)
                    .isoformat(timespec="seconds")
                )
                end_at_iso = (
                    local_end.astimezone(timezone.utc)
                    .replace(tzinfo=None)
                    .isoformat(timespec="seconds")
                )
            except ValueError:
                errors.append("Invalid leave or return date and time.")

    elif form.pass_type == "special":
        if not form.start_date_raw or not form.end_date_raw:
            errors.append("Start date and end date are required for a Special Pass.")
        else:
            try:
                start_date_value = datetime.strptime(form.start_date_raw, "%Y-%m-%d").date()
                end_date_value = datetime.strptime(form.end_date_raw, "%Y-%m-%d").date()

                if end_date_value < start_date_value:
                    errors.append("End date cannot be earlier than start date.")

                if start_date_value < now_local.date():
                    errors.append("Start date cannot be in the past.")

                start_date_iso = start_date_value.isoformat()
                end_date_iso = end_date_value.isoformat()
            except ValueError:
                errors.append("Invalid Special Pass dates.")

    return PassRequestValidationResult(
        errors=errors,
        start_at_iso=start_at_iso,
        end_at_iso=end_at_iso,
        start_date_iso=start_date_iso,
        end_date_iso=end_date_iso,
        late_submission_flag=late_submission_flag,
    )


def insert_pass_request(
    *,
    context: PassRequestContext,
    form: PassRequestFormData,
    validation: PassRequestValidationResult,
) -> int:
    now_iso = utcnow_iso()
    final_reason = form.special_reason if form.pass_type == "special" else form.reason
    staff_notes = "Submitted after configured deadline." if validation.late_submission_flag else None

    with db_transaction():
        pass_row = db_fetchone(
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                start_date,
                end_date,
                destination,
                reason,
                resident_notes,
                staff_notes,
                approved_by,
                approved_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                context.resident_id,
                context.shelter,
                form.pass_type,
                validation.start_at_iso,
                validation.end_at_iso,
                validation.start_date_iso,
                validation.end_date_iso,
                form.destination,
                final_reason or None,
                form.resident_notes or None,
                staff_notes,
                None,
                None,
                now_iso,
                now_iso,
            ),
        )

        if pass_row is None or pass_row.get("id") is None:
            raise RuntimeError("Pass request insert did not return an id.")

        request_id = int(pass_row["id"])

        db_execute(
            """
            INSERT INTO resident_pass_request_details (
                pass_id,
                resident_phone,
                request_date,
                resident_level,
                requirements_acknowledged,
                requirements_not_met_explanation,
                reason_for_request,
                who_with,
                destination_address,
                destination_phone,
                companion_names,
                companion_phone_numbers,
                budgeted_amount,
                approved_amount,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_id,
                form.resident_phone or None,
                form.request_date or None,
                context.resident_level or None,
                form.requirements_acknowledged or None,
                form.requirements_not_met_explanation or None,
                final_reason or None,
                form.who_with or None,
                form.destination_address or None,
                form.destination_phone or None,
                form.companion_names or None,
                form.companion_phone_numbers or None,
                str(_money_or_none(form.budgeted_amount)) if form.budgeted_amount else None,
                None,
                None,
                None,
                None,
                now_iso,
                now_iso,
            ),
        )

    return request_id


def log_pass_insert_failure(
    exc: Exception,
    *,
    resident_id: int,
    shelter: str,
    pass_type: str,
) -> None:
    try:
        current_app.logger.exception(
            "resident pass request insert failed resident_id=%s shelter=%s pass_type=%s",
            resident_id,
            shelter,
            pass_type,
            exc_info=exc,
        )
    except Exception:
        pass
