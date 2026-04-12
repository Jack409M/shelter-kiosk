from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from flask import abort, session

from routes.attendance_parts.pass_policy import has_active_pass_block


MANAGE_PASS_ROLES = {"admin", "shelter_director", "case_manager"}


@dataclass
class StaffPassViewContext:
    shelter: str
    role: str


@dataclass
class StaffPassActionContext:
    shelter: str
    staff_id: int | None
    staff_name: str


def get_staff_pass_view_context() -> StaffPassViewContext:
    return StaffPassViewContext(
        shelter=str(session.get("shelter") or "").strip(),
        role=str(session.get("role") or "").strip(),
    )


def require_manage_passes_role() -> StaffPassViewContext:
    context = get_staff_pass_view_context()
    if context.role not in MANAGE_PASS_ROLES:
        abort(403)
    return context


def get_staff_pass_action_context() -> StaffPassActionContext:
    return StaffPassActionContext(
        shelter=str(session.get("shelter") or "").strip(),
        staff_id=session.get("staff_user_id"),
        staff_name=str(session.get("username") or "").strip(),
    )


def enrich_pending_pass_rows(rows: list[dict]) -> list[dict]:
    processed: list[dict] = []

    for row in rows:
        blocked, restriction_rows = has_active_pass_block(int(row.get("resident_id") or 0))
        item = dict(row)
        item["has_disciplinary_block"] = blocked
        item["disciplinary_restrictions"] = restriction_rows
        processed.append(item)

    return processed


def filter_overdue_pass_rows(rows: list[dict], now_local: datetime) -> list[dict]:
    overdue_rows: list[dict] = []

    for row in rows:
        expected_back_local = row.get("expected_back_local")
        if expected_back_local and expected_back_local < now_local:
            overdue_rows.append(row)

    return overdue_rows


def build_pass_action_redirect_target(target: str, *, pass_id: int) -> tuple[str, dict]:
    if target == "attendance.staff_pass_detail":
        return target, {"pass_id": pass_id}
    return target, {}
