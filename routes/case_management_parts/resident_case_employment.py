from __future__ import annotations


def load_employment_income_defaults() -> dict:
    return {
        "employment_income_module_enabled": True,
        "employment_income_graduation_minimum": 1200.0,
        "employment_income_band_green_min": 1200.0,
        "employment_income_band_yellow_min": 1000.0,
        "employment_income_band_orange_min": 700.0,
        "employment_income_band_red_max": 699.99,
    }


def resolve_monthly_income_for_display(enrollment_context: dict) -> object:
    intake_income_support = enrollment_context.get("intake_income_support") or {}
    monthly_income_for_display = intake_income_support.get("weighted_stable_income")

    if monthly_income_for_display in (None, ""):
        monthly_income_for_display = intake_income_support.get("total_cash_support")

    if monthly_income_for_display in (None, ""):
        intake_assessment = enrollment_context.get("intake_assessment") or {}
        monthly_income_for_display = intake_assessment.get("income_at_entry")

    return monthly_income_for_display


def build_employment_income_snapshot(monthly_income, settings: dict) -> dict:
    graduation_minimum = float(settings.get("employment_income_graduation_minimum") or 1200.0)
    green_min = float(settings.get("employment_income_band_green_min") or graduation_minimum)
    yellow_min = float(settings.get("employment_income_band_yellow_min") or 1000.0)
    orange_min = float(settings.get("employment_income_band_orange_min") or 700.0)

    income_value = None
    if monthly_income not in (None, ""):
        try:
            income_value = float(monthly_income)
        except Exception:
            income_value = None

    if income_value is None or graduation_minimum <= 0:
        readiness_percent = None
    else:
        readiness_percent = round(min((income_value / graduation_minimum) * 100.0, 100.0))

    if income_value is None:
        band_key = "neutral"
        pill_style = "display:inline-flex; align-items:center; justify-content:center; min-width:48px; padding:4px 10px; border-radius:999px; background:#eef2f6; border:1px solid #c7d2de; color:#46607a; font-weight:700; font-size:12px; line-height:1;"
    elif income_value >= green_min:
        band_key = "green"
        pill_style = "display:inline-flex; align-items:center; justify-content:center; min-width:48px; padding:4px 10px; border-radius:999px; background:#dfeee5; border:1px solid #8fbea0; color:#1d5f33; font-weight:700; font-size:12px; line-height:1;"
    elif income_value >= yellow_min:
        band_key = "yellow"
        pill_style = "display:inline-flex; align-items:center; justify-content:center; min-width:48px; padding:4px 10px; border-radius:999px; background:#fff3c7; border:1px solid #ddc56d; color:#7a6500; font-weight:700; font-size:12px; line-height:1;"
    elif income_value >= orange_min:
        band_key = "orange"
        pill_style = "display:inline-flex; align-items:center; justify-content:center; min-width:48px; padding:4px 10px; border-radius:999px; background:#ffe0bf; border:1px solid #d9a06a; color:#98510a; font-weight:700; font-size:12px; line-height:1;"
    else:
        band_key = "red"
        pill_style = "display:inline-flex; align-items:center; justify-content:center; min-width:48px; padding:4px 10px; border-radius:999px; background:#f6dada; border:1px solid #d38b8b; color:#8f1f1f; font-weight:700; font-size:12px; line-height:1;"

    return {
        "module_enabled": bool(settings.get("employment_income_module_enabled", True)),
        "graduation_minimum": graduation_minimum,
        "income_value": income_value,
        "readiness_percent": readiness_percent,
        "readiness_percent_display": f"{readiness_percent}%" if readiness_percent is not None else "—",
        "meets_goal": bool(income_value is not None and income_value >= graduation_minimum),
        "band_key": band_key,
        "pill_style": pill_style,
    }


def resolve_employment_status_snapshot(
    recovery_snapshot: dict | None,
    intake_assessment: dict | None,
) -> str:
    rs = recovery_snapshot or {}
    ia = intake_assessment or {}

    recovery_employment_status = str(
        rs.get("employment_status_current")
        or rs.get("employment_status")
        or ""
    ).strip().lower()

    if recovery_employment_status in {"employed", "unemployed"}:
        return recovery_employment_status

    intake_employment_status = str(ia.get("employment_status_at_entry") or "").strip().lower()
    intake_to_profile_map = {
        "employed_full_time": "employed",
        "employed_part_time": "employed",
        "unemployed": "unemployed",
        "disabled": "unemployed",
        "unknown": "",
    }
    return intake_to_profile_map.get(intake_employment_status, "")


def build_employment_stability_snapshot(
    recovery_snapshot: dict | None,
    employment_status_snapshot: str = "",
) -> dict:
    rs = recovery_snapshot or {}

    employment_status = str(employment_status_snapshot or "").strip().lower()
    current_job_days = rs.get("current_job_days")
    continuous_days = rs.get("continuous_employment_days")
    gap_days = rs.get("employment_gap_days")
    upward_value = rs.get("upward_job_change")

    currently_employed = employment_status == "employed"
    upward_protected = bool(currently_employed and upward_value is True)

    current_job_days_min = 90
    continuous_days_min = 180

    passes = bool(
        currently_employed
        and (
            (isinstance(current_job_days, int) and current_job_days >= current_job_days_min)
            or (isinstance(continuous_days, int) and continuous_days >= continuous_days_min)
        )
    )

    if not currently_employed:
        label = "Not Employed"
        card_style = "background:#eef2f6; border:1px solid #c7d2de;"
    elif passes:
        label = "Pass"
        card_style = "background:#dfeee5; border:1px solid #8fbea0;"
    else:
        label = "Below Threshold"
        card_style = "background:#fff3c7; border:1px solid #ddc56d;"

    return {
        "label": label,
        "card_style": card_style,
        "current_job_days_min": current_job_days_min,
        "continuous_days_min": continuous_days_min,
        "current_job_days": current_job_days,
        "continuous_days": continuous_days,
        "gap_days": gap_days,
        "upward_protected": upward_protected,
        "passes": passes,
    }
