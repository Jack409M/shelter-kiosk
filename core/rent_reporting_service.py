from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import date, datetime
from statistics import mean
from zoneinfo import ZoneInfo

from core.db import db_fetchall
from routes.rent_tracking_parts.settings import _load_settings

CHICAGO_TZ = ZoneInfo("America/Chicago")
SHELTER_ORDER = ("abba", "haven", "gratitude")
SHELTER_LABELS = {
    "abba": "Abba House",
    "haven": "Haven House",
    "gratitude": "Gratitude House",
}
SHELTER_CAPACITY = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
}


@dataclass(slots=True)
class RentFinancialShelterRow:
    shelter: str
    shelter_label: str
    minimal_capacity_rent: float
    historic_capacity_rent: float
    actual_charged_rent: float
    cash_collected: float
    work_credit: float
    total_recovered: float
    vacancy_loss: float
    unrecovered_charged_rent: float
    total_gap_minimal: float
    collection_rate: float | None
    recovery_rate: float | None
    capacity_utilization_rate: float | None
    occupied_days: int
    capacity_days: int
    vacant_days: int
    payment_count: int
    work_credit_count: int
    notes: list[str]


@dataclass(slots=True)
class RentFinancialReport:
    year: int
    generated_at: str
    rows: list[RentFinancialShelterRow]
    totals: RentFinancialShelterRow
    monthly_rows: list[dict]
    definitions: list[dict[str, str]]


def current_report_year() -> int:
    return datetime.now(CHICAGO_TZ).year


def clean_report_year(value: object | None) -> int:
    try:
        year = int(value or current_report_year())
    except Exception:
        return current_report_year()

    if year < 2000 or year > 2100:
        return current_report_year()

    return year


def report_to_dict(report: RentFinancialReport) -> dict:
    return {
        "year": report.year,
        "generated_at": report.generated_at,
        "rows": [asdict(row) for row in report.rows],
        "totals": asdict(report.totals),
        "monthly_rows": report.monthly_rows,
        "definitions": report.definitions,
    }


def _money(value: object | None) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _int(value: object | None) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _shelter_key(value: object | None) -> str:
    text = str(value or "").strip().lower()
    if text.endswith(" house"):
        text = text.removesuffix(" house").strip()
    return text


def _shelter_label(key: str) -> str:
    return SHELTER_LABELS.get(key, key.title() if key else "Unknown")


def _days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def _capacity_days(year: int, shelter: str) -> int:
    return SHELTER_CAPACITY.get(shelter, 0) * _days_in_year(year)


def _settings_float(settings: dict, key: str, fallback: float) -> float:
    value = _money(settings.get(key))
    return value if value > 0 else fallback


def _normal_unit_type(value: object | None) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("-", " ").replace("_", " ")
    if "town" in text:
        return "townhome"
    if "2" in text or "two" in text:
        return "two_bedroom"
    if "1" in text or "one" in text:
        return "one_bedroom"
    return "unknown"


def _gratitude_level5_rate_for_unit(settings: dict, unit_type: str) -> float:
    if unit_type == "one_bedroom":
        return _settings_float(settings, "gh_level_5_one_bedroom_rent", 250.0)
    if unit_type == "townhome":
        return _settings_float(settings, "gh_level_5_townhome_rent", 300.0)
    return _settings_float(settings, "gh_level_5_two_bedroom_rent", 300.0)


