from __future__ import annotations

from statistics import median

from flask import Blueprint, flash, redirect, render_template, request, session, url_for, g

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

operations_settings = Blueprint(
    "operations_settings",
    __name__,
    url_prefix="/staff/admin/operations-settings",
)


DEFAULT_INSPECTION_ITEMS = [
    "Floors clean",
    "Bed made",
    "Trash removed",
    "Bathroom clean",
    "No prohibited items visible",
    "General room condition acceptable",
]


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _director_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director"}


def _to_bool(value: str | None, default: bool = False) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return default


def _to_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip() or str(default))
    except Exception:
        return default


def _to_float(value: str | None, default: float) -> float:
    try:
        return float((value or "").strip() or str(default))
    except Exception:
        return default


def _default_labels_text() -> str:
    return "\n".join(DEFAULT_INSPECTION_ITEMS)


def _currency(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 2)


def _ensure_operations_settings_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                inspection_scoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
                inspection_include_current_open_month BOOLEAN NOT NULL DEFAULT FALSE,
                inspection_score_passed INTEGER NOT NULL DEFAULT 100,
                inspection_needs_attention_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
                inspection_score_failed INTEGER NOT NULL DEFAULT 0,
                inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
                inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
                inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
                inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
                inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
                employment_income_module_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                employment_income_graduation_minimum DOUBLE PRECISION NOT NULL DEFAULT 1200.00,
                employment_income_band_green_min DOUBLE PRECISION NOT NULL DEFAULT 1200.00,
                employment_income_band_yellow_min DOUBLE PRECISION NOT NULL DEFAULT 1000.00,
                employment_income_band_orange_min DOUBLE PRECISION NOT NULL DEFAULT 700.00,
                employment_income_band_red_max DOUBLE PRECISION NOT NULL DEFAULT 699.99,
                income_weight_employment DOUBLE PRECISION NOT NULL DEFAULT 1.00,
                income_weight_ssi_ssdi_self DOUBLE PRECISION NOT NULL DEFAULT 1.00,
                income_weight_child_support DOUBLE PRECISION NOT NULL DEFAULT 0.50,
                income_weight_alimony DOUBLE PRECISION NOT NULL DEFAULT 0.50,
                income_weight_other_income DOUBLE PRECISION NOT NULL DEFAULT 0.25,
                income_weight_survivor_cutoff_months INTEGER NOT NULL DEFAULT 18,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                inspection_scoring_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
                inspection_include_current_open_month INTEGER NOT NULL DEFAULT 0,
                inspection_score_passed INTEGER NOT NULL DEFAULT 100,
                inspection_needs_attention_enabled INTEGER NOT NULL DEFAULT 0,
                inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
                inspection_score_failed INTEGER NOT NULL DEFAULT 0,
                inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
                inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
                inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
                inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
                inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
                employment_income_module_enabled INTEGER NOT NULL DEFAULT 1,
                employment_income_graduation_minimum REAL NOT NULL DEFAULT 1200.00,
                employment_income_band_green_min REAL NOT NULL DEFAULT 1200.00,
                employment_income_band_yellow_min REAL NOT NULL DEFAULT 1000.00,
                employment_income_band_orange_min REAL NOT NULL DEFAULT 700.00,
                employment_income_band_red_max REAL NOT NULL DEFAULT 699.99,
                income_weight_employment REAL NOT NULL DEFAULT 1.00,
                income_weight_ssi_ssdi_self REAL NOT NULL DEFAULT 1.00,
                income_weight_child_support REAL NOT NULL DEFAULT 0.50,
                income_weight_alimony REAL NOT NULL DEFAULT 0.50,
                income_weight_other_income REAL NOT NULL DEFAULT 0.25,
                income_weight_survivor_cutoff_months INTEGER NOT NULL DEFAULT 18,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    statements = [
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_late_day_of_month INTEGER DEFAULT 6",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_partially_paid INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid_late INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_not_paid INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_exempt INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_carry_forward_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_default_item_status TEXT DEFAULT 'passed'",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_item_labels TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_scoring_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_lookback_months INTEGER DEFAULT 9",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_include_current_open_month BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_passed INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_needs_attention_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_needs_attention INTEGER DEFAULT 70",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_failed INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_passing_threshold INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_green_min INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_yellow_min INTEGER DEFAULT 78",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_orange_min INTEGER DEFAULT 56",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_red_max INTEGER DEFAULT 55",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_module_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_graduation_minimum DOUBLE PRECISION DEFAULT 1200.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_green_min DOUBLE PRECISION DEFAULT 1200.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_yellow_min DOUBLE PRECISION DEFAULT 1000.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_orange_min DOUBLE PRECISION DEFAULT 700.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS employment_income_band_red_max DOUBLE PRECISION DEFAULT 699.99",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_employment DOUBLE PRECISION DEFAULT 1.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_ssi_ssdi_self DOUBLE PRECISION DEFAULT 1.00",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_child_support DOUBLE PRECISION DEFAULT 0.50",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_alimony DOUBLE PRECISION DEFAULT 0.50",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_other_income DOUBLE PRECISION DEFAULT 0.25",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS income_weight_survivor_cutoff_months INTEGER DEFAULT 18",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _settings_row_for_shelter(shelter: str):
    _ensure_operations_settings_table()
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    if row:
        return row

    now = utcnow_iso()
    db_execute(
        (
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled,
                inspection_lookback_months,
                inspection_include_current_open_month,
                inspection_score_passed,
                inspection_needs_attention_enabled,
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_child_support,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled,
                inspection_lookback_months,
                inspection_include_current_open_month,
                inspection_score_passed,
                inspection_needs_attention_enabled,
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_child_support,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            shelter,
            6,
            100,
            75,
            75,
            0,
            100,
            True if g.get("db_kind") == "pg" else 1,
            "passed",
            _default_labels_text(),
            True if g.get("db_kind") == "pg" else 1,
            9,
            False if g.get("db_kind") == "pg" else 0,
            100,
            False if g.get("db_kind") == "pg" else 0,
            70,
            0,
            83,
            83,
            78,
            56,
            55,
            True if g.get("db_kind") == "pg" else 1,
            1200.00,
            1200.00,
            1000.00,
            700.00,
            699.99,
            1.00,
            1.00,
            0.50,
            0.50,
            0.25,
            18,
            now,
            now,
        ),
    )
    return db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )


