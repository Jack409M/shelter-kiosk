from __future__ import annotations

from .RR_rent_config import load_rr_rent_policy, resolve_rr_base_rent
from .dates import _days_in_month, _month_start_end, _parse_iso_date
from .utils import _bool_value, _float_value, _int_value

ABBA_APARTMENT_NUMBERS = [str(i) for i in range(1, 11)]

GH_APARTMENT_NUMBERS = [
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "20",
    "21",
    "22",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
]

GH_TWO_BEDROOM_NUMBERS = {"2", "5", "8", "11", "26", "29", "32", "35"}
GH_TOWNHOME_NUMBERS = {"13", "14", "15", "16", "37", "38", "39", "40"}


def _rent_band_for_score(score: float | int | None) -> dict:
    numeric_score = float(score or 0)

    if numeric_score >= 95:
        return {
            "band_key": "green",
            "band_label": "Green",
            "card_style": "background:#eef8f0; border:1px solid #9bc8a6;",
            "value_style": "color:#1f6b33; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#dcefe1; border:1px solid #9bc8a6; color:#1f6b33; font-weight:700;",
        }

    if numeric_score >= 79:
        return {
            "band_key": "yellow",
            "band_label": "Yellow",
            "card_style": "background:#fff8df; border:1px solid #e0cd7a;",
            "value_style": "color:#7a6500; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#fff1b8; border:1px solid #e0cd7a; color:#7a6500; font-weight:700;",
        }

    if numeric_score >= 62:
        return {
            "band_key": "orange",
            "band_label": "Orange",
            "card_style": "background:#fff0e4; border:1px solid #e2b27d;",
            "value_style": "color:#9a4f00; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd8b0; border:1px solid #e2b27d; color:#9a4f00; font-weight:700;",
        }

    return {
        "band_key": "red",
        "band_label": "Red",
        "card_style": "background:#fff0f0; border:1px solid #e2a0a0;",
        "value_style": "color:#9a1f1f; font-weight:700;",
        "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd6d6; border:1px solid #e2a0a0; color:#9a1f1f; font-weight:700;",
    }


def _score_for_status(settings: dict, status: str) -> int:
    mapping = {
        "Paid": int(settings.get("rent_score_paid", 100) or 100),
        "Partially Paid": int(settings.get("rent_score_partially_paid", 75) or 75),
        "Paid Late": int(settings.get("rent_score_paid_late", 75) or 75),
        "Not Paid": int(settings.get("rent_score_not_paid", 0) or 0),
        "Exempt": int(settings.get("rent_score_exempt", 100) or 100),
    }
    return mapping.get(status, 0)


def _derive_status(
    total_due: float,
    amount_paid: float,
    paid_date: str | None,
    is_exempt: bool,
    late_fee_charge: float,
) -> str:
    if is_exempt:
        return "Exempt"
    if total_due <= 0:
        return "Paid"
    if amount_paid <= 0:
        return "Not Paid"
    if amount_paid < total_due:
        return "Partially Paid"
    if late_fee_charge > 0:
        return "Paid Late"
    if paid_date:
        return "Paid"
    return "Paid"


def _apartment_options_for_shelter(shelter: str) -> list[str]:
    shelter_key = (shelter or "").strip().lower()
    if shelter_key == "abba":
        return ABBA_APARTMENT_NUMBERS
    if shelter_key == "gratitude":
        return GH_APARTMENT_NUMBERS
    return []


def _normalize_apartment_number(shelter: str, apartment_number: str | None) -> str | None:
    shelter_key = (shelter or "").strip().lower()
    raw = (apartment_number or "").strip()
    if not raw:
        return None

    if shelter_key == "haven":
        return None

    allowed = set(_apartment_options_for_shelter(shelter_key))
    return raw if raw in allowed else None


def _derive_apartment_size_from_assignment(
    shelter: str, apartment_number: str | None
) -> str | None:
    shelter_key = (shelter or "").strip().lower()
    apartment_value = _normalize_apartment_number(shelter_key, apartment_number)

    if shelter_key == "haven":
        return "Bed"
    if shelter_key == "abba":
        return "One Bedroom" if apartment_value else None
    if shelter_key == "gratitude":
        if not apartment_value:
            return None
        if apartment_value in GH_TWO_BEDROOM_NUMBERS:
            return "Two Bedroom"
        if apartment_value in GH_TOWNHOME_NUMBERS:
            return "Town Home"
        return "One Bedroom"
    return None


def _derive_base_monthly_rent(settings: dict, shelter: str, config: dict) -> tuple[float, str]:
    if _bool_value(config.get("is_exempt")):
        return 0.0, "Resident marked exempt"

    level = str(config.get("level_snapshot") or "").strip()
    apartment_number = config.get("apartment_number_snapshot")
    apartment_size = (
        _derive_apartment_size_from_assignment(shelter, apartment_number)
        or str(config.get("apartment_size_snapshot") or "").strip()
    )
    manual_rent = _float_value(config.get("monthly_rent"))

    rr_base_rent, rr_note = resolve_rr_base_rent(
        shelter=shelter,
        program_level=level,
        unit_type=apartment_size,
    )

    if level == "8" and manual_rent > 0:
        if rr_base_rent > 0 and manual_rent < rr_base_rent:
            return rr_base_rent, f"{rr_note}; Level 8 adjustment below minimum ignored"
        return manual_rent, "Level 8 adjusted rent from resident rent setup"

    return rr_base_rent, rr_note


