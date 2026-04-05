from __future__ import annotations

from statistics import median

from core.db import db_fetchall


def _average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 2)


def _employment_income_guidance(shelter: str, placeholder: str) -> dict:
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
        WHERE LOWER(COALESCE(pe.shelter, '')) = {placeholder}
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
