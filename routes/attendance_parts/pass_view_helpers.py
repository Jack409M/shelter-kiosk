from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import abort, session

from routes.attendance_parts.pass_policy import has_active_pass_block


MANAGE_PASS_ROLES = {"admin", "shelter_director", "case_manager"}


# -----------------------------------------
# CONTEXT MODELS
# -----------------------------------------

@dataclass(frozen=True)
class StaffPassViewContext:
    shelter: str
    role: str


@dataclass(frozen=True)
class StaffPassActionContext:
    shelter: str
    staff_id: int | None
    staff_name: str


# -----------------------------------------
# INTERNAL HELPERS
# -----------------------------------------

def _session_str(key: str) -> str:
    return str(session.get(key) or "").strip()


def _session_int(key: str) -> int | None:
    value = session.get(key)
    return int(value) if value is not None else None


def _require_shelter(shelter: str) -> str:
    if not shelter:
        abort(403)
    return shelter


# -----------------------------------------
# CONTEXT BUILDERS
# -----------------------------------------

def get_staff_pass_view_context() -> StaffPassViewContext:
    shelter = _require_shelter(_session_str("shelter"))
    role = _session_str("role")

    return StaffPassViewContext(
        shelter=shelter,
        role=role,
    )


def require_manage_passes_role() -> StaffPassViewContext:
    context = get_staff_pass_view_context()

    if context.role not in MANAGE_PASS_ROLES:
        abort(403)

    return context


def get_staff_pass_action_context() -> StaffPassActionContext:
    shelter = _require_shelter(_session_str("shelter"))

    return StaffPassActionContext(
        shelter=shelter,
        staff_id=_session_int("staff_user_id"),
        staff_name=_session_str("username"),
    )


# -----------------------------------------
# DATA TRANSFORMS
# -----------------------------------------

def enrich_pending_pass_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    for row in rows:
        resident_id = int(row.get("resident_id") or 0)

        blocked, restriction_rows = has_active_pass_block(resident_id)

        enriched.append({
            **row,
            "has_disciplinary_block": blocked,
            "disciplinary_restrictions": restriction_rows,
        })

    return enriched


def filter_overdue_pass_rows(rows: list[dict[str, Any]], now_local: datetime) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if (expected := row.get("expected_back_local")) and expected < now_local
    ]


# -----------------------------------------
# REDIRECT LOGIC
# -----------------------------------------

def build_pass_action_redirect_target(target: str, *, pass_id: int) -> tuple[str, dict]:
    if target == "attendance.staff_pass_detail":
        return target, {"pass_id": pass_id}

    return target, {}
