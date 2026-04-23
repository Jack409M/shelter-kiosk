from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, request, session, url_for

from core.attendance_hours import build_attendance_hours_snapshot
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from core.l9_support_lifecycle import start_level9_lifecycle
from routes.case_management_parts.budget_scoring import load_budget_score_snapshot
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
...TRUNCATED FOR TOOL...