def _employment_income_guidance(shelter: str) -> dict:
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            pe.id AS enrollment_id,
            ea.income_at_exit,
            ea.graduation_income_snapshot,
            f.followup_type,
            f.followup_date,
            f.sober_at_followup
        FROM program_enrollments pe
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        LEFT JOIN followups f ON f.enrollment_id = pe.id
        WHERE LOWER(COALESCE(pe.shelter, '')) = {ph}
          AND COALESCE(ea.exit_category, '') = 'Successful Completion'
          AND COALESCE(ea.exit_reason, '') = 'Program Graduated'
          AND COALESCE(ea.graduate_dwc, 0) = 1
        ORDER BY pe.id ASC, COALESCE(f.followup_date, '') DESC
        """,
        (shelter,),
    )

    graduates: dict[int, dict] = {}
    for row in rows:
        enrollment_id = int(row["enrollment_id"])
        graduate = graduates.get(enrollment_id)
        if not graduate:
            snapshot = row.get("graduation_income_snapshot")
            if snapshot in (None, ""):
                snapshot = row.get("income_at_exit")
            graduate = {
                "graduation_income": float(snapshot) if snapshot not in (None, "") else None,
                "followups": {},
            }
            graduates[enrollment_id] = graduate

        followup_type = (row.get("followup_type") or "").strip()
        if followup_type not in {"6_month", "1_year"}:
            continue

        existing = graduate["followups"].get(followup_type)
        current_date = row.get("followup_date") or ""
        existing_date = existing.get("followup_date") if existing else ""

        if existing and existing_date >= current_date:
            continue

        graduate["followups"][followup_type] = {
            "followup_date": current_date,
            "sober": bool(int(row.get("sober_at_followup") or 0)),
        }

    graduation_incomes: list[float] = []
    six_month_sober_incomes: list[float] = []
    one_year_sober_incomes: list[float] = []

    for graduate in graduates.values():
        grad_income = graduate["graduation_income"]
        if grad_income is not None:
            graduation_incomes.append(grad_income)

        six_month = graduate["followups"].get("6_month")
        if six_month and six_month["sober"] and grad_income is not None:
            six_month_sober_incomes.append(grad_income)

        one_year = graduate["followups"].get("1_year")
        if one_year and one_year["sober"] and grad_income is not None:
            one_year_sober_incomes.append(grad_income)

    return {
        "average_graduation_income": _average_or_none(graduation_incomes),
        "median_graduation_income": _median_or_none(graduation_incomes),
        "average_sober_6_month_income": _average_or_none(six_month_sober_incomes),
        "average_sober_12_month_income": _average_or_none(one_year_sober_incomes),
    }


@operations_settings.route("", methods=["GET", "POST"])
@require_login
@require_shelter
def settings_page():
    if not _director_allowed():
        flash("Admin or shelter director access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    row = _settings_row_for_shelter(shelter)

    if request.method == "POST":
        now = utcnow_iso()

        late_day = min(max(_to_int(request.form.get("rent_late_day_of_month"), 6), 1), 28)
        carry_forward_enabled = _to_bool(request.form.get("rent_carry_forward_enabled"), True)

        inspection_default_item_status = (request.form.get("inspection_default_item_status") or "passed").strip().lower()
        if inspection_default_item_status not in {"passed", "needs_attention", "failed"}:
            inspection_default_item_status = "passed"

        inspection_item_labels = (request.form.get("inspection_item_labels") or "").strip() or _default_labels_text()

        rent_score_paid = _to_int(request.form.get("rent_score_paid"), 100)
        rent_score_partially_paid = _to_int(request.form.get("rent_score_partially_paid"), 75)
        rent_score_paid_late = _to_int(request.form.get("rent_score_paid_late"), 75)
        rent_score_not_paid = _to_int(request.form.get("rent_score_not_paid"), 0)
        rent_score_exempt = _to_int(request.form.get("rent_score_exempt"), 100)

        inspection_scoring_enabled = _to_bool(request.form.get("inspection_scoring_enabled"), True)
        inspection_lookback_months = max(_to_int(request.form.get("inspection_lookback_months"), 9), 1)
        inspection_include_current_open_month = _to_bool(
            request.form.get("inspection_include_current_open_month"),
            False,
        )
        inspection_score_passed = _to_int(request.form.get("inspection_score_passed"), 100)
        inspection_needs_attention_enabled = _to_bool(
            request.form.get("inspection_needs_attention_enabled"),
            False,
        )
        inspection_score_needs_attention = _to_int(request.form.get("inspection_score_needs_attention"), 70)
        inspection_score_failed = _to_int(request.form.get("inspection_score_failed"), 0)
        inspection_passing_threshold = _to_int(request.form.get("inspection_passing_threshold"), 83)
        inspection_band_green_min = _to_int(request.form.get("inspection_band_green_min"), 83)
        inspection_band_yellow_min = _to_int(request.form.get("inspection_band_yellow_min"), 78)
        inspection_band_orange_min = _to_int(request.form.get("inspection_band_orange_min"), 56)
        inspection_band_red_max = _to_int(request.form.get("inspection_band_red_max"), 55)

        if inspection_band_green_min < inspection_band_yellow_min:
            inspection_band_green_min = inspection_band_yellow_min + 1
        if inspection_band_yellow_min < inspection_band_orange_min:
            inspection_band_yellow_min = inspection_band_orange_min + 1
        if inspection_band_red_max >= inspection_band_orange_min:
            inspection_band_red_max = inspection_band_orange_min - 1

        employment_income_module_enabled = _to_bool(
            request.form.get("employment_income_module_enabled"),
            True,
        )
        employment_income_graduation_minimum = _to_float(
            request.form.get("employment_income_graduation_minimum"),
            1200.00,
        )
        employment_income_band_green_min = _to_float(
            request.form.get("employment_income_band_green_min"),
            1200.00,
        )
        employment_income_band_yellow_min = _to_float(
            request.form.get("employment_income_band_yellow_min"),
            1000.00,
        )
        employment_income_band_orange_min = _to_float(
            request.form.get("employment_income_band_orange_min"),
            700.00,
        )
        employment_income_band_red_max = _to_float(
            request.form.get("employment_income_band_red_max"),
            699.99,
        )

        if employment_income_band_green_min < employment_income_band_yellow_min:
            employment_income_band_green_min = employment_income_band_yellow_min + 0.01
        if employment_income_band_yellow_min < employment_income_band_orange_min:
            employment_income_band_yellow_min = employment_income_band_orange_min + 0.01
        if employment_income_band_red_max >= employment_income_band_orange_min:
            employment_income_band_red_max = employment_income_band_orange_min - 0.01

        income_weight_employment = max(_to_float(request.form.get("income_weight_employment"), 1.00), 0.0)
        income_weight_ssi_ssdi_self = max(_to_float(request.form.get("income_weight_ssi_ssdi_self"), 1.00), 0.0)
        income_weight_child_support = max(_to_float(request.form.get("income_weight_child_support"), 0.50), 0.0)
        income_weight_alimony = max(_to_float(request.form.get("income_weight_alimony"), 0.50), 0.0)
        income_weight_other_income = max(_to_float(request.form.get("income_weight_other_income"), 0.25), 0.0)
        income_weight_survivor_cutoff_months = max(
            _to_int(request.form.get("income_weight_survivor_cutoff_months"), 18),
            0,
        )

        db_execute(
            (
                """
                UPDATE shelter_operation_settings
                SET rent_late_day_of_month = %s,
                    rent_score_paid = %s,
                    rent_score_partially_paid = %s,
                    rent_score_paid_late = %s,
                    rent_score_not_paid = %s,
                    rent_score_exempt = %s,
                    rent_carry_forward_enabled = %s,
                    inspection_default_item_status = %s,
                    inspection_item_labels = %s,
                    inspection_scoring_enabled = %s,
                    inspection_lookback_months = %s,
                    inspection_include_current_open_month = %s,
                    inspection_score_passed = %s,
                    inspection_needs_attention_enabled = %s,
                    inspection_score_needs_attention = %s,
                    inspection_score_failed = %s,
                    inspection_passing_threshold = %s,
                    inspection_band_green_min = %s,
                    inspection_band_yellow_min = %s,
                    inspection_band_orange_min = %s,
                    inspection_band_red_max = %s,
                    employment_income_module_enabled = %s,
                    employment_income_graduation_minimum = %s,
                    employment_income_band_green_min = %s,
                    employment_income_band_yellow_min = %s,
                    employment_income_band_orange_min = %s,
                    employment_income_band_red_max = %s,
                    income_weight_employment = %s,
                    income_weight_ssi_ssdi_self = %s,
                    income_weight_child_support = %s,
                    income_weight_alimony = %s,
                    income_weight_other_income = %s,
                    income_weight_survivor_cutoff_months = %s,
                    updated_at = %s
                WHERE LOWER(COALESCE(shelter, '')) = %s
                """
                if g.get("db_kind") == "pg"
                else
                """
                UPDATE shelter_operation_settings
                SET rent_late_day_of_month = ?,
                    rent_score_paid = ?,
                    rent_score_partially_paid = ?,
                    rent_score_paid_late = ?,
                    rent_score_not_paid = ?,
                    rent_score_exempt = ?,
                    rent_carry_forward_enabled = ?,
                    inspection_default_item_status = ?,
                    inspection_item_labels = ?,
                    inspection_scoring_enabled = ?,
                    inspection_lookback_months = ?,
                    inspection_include_current_open_month = ?,
                    inspection_score_passed = ?,
                    inspection_needs_attention_enabled = ?,
                    inspection_score_needs_attention = ?,
                    inspection_score_failed = ?,
                    inspection_passing_threshold = ?,
                    inspection_band_green_min = ?,
                    inspection_band_yellow_min = ?,
                    inspection_band_orange_min = ?,
                    inspection_band_red_max = ?,
                    employment_income_module_enabled = ?,
                    employment_income_graduation_minimum = ?,
                    employment_income_band_green_min = ?,
                    employment_income_band_yellow_min = ?,
                    employment_income_band_orange_min = ?,
                    employment_income_band_red_max = ?,
                    income_weight_employment = ?,
                    income_weight_ssi_ssdi_self = ?,
                    income_weight_child_support = ?,
                    income_weight_alimony = ?,
                    income_weight_other_income = ?,
                    income_weight_survivor_cutoff_months = ?,
                    updated_at = ?
                WHERE LOWER(COALESCE(shelter, '')) = ?
                """
            ),
            (
                late_day,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                carry_forward_enabled if g.get("db_kind") == "pg" else (1 if carry_forward_enabled else 0),
                inspection_default_item_status,
                inspection_item_labels,
                inspection_scoring_enabled if g.get("db_kind") == "pg" else (1 if inspection_scoring_enabled else 0),
                inspection_lookback_months,
                inspection_include_current_open_month if g.get("db_kind") == "pg" else (1 if inspection_include_current_open_month else 0),
                inspection_score_passed,
                inspection_needs_attention_enabled if g.get("db_kind") == "pg" else (1 if inspection_needs_attention_enabled else 0),
                inspection_score_needs_attention,
                inspection_score_failed,
                inspection_passing_threshold,
                inspection_band_green_min,
                inspection_band_yellow_min,
                inspection_band_orange_min,
                inspection_band_red_max,
                employment_income_module_enabled if g.get("db_kind") == "pg" else (1 if employment_income_module_enabled else 0),
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max,
                income_weight_employment,
                income_weight_ssi_ssdi_self,
                income_weight_child_support,
                income_weight_alimony,
                income_weight_other_income,
                income_weight_survivor_cutoff_months,
                now,
                shelter,
            ),
        )

        flash("Operations settings updated.", "ok")
        return redirect(url_for("operations_settings.settings_page"))

    guidance = _employment_income_guidance(shelter)

    return render_template(
        "admin_operations_settings.html",
        shelter=shelter,
        settings=row,
        default_inspection_items=_default_labels_text(),
        employment_guidance=guidance,
        currency=_currency,
    )
