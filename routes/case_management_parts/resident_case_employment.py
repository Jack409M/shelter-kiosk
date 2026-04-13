from __future__ import annotations


def _to_float_or_none(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int_or_none(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _neutral_pill_style() -> str:
    return (
        "display:inline-flex; align-items:center; justify-content:center; "
        "min-width:48px; padding:4px 10px; border-radius:999px; "
        "background:#eef2f6; border:1px solid #c7d2de; color:#46607a; "
        "font-weight:700; font-size:12px; line-height:1;"
    )


def _green_pill_style() -> str:
    return (
        "display:inline-flex; align-items:center; justify-content:center; "
        "min-width:48px; padding:4px 10px; border-radius:999px; "
        "background:#dfeee5; border:1px solid #8fbea0; color:#1d5f33; "
        "font-weight:700; font-size:12px; line-height:1;"
    )


def _yellow_pill_style() -> str:
    return (
        "display:inline-flex; align-items:center; justify-content:center; "
        "min-width:48px; padding:4px 10px; border-radius:999px; "
        "background:#fff3c7; border:1px solid #ddc56d; color:#7a6500; "
        "font-weight:700; font-size:12px; line-height:1;"
    )


def _orange_pill_style() -> str:
    return (
        "display:inline-flex; align-items:center; justify-content:center; "
        "min-width:48px; padding:4px 10px; border-radius:999px; "
        "background:#ffe0bf; border:1px solid #d9a06a; color:#98510a; "
        "font-weight:700; font-size:12px; line-height:1;"
    )


def _red_pill_style() -> str:
    return (
        "display:inline-flex; align-items:center; justify-content:center; "
        "min-width:48px; padding:4px 10px; border-radius:999px; "
        "background:#f6dada; border:1px solid #d38b8b; color:#8f1f1f; "
        "font-weight:700; font-size:12px; line-height:1;"
    )


def _resolve_income_thresholds(settings: dict) -> tuple[float, float, float, float]:
    graduation_minimum = _to_float_or_none(
        settings.get("employment_income_graduation_minimum")
    )
    if graduation_minimum is None or graduation_minimum <= 0:
        graduation_minimum = 1200.0

    green_min = _to_float_or_none(settings.get("employment_income_band_green_min"))
    if green_min is None:
        green_min = graduation_minimum

    yellow_min = _to_float_or_none(settings.get("employment_income_band_yellow_min"))
    if yellow_min is None:
        yellow_min = 1000.0

    orange_min = _to_float_or_none(settings.get("employment_income_band_orange_min"))
    if orange_min is None:
        orange_min = 700.0

    return graduation_minimum, green_min, yellow_min, orange_min


def _resolve_income_band(
    income_value: float | None,
    *,
    green_min: float,
    yellow_min: float,
    orange_min: float,
) -> tuple[str, str]:
    if income_value is None:
        return "neutral", _neutral_pill_style()

    if income_value >= green_min:
        return "green", _green_pill_style()

    if income_value >= yellow_min:
        return "yellow", _yellow_pill_style()

    if income_value >= orange_min:
        return "orange", _orange_pill_style()

    return "red", _red_pill_style()


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
    graduation_minimum, green_min, yellow_min, orange_min = _resolve_income_thresholds(
        settings
    )
    income_value = _to_float_or_none(monthly_income)

    if income_value is None:
        readiness_percent = None
    else:
        readiness_percent = round(min((income_value / graduation_minimum) * 100.0, 100.0))

    band_key, pill_style = _resolve_income_band(
        income_value,
        green_min=green_min,
        yellow_min=yellow_min,
        orange_min=orange_min,
    )

    return {
        "module_enabled": _to_bool(settings.get("employment_income_module_enabled", True)),
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
    current_job_days = _to_int_or_none(rs.get("current_job_days"))
    continuous_days = _to_int_or_none(rs.get("continuous_employment_days"))
    gap_days = _to_int_or_none(rs.get("employment_gap_days"))
    upward_value = rs.get("upward_job_change")

    currently_employed = employment_status == "employed"
    upward_protected = bool(currently_employed and _to_bool(upward_value))

    current_job_days_min = 90
    continuous_days_min = 180

    passes = bool(
        currently_employed
        and (
            (current_job_days is not None and current_job_days >= current_job_days_min)
            or (continuous_days is not None and continuous_days >= continuous_days_min)
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