def _historical_abba_level4_rate(year: int) -> float:
    rows = db_fetchall(
        """
        SELECT base_monthly_rent, prorated_charge, occupied_days, month_day_count
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE s.rent_year = ?
          AND LOWER(COALESCE(s.shelter, '')) = ?
          AND COALESCE(e.level_snapshot, '') LIKE ?
          AND COALESCE(e.base_monthly_rent, 0) > 0
        """,
        (year, "abba", "%4%"),
    )
    values = [_money(row.get("base_monthly_rent")) for row in rows or [] if _money(row.get("base_monthly_rent")) > 0]
    if values:
        return round(mean(values), 2)

    rows = db_fetchall(
        """
        SELECT monthly_rent
        FROM resident_rent_configs
        WHERE LOWER(COALESCE(shelter, '')) = ?
          AND COALESCE(level_snapshot, '') LIKE ?
          AND COALESCE(monthly_rent, 0) > 0
        """,
        ("abba", "%4%"),
    )
    values = [_money(row.get("monthly_rent")) for row in rows or [] if _money(row.get("monthly_rent")) > 0]
    if values:
        return round(mean(values), 2)

    return 0.0


def _minimal_monthly_rate_for_shelter(year: int, shelter: str, notes: list[str]) -> float:
    if shelter == "haven":
        settings = _load_settings("haven")
        return _settings_float(settings, "hh_rent_amount", 150.0)

    if shelter == "abba":
        rate = _historical_abba_level4_rate(year)
        if rate <= 0:
            notes.append("Abba Level 4 rent was not found in rent sheets or rent configs; minimal capacity rent is shown as 0 until configured.")
        return rate

    return 0.0


def _gratitude_known_unit_rates(year: int, notes: list[str]) -> list[float]:
    settings = _load_settings("gratitude")
    rows = db_fetchall(
        """
        SELECT DISTINCT apartment_number_snapshot, apartment_size_snapshot
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE s.rent_year = ?
          AND LOWER(COALESCE(s.shelter, '')) = ?
          AND COALESCE(e.apartment_number_snapshot, '') <> ''
        """,
        (year, "gratitude"),
    )

    rates: list[float] = []
    seen_units: set[str] = set()
    for row in rows or []:
        unit = str(row.get("apartment_number_snapshot") or "").strip().lower()
        if not unit or unit in seen_units:
            continue
        seen_units.add(unit)
        unit_type = _normal_unit_type(row.get("apartment_size_snapshot"))
        rates.append(_gratitude_level5_rate_for_unit(settings, unit_type))

    capacity = SHELTER_CAPACITY["gratitude"]
    if len(rates) < capacity:
        default_rate = _settings_float(settings, "gh_level_5_two_bedroom_rent", 300.0)
        missing = capacity - len(rates)
        rates.extend([default_rate] * missing)
        notes.append(
            f"Gratitude had {len(seen_units)} known units in rent sheets; {missing} capacity slot(s) used the Level 5 two bedroom default."
        )
    elif len(rates) > capacity:
        rates = rates[:capacity]
        notes.append("Gratitude rent sheets contained more unique units than configured capacity; report capped at configured capacity.")

    return rates


def _minimal_capacity_rent(year: int, shelter: str, notes: list[str]) -> float:
    days = _days_in_year(year)
    if shelter == "gratitude":
        return round(sum(rate * 12 for rate in _gratitude_known_unit_rates(year, notes)), 2)

    monthly_rate = _minimal_monthly_rate_for_shelter(year, shelter, notes)
    return round(monthly_rate * SHELTER_CAPACITY.get(shelter, 0) * 12, 2)


def _actual_charges_by_shelter(year: int) -> dict[str, dict]:
    rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(s.shelter, '')) AS shelter,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS actual_charged_rent,
            COALESCE(SUM(COALESCE(e.occupied_days, 0)), 0) AS occupied_days,
            COUNT(*) AS charged_entry_count
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE s.rent_year = ?
        GROUP BY LOWER(COALESCE(s.shelter, ''))
        """,
        (year,),
    )
    return {_shelter_key(row.get("shelter")): dict(row) for row in rows or []}


def _credits_by_shelter(year: int) -> dict[str, dict]:
    rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(shelter, '')) AS shelter,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS cash_collected,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS work_credit,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN 1 ELSE 0 END), 0) AS payment_count,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN 1 ELSE 0 END), 0) AS work_credit_count
        FROM resident_rent_ledger_entries
        WHERE entry_date >= ?
          AND entry_date <= ?
          AND COALESCE(voided, FALSE) = FALSE
        GROUP BY LOWER(COALESCE(shelter, ''))
        """,
        (f"{year:04d}-01-01", f"{year:04d}-12-31"),
    )
    return {_shelter_key(row.get("shelter")): dict(row) for row in rows or []}