def _calculate_proration(
    base_monthly_rent: float,
    config: dict,
    enrollment: dict | None,
    rent_year: int,
    rent_month: int,
) -> dict:
    month_start, month_end = _month_start_end(rent_year, rent_month)
    month_day_count = _days_in_month(rent_year, rent_month)

    occupancy_start = month_start
    occupancy_end = month_end
    notes: list[str] = []

    enrollment_entry = _parse_iso_date(enrollment.get("entry_date") if enrollment else None)
    enrollment_exit = _parse_iso_date(enrollment.get("exit_date") if enrollment else None)
    config_start = _parse_iso_date(config.get("effective_start_date"))

    if enrollment_entry and enrollment_entry > occupancy_start:
        occupancy_start = enrollment_entry
        notes.append("Move in proration applied from program entry date")
    elif (
        config_start
        and config_start.year == rent_year
        and config_start.month == rent_month
        and config_start > occupancy_start
    ):
        occupancy_start = config_start
        notes.append("Proration applied from rent setup effective start date")

    if enrollment_exit and enrollment_exit < occupancy_end:
        occupancy_end = enrollment_exit
        notes.append("Move out proration applied through program exit date")

    if occupancy_end < occupancy_start:
        occupied_days = 0
        prorated_charge = 0.0
    else:
        occupied_days = (occupancy_end - occupancy_start).days + 1
        prorated_charge = round((base_monthly_rent * occupied_days) / month_day_count, 2)

    if occupied_days == month_day_count and base_monthly_rent > 0:
        notes.append("Full month charge")
    elif occupied_days == 0:
        notes.append("No occupied days in this month")

    return {
        "occupancy_start_date": occupancy_start.isoformat() if occupied_days > 0 else "",
        "occupancy_end_date": occupancy_end.isoformat() if occupied_days > 0 else "",
        "occupied_days": occupied_days,
        "month_day_count": month_day_count,
        "prorated_charge": prorated_charge,
        "notes": notes,
    }


def _late_start_day(settings: dict, shelter: str) -> int:
    policy = load_rr_rent_policy(shelter)
    return _int_value(policy.get("rent_late_day"), 6)


def _late_fee_per_day(settings: dict, shelter: str) -> float:
    policy = load_rr_rent_policy(shelter)
    return _float_value(policy.get("rent_late_fee_per_day"))


def _calculate_late_fee(
    settings: dict,
    shelter: str,
    rent_year: int,
    rent_month: int,
    subtotal_due: float,
    paid_date: str | None,
    approved_late_arrangement: bool,
    is_exempt: bool,
    today_date,
) -> tuple[float, str]:
    late_fee_info = _calculate_late_fee_info(
        settings=settings,
        shelter=shelter,
        rent_year=rent_year,
        rent_month=rent_month,
        subtotal_due=subtotal_due,
        paid_date=paid_date,
        approved_late_arrangement=approved_late_arrangement,
        is_exempt=is_exempt,
        today_date=today_date,
    )
    return late_fee_info["amount"], late_fee_info["note"]


def _calculate_late_fee_info(
    settings: dict,
    shelter: str,
    rent_year: int,
    rent_month: int,
    subtotal_due: float,
    paid_date: str | None,
    approved_late_arrangement: bool,
    is_exempt: bool,
    today_date,
) -> dict:
    if is_exempt or approved_late_arrangement or subtotal_due <= 0:
        if approved_late_arrangement:
            return {
                "amount": 0.0,
                "note": "Late fee waived by approved arrangement",
                "late_start_date": None,
                "posting_date": None,
                "late_days": 0,
                "daily_rate": 0.0,
                "is_postable": False,
            }
        return {
            "amount": 0.0,
            "note": "",
            "late_start_date": None,
            "posting_date": None,
            "late_days": 0,
            "daily_rate": 0.0,
            "is_postable": False,
        }

    _month_start, month_end = _month_start_end(rent_year, rent_month)
    late_start_day = _late_start_day(settings, shelter)
    fee_per_day = _late_fee_per_day(settings, shelter)

    if fee_per_day <= 0:
        return {
            "amount": 0.0,
            "note": "",
            "late_start_date": None,
            "posting_date": None,
            "late_days": 0,
            "daily_rate": 0.0,
            "is_postable": False,
        }

    if late_start_day < 1:
        late_start_day = 1
    if late_start_day > month_end.day:
        late_start_day = month_end.day

    late_start_date = month_end.replace(day=late_start_day)
    parsed_paid_date = _parse_iso_date(paid_date)

    if parsed_paid_date:
        window_end = min(parsed_paid_date, month_end)
    else:
        if today_date.year == rent_year and today_date.month == rent_month:
            window_end = min(today_date, month_end)
        elif (today_date.year, today_date.month) > (rent_year, rent_month):
            window_end = month_end
        else:
            return {
                "amount": 0.0,
                "note": "",
                "late_start_date": late_start_date.isoformat(),
                "posting_date": None,
                "late_days": 0,
                "daily_rate": fee_per_day,
                "is_postable": False,
            }

    if window_end < late_start_date:
        return {
            "amount": 0.0,
            "note": "",
            "late_start_date": late_start_date.isoformat(),
            "posting_date": None,
            "late_days": 0,
            "daily_rate": fee_per_day,
            "is_postable": False,
        }

    late_days = (window_end - late_start_date).days + 1
    if late_days <= 0:
        return {
            "amount": 0.0,
            "note": "",
            "late_start_date": late_start_date.isoformat(),
            "posting_date": None,
            "late_days": 0,
            "daily_rate": fee_per_day,
            "is_postable": False,
        }

    amount = round(late_days * fee_per_day, 2)

    return {
        "amount": amount,
        "note": f"Late fee applied for {late_days} day(s)",
        "late_start_date": late_start_date.isoformat(),
        "posting_date": late_start_date.isoformat(),
        "late_days": late_days,
        "daily_rate": fee_per_day,
        "is_postable": amount > 0,
    }
