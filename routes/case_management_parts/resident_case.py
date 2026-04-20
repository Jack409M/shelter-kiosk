from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app, flash, redirect, render_template, session, url_for

from core.attendance_hours import build_attendance_hours_snapshot
from core.db import db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_children import load_children_with_services
from routes.case_management_parts.resident_case_discipline import load_active_writeup_restrictions
from routes.case_management_parts.resident_case_employment import (
    build_employment_income_snapshot,
    build_employment_stability_snapshot,
    load_employment_income_defaults,
    resolve_employment_status_snapshot,
    resolve_monthly_income_for_display,
)
from routes.case_management_parts.resident_case_enrollment_context import (
    base_empty_enrollment_context,
    calculate_grit_difference,
    load_enrollment_context,
)
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)
from routes.case_management_parts.resident_case_viewmodel import (
    build_meeting_defaults,
    build_operations_snapshot,
    build_workspace_header,
)
from routes.case_management_parts.budget_scoring import load_budget_score_snapshot
from routes.inspection_v2 import build_inspection_stability_snapshot
from routes.rent_tracking import build_rent_stability_snapshot

# rest of file unchanged until context build

    budget_summary = _safe_load(
        "budget_summary",
        lambda: _load_current_budget_summary(resident["id"], enrollment_id),
        _default_budget_summary,
    )

    budget_score_snapshot = _safe_load(
        "budget_score",
        lambda: load_budget_score_snapshot(resident["id"]),
        lambda: {},
    )

    return {
        # existing context
        "budget_summary": budget_summary,
        "budget_score_snapshot": budget_score_snapshot,
        # rest unchanged
    }