def _monthly_rows(year: int) -> list[dict]:
    charge_rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(s.shelter, '')) AS shelter,
            s.rent_month AS month,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS actual_charged_rent,
            COALESCE(SUM(COALESCE(e.occupied_days, 0)), 0) AS occupied_days
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE s.rent_year = ?
        GROUP BY LOWER(COALESCE(s.shelter, '')), s.rent_month
        """,
        (year,),
    )
    credit_rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(shelter, '')) AS shelter,
            CAST(SUBSTR(entry_date, 6, 2) AS INTEGER) AS month,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS cash_collected,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS work_credit
        FROM resident_rent_ledger_entries
        WHERE entry_date >= ?
          AND entry_date <= ?
          AND COALESCE(voided, FALSE) = FALSE
        GROUP BY LOWER(COALESCE(shelter, '')), CAST(SUBSTR(entry_date, 6, 2) AS INTEGER)
        """,
        (f"{year:04d}-01-01", f"{year:04d}-12-31"),
    )

    charges = {(_shelter_key(row.get("shelter")), _int(row.get("month"))): dict(row) for row in charge_rows or []}
    credits = {(_shelter_key(row.get("shelter")), _int(row.get("month"))): dict(row) for row in credit_rows or []}
    output: list[dict] = []

    for month in range(1, 13):
        for shelter in SHELTER_ORDER:
            charge = charges.get((shelter, month), {})
            credit = credits.get((shelter, month), {})
            actual_charged = _money(charge.get("actual_charged_rent"))
            cash = _money(credit.get("cash_collected"))
            work = _money(credit.get("work_credit"))
            recovered = round(cash + work, 2)
            output.append(
                {
                    "month": month,
                    "month_label": date(year, month, 1).strftime("%B"),
                    "shelter": shelter,
                    "shelter_label": _shelter_label(shelter),
                    "actual_charged_rent": actual_charged,
                    "cash_collected": cash,
                    "work_credit": work,
                    "total_recovered": recovered,
                    "unrecovered_charged_rent": round(actual_charged - recovered, 2),
                    "occupied_days": _int(charge.get("occupied_days")),
                }
            )

    return output


def _historic_capacity_rent(minimal_capacity: float, actual_charged: float, occupied_days: int, capacity_days: int) -> float:
    if occupied_days <= 0 or capacity_days <= 0:
        return minimal_capacity
    daily_actual_average = actual_charged / occupied_days
    return round(daily_actual_average * capacity_days, 2)


def _build_total_row(year: int, rows: list[RentFinancialShelterRow]) -> RentFinancialShelterRow:
    minimal = round(sum(row.minimal_capacity_rent for row in rows), 2)
    historic = round(sum(row.historic_capacity_rent for row in rows), 2)
    charged = round(sum(row.actual_charged_rent for row in rows), 2)
    cash = round(sum(row.cash_collected for row in rows), 2)
    work = round(sum(row.work_credit for row in rows), 2)
    recovered = round(cash + work, 2)
    occupied_days = sum(row.occupied_days for row in rows)
    capacity_days = sum(row.capacity_days for row in rows)
    vacant_days = max(capacity_days - occupied_days, 0)
    return RentFinancialShelterRow(
        shelter="total_program",
        shelter_label="Total Program",
        minimal_capacity_rent=minimal,
        historic_capacity_rent=historic,
        actual_charged_rent=charged,
        cash_collected=cash,
        work_credit=work,
        total_recovered=recovered,
        vacancy_loss=round(sum(row.vacancy_loss for row in rows), 2),
        unrecovered_charged_rent=round(charged - recovered, 2),
        total_gap_minimal=round(minimal - recovered, 2),
        collection_rate=_pct(cash, charged),
        recovery_rate=_pct(recovered, charged),
        capacity_utilization_rate=_pct(charged, minimal),
        occupied_days=occupied_days,
        capacity_days=capacity_days,
        vacant_days=vacant_days,
        payment_count=sum(row.payment_count for row in rows),
        work_credit_count=sum(row.work_credit_count for row in rows),
        notes=[],
    )


