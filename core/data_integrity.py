from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso


ACTIVE_PROGRAM_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "active",
        "pending",
        "enrolled",
    }
)


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    code: str
    message: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IntegrityCheckResult:
    ok: bool
    issues: list[IntegrityIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity == "warning" for issue in self.issues)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalized_shelter(value: object) -> str:
    return _clean_text(value).lower()


def _normalized_status(value: object) -> str:
    return _clean_text(value).lower()


def _issue(
    *,
    code: str,
    message: str,
    severity: str,
    **details: Any,
) -> IntegrityIssue:
    return IntegrityIssue(
        code=code,
        message=message,
        severity=severity,
        details=details,
    )


def _row_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resident_row(resident_id: int) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT
            id,
            resident_identifier,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = %s
        LIMIT 1
        """,
        (resident_id,),
    )


def _current_enrollments_for_resident(resident_id: int) -> list[dict[str, Any]]:
    return db_fetchall(
        """
        SELECT
            id,
            resident_id,
            shelter,
            program_status,
            entry_date,
            created_at,
            updated_at
        FROM program_enrollments
        WHERE resident_id = %s
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(program_status, '')) IN ('active', 'pending', 'enrolled')
                THEN 0
                ELSE 1
            END,
            id DESC
        """,
        (resident_id,),
    )


def _latest_intake_for_enrollment(enrollment_id: int) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT
            id,
            enrollment_id,
            created_at,
            updated_at
        FROM intake_assessments
        WHERE enrollment_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


def _latest_family_snapshot_for_enrollment(enrollment_id: int) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT
            id,
            enrollment_id,
            created_at,
            updated_at
        FROM family_snapshots
        WHERE enrollment_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )


def _resident_passes_for_resident(resident_id: int) -> list[dict[str, Any]]:
    return db_fetchall(
        """
        SELECT
            id,
            resident_id,
            shelter,
            status,
            pass_type,
            start_at,
            end_at,
            start_date,
            end_date
        FROM resident_passes
        WHERE resident_id = %s
        ORDER BY id DESC
        """,
        (resident_id,),
    )


def _notifications_for_resident(resident_id: int) -> list[dict[str, Any]]:
    return db_fetchall(
        """
        SELECT
            id,
            resident_id,
            shelter,
            related_pass_id,
            is_read,
            created_at
        FROM resident_notifications
        WHERE resident_id = %s
        ORDER BY id DESC
        """,
        (resident_id,),
    )


def check_resident_integrity(resident_id: int) -> IntegrityCheckResult:
    resident = _resident_row(resident_id)
    if resident is None:
        return IntegrityCheckResult(
            ok=False,
            issues=[
                _issue(
                    code="resident_missing",
                    message="Resident record not found.",
                    severity="error",
                    resident_id=resident_id,
                )
            ],
        )

    issues: list[IntegrityIssue] = []

    resident_shelter = _normalized_shelter(resident.get("shelter"))
    resident_is_active = bool(resident.get("is_active"))
    resident_identifier = _clean_text(resident.get("resident_identifier"))
    resident_code = _clean_text(resident.get("resident_code"))

    if not resident_identifier:
        issues.append(
            _issue(
                code="resident_identifier_missing",
                message="Resident is missing resident_identifier.",
                severity="error",
                resident_id=resident_id,
            )
        )

    if not resident_code:
        issues.append(
            _issue(
                code="resident_code_missing",
                message="Resident is missing resident_code.",
                severity="error",
                resident_id=resident_id,
            )
        )

    if not resident_shelter:
        issues.append(
            _issue(
                code="resident_shelter_missing",
                message="Resident is missing shelter.",
                severity="error",
                resident_id=resident_id,
            )
        )

    enrollments = _current_enrollments_for_resident(resident_id)
    active_enrollments = [
        enrollment
        for enrollment in enrollments
        if _normalized_status(enrollment.get("program_status")) in ACTIVE_PROGRAM_STATUSES
    ]

    if resident_is_active and not active_enrollments:
        issues.append(
            _issue(
                code="active_resident_without_active_enrollment",
                message="Active resident has no active enrollment.",
                severity="error",
                resident_id=resident_id,
            )
        )

    if len(active_enrollments) > 1:
        issues.append(
            _issue(
                code="multiple_active_enrollments",
                message="Resident has multiple active enrollments.",
                severity="error",
                resident_id=resident_id,
                enrollment_ids=[
                    _row_int(enrollment, "id")
                    for enrollment in active_enrollments
                ],
            )
        )

    for enrollment in active_enrollments:
        enrollment_id = _row_int(enrollment, "id")
        enrollment_shelter = _normalized_shelter(enrollment.get("shelter"))

        if enrollment_shelter != resident_shelter:
            issues.append(
                _issue(
                    code="resident_enrollment_shelter_mismatch",
                    message="Resident shelter does not match active enrollment shelter.",
                    severity="error",
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                    resident_shelter=resident_shelter,
                    enrollment_shelter=enrollment_shelter,
                )
            )

        if enrollment_id is None:
            issues.append(
                _issue(
                    code="enrollment_id_invalid",
                    message="Enrollment id is missing or invalid.",
                    severity="error",
                    resident_id=resident_id,
                )
            )
            continue

        intake_row = _latest_intake_for_enrollment(enrollment_id)
        if intake_row is None:
            issues.append(
                _issue(
                    code="intake_missing_for_active_enrollment",
                    message="Active enrollment is missing intake assessment.",
                    severity="error",
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                )
            )

        family_row = _latest_family_snapshot_for_enrollment(enrollment_id)
        if family_row is None:
            issues.append(
                _issue(
                    code="family_snapshot_missing_for_active_enrollment",
                    message="Active enrollment is missing family snapshot.",
                    severity="warning",
                    resident_id=resident_id,
                    enrollment_id=enrollment_id,
                )
            )

    resident_passes = _resident_passes_for_resident(resident_id)
    for pass_row in resident_passes:
        pass_id = _row_int(pass_row, "id")
        pass_shelter = _normalized_shelter(pass_row.get("shelter"))

        if resident_shelter and pass_shelter and pass_shelter != resident_shelter:
            issues.append(
                _issue(
                    code="resident_pass_shelter_mismatch",
                    message="Resident pass shelter does not match resident shelter.",
                    severity="error",
                    resident_id=resident_id,
                    pass_id=pass_id,
                    resident_shelter=resident_shelter,
                    pass_shelter=pass_shelter,
                )
            )

    notifications = _notifications_for_resident(resident_id)
    valid_pass_ids = {
        _row_int(pass_row, "id")
        for pass_row in resident_passes
        if _row_int(pass_row, "id") is not None
    }

    for notification in notifications:
        notification_id = _row_int(notification, "id")
        notification_shelter = _normalized_shelter(notification.get("shelter"))
        related_pass_id = _row_int(notification, "related_pass_id")

        if resident_shelter and notification_shelter and notification_shelter != resident_shelter:
            issues.append(
                _issue(
                    code="resident_notification_shelter_mismatch",
                    message="Resident notification shelter does not match resident shelter.",
                    severity="error",
                    resident_id=resident_id,
                    notification_id=notification_id,
                    resident_shelter=resident_shelter,
                    notification_shelter=notification_shelter,
                )
            )

        if related_pass_id is not None and related_pass_id not in valid_pass_ids:
            issues.append(
                _issue(
                    code="resident_notification_orphaned_pass_reference",
                    message="Resident notification references a pass that does not belong to the resident.",
                    severity="warning",
                    resident_id=resident_id,
                    notification_id=notification_id,
                    related_pass_id=related_pass_id,
                )
            )

    return IntegrityCheckResult(
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )


def ensure_resident_integrity(resident_id: int) -> None:
    result = check_resident_integrity(resident_id)
    if result.ok:
        return

    error_messages = [
        issue.message
        for issue in result.issues
        if issue.severity == "error"
    ]
    raise ValueError(
        f"Resident integrity check failed for resident_id={resident_id}: "
        + "; ".join(error_messages)
    )


def repair_missing_family_snapshot_for_enrollment(enrollment_id: int) -> bool:
    existing_family = _latest_family_snapshot_for_enrollment(enrollment_id)
    if existing_family is not None:
        return False

    now = utcnow_iso()

    db_execute(
        """
        INSERT INTO family_snapshots
        (
            enrollment_id,
            kids_at_dwc,
            kids_served_outside_under_18,
            kids_ages_0_5,
            kids_ages_6_11,
            kids_ages_12_17,
            kids_reunited_while_in_program,
            healthy_babies_born_at_dwc,
            created_at,
            updated_at
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            enrollment_id,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            now,
            now,
        ),
    )

    return True


def repair_resident_integrity(resident_id: int) -> IntegrityCheckResult:
    resident = _resident_row(resident_id)
    if resident is None:
        return IntegrityCheckResult(
            ok=False,
            issues=[
                _issue(
                    code="resident_missing",
                    message="Resident record not found.",
                    severity="error",
                    resident_id=resident_id,
                )
            ],
        )

    with db_transaction():
        enrollments = _current_enrollments_for_resident(resident_id)
        active_enrollments = [
            enrollment
            for enrollment in enrollments
            if _normalized_status(enrollment.get("program_status")) in ACTIVE_PROGRAM_STATUSES
        ]

        for enrollment in active_enrollments:
            enrollment_id = _row_int(enrollment, "id")
            if enrollment_id is None:
                continue
            repair_missing_family_snapshot_for_enrollment(enrollment_id)

    return check_resident_integrity(resident_id)