def build_rent_financial_performance_report(year: int) -> RentFinancialReport:
    actual_by_shelter = _actual_charges_by_shelter(year)
    credits_by_shelter = _credits_by_shelter(year)
    rows: list[RentFinancialShelterRow] = []

    for shelter in SHELTER_ORDER:
        notes: list[str] = []
        actual = actual_by_shelter.get(shelter, {})
        credits = credits_by_shelter.get(shelter, {})
        capacity_days = _capacity_days(year, shelter)
        minimal_capacity = _minimal_capacity_rent(year, shelter, notes)
        actual_charged = _money(actual.get("actual_charged_rent"))
        occupied_days = min(_int(actual.get("occupied_days")), capacity_days) if capacity_days else 0
        vacant_days = max(capacity_days - occupied_days, 0)
        cash = _money(credits.get("cash_collected"))
        work = _money(credits.get("work_credit"))
        recovered = round(cash + work, 2)
        historic_capacity = _historic_capacity_rent(
            minimal_capacity,
            actual_charged,
            occupied_days,
            capacity_days,
        )
        vacancy_loss = round(max(minimal_capacity - actual_charged, 0), 2)
        rows.append(
            RentFinancialShelterRow(
                shelter=shelter,
                shelter_label=_shelter_label(shelter),
                minimal_capacity_rent=minimal_capacity,
                historic_capacity_rent=historic_capacity,
                actual_charged_rent=actual_charged,
                cash_collected=cash,
                work_credit=work,
                total_recovered=recovered,
                vacancy_loss=vacancy_loss,
                unrecovered_charged_rent=round(actual_charged - recovered, 2),
                total_gap_minimal=round(minimal_capacity - recovered, 2),
                collection_rate=_pct(cash, actual_charged),
                recovery_rate=_pct(recovered, actual_charged),
                capacity_utilization_rate=_pct(actual_charged, minimal_capacity),
                occupied_days=occupied_days,
                capacity_days=capacity_days,
                vacant_days=vacant_days,
                payment_count=_int(credits.get("payment_count")),
                work_credit_count=_int(credits.get("work_credit_count")),
                notes=notes,
            )
        )

    definitions = [
        {"term": "Minimal Capacity Rent", "definition": "Conservative annual capacity floor: Haven base rent, Abba Level 4 rent, and Gratitude Level 5 rent by unit type."},
        {"term": "Historic Capacity Rent", "definition": "Actual average charged rent per occupied day multiplied by full annual capacity days."},
        {"term": "Actual Charged Rent", "definition": "Sum of actual rent sheet charges for occupied residents."},
        {"term": "Cash Collected", "definition": "Non-voided rent ledger payments only."},
        {"term": "Work Credit", "definition": "Non-voided rent ledger credits with source code manual_credit_work_credit."},
        {"term": "Vacancy Loss", "definition": "Minimal capacity rent minus actual charged rent. This is conservative and separates vacancy from nonpayment."},
        {"term": "Unrecovered Charged Rent", "definition": "Actual charged rent minus cash collected and work credit."},
    ]

    return RentFinancialReport(
        year=year,
        generated_at=datetime.now(CHICAGO_TZ).replace(microsecond=0).isoformat(),
        rows=rows,
        totals=_build_total_row(year, rows),
        monthly_rows=_monthly_rows(year),
        definitions=definitions,
    )
