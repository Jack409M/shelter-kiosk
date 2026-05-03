from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import date, datetime
from statistics import mean
from zoneinfo import ZoneInfo

from core.db import db_fetchall
from core.shelter_capacity_service import load_shelter_capacities
from routes.rent_tracking_parts.settings import _load_settings

CHICAGO_TZ = ZoneInfo("America/Chicago")
SHELTER_ORDER = ("abba", "haven", "gratitude")
SHELTER_LABELS = {
    "abba": "Abba House",
    "haven": "Haven House",
    "gratitude": "Gratitude House",
}


@dataclass(slots=True)
class RentReportPeriod:
    start_date: date
    end_date: date
    year: int
    label: str


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
    period_start: str
    period_end: str
    period_label: str
    generated_at: str
    rows: list[RentFinancialShelterRow]
    totals: RentFinancialShelterRow
    monthly_rows: list[dict]
    twelve_month_trend: list[dict]
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


def _parse_iso_date(value: object | None) -> date | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return date.fromisoformat(text)
    except Exception:
        return None


def _period_label(start: date, end: date) -> str:
    if start == date(start.year, 1, 1) and end == date(start.year, 12, 31):
        return f"Year {start.year}"
    if start.year == end.year:
        return f"{start.strftime('%b %d')} to {end.strftime('%b %d, %Y')}"
    return f"{start.strftime('%b %d, %Y')} to {end.strftime('%b %d, %Y')}"


def clean_report_period(
    *,
    start_date_value: object | None = None,
    end_date_value: object | None = None,
    year_value: object | None = None,
) -> RentReportPeriod:
    year = clean_report_year(year_value)
    start = _parse_iso_date(start_date_value)
    end = _parse_iso_date(end_date_value)

    if start is None and end is None:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
    elif start is None and end is not None:
        start = date(end.year, 1, 1)
    elif start is not None and end is None:
        end = date(start.year, 12, 31)

    assert start is not None
    assert end is not None

    if start > end:
        start, end = end, start

    if start.year < 2000 or end.year > 2100:
        fallback_year = current_report_year()
        start = date(fallback_year, 1, 1)
        end = date(fallback_year, 12, 31)

    return RentReportPeriod(
        start_date=start,
        end_date=end,
        year=start.year,
        label=_period_label(start, end),
    )


def report_to_dict(report: RentFinancialReport) -> dict:
    return {
        "year": report.year,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "period_label": report.period_label,
        "generated_at": report.generated_at,
        "rows": [asdict(row) for row in report.rows],
        "totals": asdict(report.totals),
        "monthly_rows": report.monthly_rows,
        "twelve_month_trend": report.twelve_month_trend,
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


def _month_key(year: int, month: int) -> int:
    return (year * 100) + month


def _period_month_keys(period: RentReportPeriod) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    current_year = period.start_date.year
    current_month = period.start_date.month
    while (current_year, current_month) <= (period.end_date.year, period.end_date.month):
        months.append((current_year, current_month))
        current_month += 1
        if current_month == 13:
            current_month = 1
            current_year += 1
    return months


def _period_day_count(period: RentReportPeriod) -> int:
    return (period.end_date - period.start_date).days + 1


def _capacity_days(period: RentReportPeriod, shelter: str, capacities: dict[str, int]) -> int:
    return int(capacities.get(shelter, 0) or 0) * _period_day_count(period)


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


def _period_bounds(period: RentReportPeriod) -> tuple[int, int, str, str]:
    month_start = _month_key(period.start_date.year, period.start_date.month)
    month_end = _month_key(period.end_date.year, period.end_date.month)
    return month_start, month_end, period.start_date.isoformat(), period.end_date.isoformat()


def _historical_abba_level4_rate(period: RentReportPeriod) -> float:
    month_start, month_end, _, _ = _period_bounds(period)
    rows = db_fetchall(
        """
        SELECT base_monthly_rent, prorated_charge, occupied_days, month_day_count
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE ((s.rent_year * 100) + s.rent_month) >= ?
          AND ((s.rent_year * 100) + s.rent_month) <= ?
          AND LOWER(COALESCE(s.shelter, '')) = ?
          AND COALESCE(e.level_snapshot, '') LIKE ?
          AND COALESCE(e.base_monthly_rent, 0) > 0
        """,
        (month_start, month_end, "abba", "%4%"),
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


def _minimal_monthly_rate_for_shelter(period: RentReportPeriod, shelter: str, notes: list[str]) -> float:
    if shelter == "haven":
        settings = _load_settings("haven")
        return _settings_float(settings, "hh_rent_amount", 150.0)

    if shelter == "abba":
        rate = _historical_abba_level4_rate(period)
        if rate <= 0:
            notes.append("Abba Level 4 rent was not found in rent sheets or rent configs; minimal capacity rent is shown as 0 until configured.")
        return rate

    return 0.0


def _gratitude_known_unit_rates(period: RentReportPeriod, notes: list[str], capacity: int) -> list[float]:
    settings = _load_settings("gratitude")
    month_start, month_end, _, _ = _period_bounds(period)
    rows = db_fetchall(
        """
        SELECT DISTINCT apartment_number_snapshot, apartment_size_snapshot
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE ((s.rent_year * 100) + s.rent_month) >= ?
          AND ((s.rent_year * 100) + s.rent_month) <= ?
          AND LOWER(COALESCE(s.shelter, '')) = ?
          AND COALESCE(e.apartment_number_snapshot, '') <> ''
        """,
        (month_start, month_end, "gratitude"),
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


def _minimal_capacity_rent(period: RentReportPeriod, shelter: str, notes: list[str], capacities: dict[str, int]) -> float:
    capacity = int(capacities.get(shelter, 0) or 0)
    month_count = len(_period_month_keys(period))

    if shelter == "gratitude":
        return round(sum(rate * month_count for rate in _gratitude_known_unit_rates(period, notes, capacity)), 2)

    monthly_rate = _minimal_monthly_rate_for_shelter(period, shelter, notes)
    return round(monthly_rate * capacity * month_count, 2)


def _actual_charges_by_shelter(period: RentReportPeriod) -> dict[str, dict]:
    month_start, month_end, _, _ = _period_bounds(period)
    rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(s.shelter, '')) AS shelter,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS actual_charged_rent,
            COALESCE(SUM(COALESCE(e.occupied_days, 0)), 0) AS occupied_days,
            COUNT(*) AS charged_entry_count
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE ((s.rent_year * 100) + s.rent_month) >= ?
          AND ((s.rent_year * 100) + s.rent_month) <= ?
        GROUP BY LOWER(COALESCE(s.shelter, ''))
        """,
        (month_start, month_end),
    )
    return {_shelter_key(row.get("shelter")): dict(row) for row in rows or []}


def _credits_by_shelter(period: RentReportPeriod) -> dict[str, dict]:
    _, _, start_text, end_text = _period_bounds(period)
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
        (start_text, end_text),
    )
    return {_shelter_key(row.get("shelter")): dict(row) for row in rows or []}


def _month_sequence_ending(year: int, month: int, count: int = 12) -> list[tuple[int, int]]:
    values: list[tuple[int, int]] = []
    y = year
    m = month
    for _ in range(count):
        values.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(values))


def _rolling_twelve_month_trend(period: RentReportPeriod) -> list[dict]:
    months = _month_sequence_ending(period.end_date.year, period.end_date.month, 12)
    first_year, first_month = months[0]
    last_year, last_month = months[-1]
    start_date = f"{first_year:04d}-{first_month:02d}-01"
    end_day = calendar.monthrange(last_year, last_month)[1]
    end_date = f"{last_year:04d}-{last_month:02d}-{end_day:02d}"

    charge_rows = db_fetchall(
        """
        SELECT
            s.rent_year AS year,
            s.rent_month AS month,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS actual_charged_rent
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE (s.rent_year > ? OR (s.rent_year = ? AND s.rent_month >= ?))
          AND (s.rent_year < ? OR (s.rent_year = ? AND s.rent_month <= ?))
        GROUP BY s.rent_year, s.rent_month
        """,
        (first_year, first_year, first_month, last_year, last_year, last_month),
    )
    credit_rows = db_fetchall(
        """
        SELECT
            CAST(SUBSTR(entry_date, 1, 4) AS INTEGER) AS year,
            CAST(SUBSTR(entry_date, 6, 2) AS INTEGER) AS month,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS cash_collected,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS work_credit
        FROM resident_rent_ledger_entries
        WHERE entry_date >= ?
          AND entry_date <= ?
          AND COALESCE(voided, FALSE) = FALSE
        GROUP BY CAST(SUBSTR(entry_date, 1, 4) AS INTEGER), CAST(SUBSTR(entry_date, 6, 2) AS INTEGER)
        """,
        (start_date, end_date),
    )
    charges = {(_int(row.get("year")), _int(row.get("month"))): dict(row) for row in charge_rows or []}
    credits = {(_int(row.get("year")), _int(row.get("month"))): dict(row) for row in credit_rows or []}
    output: list[dict] = []

    for month_year, month_number in months:
        charge = charges.get((month_year, month_number), {})
        credit = credits.get((month_year, month_number), {})
        actual_charged = _money(charge.get("actual_charged_rent"))
        cash = _money(credit.get("cash_collected"))
        work = _money(credit.get("work_credit"))
        total_applied = round(cash + work, 2)
        unpaid = round(actual_charged - total_applied, 2)
        output.append(
            {
                "year": month_year,
                "month": month_number,
                "label": date(month_year, month_number, 1).strftime("%b %Y"),
                "short_label": date(month_year, month_number, 1).strftime("%b"),
                "actual_charged_rent": actual_charged,
                "cash_collected": cash,
                "work_credit": work,
                "total_recovered": total_applied,
                "unrecovered_charged_rent": unpaid,
            }
        )

    return output


def _monthly_rows(period: RentReportPeriod) -> list[dict]:
    month_start, month_end, start_text, end_text = _period_bounds(period)
    charge_rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(s.shelter, '')) AS shelter,
            s.rent_year AS year,
            s.rent_month AS month,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS actual_charged_rent,
            COALESCE(SUM(COALESCE(e.occupied_days, 0)), 0) AS occupied_days
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE ((s.rent_year * 100) + s.rent_month) >= ?
          AND ((s.rent_year * 100) + s.rent_month) <= ?
        GROUP BY LOWER(COALESCE(s.shelter, '')), s.rent_year, s.rent_month
        """,
        (month_start, month_end),
    )
    credit_rows = db_fetchall(
        """
        SELECT
            LOWER(COALESCE(shelter, '')) AS shelter,
            CAST(SUBSTR(entry_date, 1, 4) AS INTEGER) AS year,
            CAST(SUBSTR(entry_date, 6, 2) AS INTEGER) AS month,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS cash_collected,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS work_credit
        FROM resident_rent_ledger_entries
        WHERE entry_date >= ?
          AND entry_date <= ?
          AND COALESCE(voided, FALSE) = FALSE
        GROUP BY LOWER(COALESCE(shelter, '')), CAST(SUBSTR(entry_date, 1, 4) AS INTEGER), CAST(SUBSTR(entry_date, 6, 2) AS INTEGER)
        """,
        (start_text, end_text),
    )

    charges = {(_shelter_key(row.get("shelter")), _int(row.get("year")), _int(row.get("month"))): dict(row) for row in charge_rows or []}
    credits = {(_shelter_key(row.get("shelter")), _int(row.get("year")), _int(row.get("month"))): dict(row) for row in credit_rows or []}
    output: list[dict] = []

    for month_year, month_number in _period_month_keys(period):
        for shelter in SHELTER_ORDER:
            charge = charges.get((shelter, month_year, month_number), {})
            credit = credits.get((shelter, month_year, month_number), {})
            actual_charged = _money(charge.get("actual_charged_rent"))
            cash = _money(credit.get("cash_collected"))
            work = _money(credit.get("work_credit"))
            total_applied = round(cash + work, 2)
            output.append(
                {
                    "year": month_year,
                    "month": month_number,
                    "month_label": date(month_year, month_number, 1).strftime("%B %Y"),
                    "shelter": shelter,
                    "shelter_label": _shelter_label(shelter),
                    "actual_charged_rent": actual_charged,
                    "cash_collected": cash,
                    "work_credit": work,
                    "total_recovered": total_applied,
                    "unrecovered_charged_rent": round(actual_charged - total_applied, 2),
                    "occupied_days": _int(charge.get("occupied_days")),
                }
            )

    return output


def _historic_capacity_rent(minimal_capacity: float, actual_charged: float, occupied_days: int, capacity_days: int) -> float:
    if occupied_days <= 0 or capacity_days <= 0:
        return minimal_capacity
    daily_actual_average = actual_charged / occupied_days
    return round(daily_actual_average * capacity_days, 2)


def _build_total_row(rows: list[RentFinancialShelterRow]) -> RentFinancialShelterRow:
    minimal = round(sum(row.minimal_capacity_rent for row in rows), 2)
    historic = round(sum(row.historic_capacity_rent for row in rows), 2)
    charged = round(sum(row.actual_charged_rent for row in rows), 2)
    cash = round(sum(row.cash_collected for row in rows), 2)
    work = round(sum(row.work_credit for row in rows), 2)
    total_applied = round(cash + work, 2)
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
        total_recovered=total_applied,
        vacancy_loss=round(sum(row.vacancy_loss for row in rows), 2),
        unrecovered_charged_rent=round(charged - total_applied, 2),
        total_gap_minimal=round(minimal - total_applied, 2),
        collection_rate=_pct(cash, charged),
        recovery_rate=_pct(total_applied, charged),
        capacity_utilization_rate=_pct(charged, minimal),
        occupied_days=occupied_days,
        capacity_days=capacity_days,
        vacant_days=vacant_days,
        payment_count=sum(row.payment_count for row in rows),
        work_credit_count=sum(row.work_credit_count for row in rows),
        notes=[],
    )


def build_rent_financial_performance_report(year: int | None = None, *, period: RentReportPeriod | None = None) -> RentFinancialReport:
    if period is None:
        period = clean_report_period(year_value=year)

    capacities = load_shelter_capacities()
    actual_by_shelter = _actual_charges_by_shelter(period)
    credits_by_shelter = _credits_by_shelter(period)
    rows: list[RentFinancialShelterRow] = []

    for shelter in SHELTER_ORDER:
        notes: list[str] = []
        actual = actual_by_shelter.get(shelter, {})
        credits = credits_by_shelter.get(shelter, {})
        capacity_days = _capacity_days(period, shelter, capacities)
        minimal_capacity = _minimal_capacity_rent(period, shelter, notes, capacities)
        actual_charged = _money(actual.get("actual_charged_rent"))
        occupied_days = min(_int(actual.get("occupied_days")), capacity_days) if capacity_days else 0
        vacant_days = max(capacity_days - occupied_days, 0)
        cash = _money(credits.get("cash_collected"))
        work = _money(credits.get("work_credit"))
        total_applied = round(cash + work, 2)
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
                total_recovered=total_applied,
                vacancy_loss=vacancy_loss,
                unrecovered_charged_rent=round(actual_charged - total_applied, 2),
                total_gap_minimal=round(minimal_capacity - total_applied, 2),
                collection_rate=_pct(cash, actual_charged),
                recovery_rate=_pct(total_applied, actual_charged),
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
        {"term": "Minimal Capacity Rent", "definition": "Conservative rent capacity floor for the selected period using configured shelter capacity, Haven base rent, Abba Level 4 rent, and Gratitude Level 5 rent by unit type."},
        {"term": "Historic Capacity Rent", "definition": "Actual average charged rent per occupied day multiplied by selected period capacity days."},
        {"term": "Actual Charged Rent", "definition": "Sum of actual rent sheet charges for occupied residents during the selected period."},
        {"term": "Cash Collected", "definition": "Non-voided rent ledger payments during the selected period. This is actual money received."},
        {"term": "Work Credit (Program Approved Rent Offset)", "definition": "Non-voided rent ledger credits with source code manual_credit_work_credit. This is approved labor applied instead of a cash rent payment."},
        {"term": "Total Rent Applied", "definition": "Cash collected plus program approved work credit applied toward rent."},
        {"term": "Vacancy Loss (Unoccupied Capacity)", "definition": "Minimal capacity rent minus actual charged rent. This is conservative and separates unoccupied capacity from unpaid rent."},
        {"term": "Vacancy Percentage", "definition": "Vacant capacity days divided by configured total capacity days for the selected period."},
        {"term": "Unpaid Rent (After Credits)", "definition": "Actual charged rent minus cash collected and program approved work credit."},
        {"term": "Rent Collection Rate", "definition": "Cash collected divided by actual charged rent. This is a rent collection measure, not a resident recovery outcome measure."},
    ]

    return RentFinancialReport(
        year=period.year,
        period_start=period.start_date.isoformat(),
        period_end=period.end_date.isoformat(),
        period_label=period.label,
        generated_at=datetime.now(CHICAGO_TZ).replace(microsecond=0).isoformat(),
        rows=rows,
        totals=_build_total_row(rows),
        monthly_rows=_monthly_rows(period),
        twelve_month_trend=_rolling_twelve_month_trend(period),
        definitions=definitions,
    )


def build_rent_resident_drilldown(*, year: int | None = None, shelter: str, period: RentReportPeriod | None = None) -> dict:
    if period is None:
        period = clean_report_period(year_value=year)

    shelter_key = _shelter_key(shelter)
    month_start, month_end, start_text, end_text = _period_bounds(period)
    rows = db_fetchall(
        """
        SELECT
            r.id AS resident_id,
            r.first_name,
            r.last_name,
            COALESCE(SUM(COALESCE(e.prorated_charge, e.current_charge, 0)), 0) AS rent_charged,
            COALESCE(SUM(COALESCE(e.occupied_days, 0)), 0) AS occupied_days
        FROM residents r
        JOIN resident_rent_sheet_entries e ON e.resident_id = r.id
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE ((s.rent_year * 100) + s.rent_month) >= ?
          AND ((s.rent_year * 100) + s.rent_month) <= ?
          AND LOWER(COALESCE(s.shelter, '')) = ?
        GROUP BY r.id, r.first_name, r.last_name
        ORDER BY r.last_name ASC, r.first_name ASC, r.id ASC
        """,
        (month_start, month_end, shelter_key),
    )
    credit_rows = db_fetchall(
        """
        SELECT
            resident_id,
            COALESCE(SUM(CASE WHEN entry_type = 'payment' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS cash_collected,
            COALESCE(SUM(CASE WHEN source_code = 'manual_credit_work_credit' THEN COALESCE(credit_amount, 0) ELSE 0 END), 0) AS work_credit
        FROM resident_rent_ledger_entries
        WHERE entry_date >= ?
          AND entry_date <= ?
          AND LOWER(COALESCE(shelter, '')) = ?
          AND COALESCE(voided, FALSE) = FALSE
        GROUP BY resident_id
        """,
        (start_text, end_text, shelter_key),
    )
    credits = {int(row.get("resident_id")): dict(row) for row in credit_rows or []}
    output_rows: list[dict] = []

    for row in rows or []:
        resident_id = int(row.get("resident_id"))
        credit = credits.get(resident_id, {})
        rent_charged = _money(row.get("rent_charged"))
        cash = _money(credit.get("cash_collected"))
        work = _money(credit.get("work_credit"))
        total_applied = round(cash + work, 2)
        output_rows.append(
            {
                "resident_id": resident_id,
                "resident_name": f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip(),
                "rent_charged": rent_charged,
                "cash_collected": cash,
                "work_credit": work,
                "total_rent_applied": total_applied,
                "unpaid_rent": round(rent_charged - total_applied, 2),
                "occupied_days": _int(row.get("occupied_days")),
                "rent_collection_rate": _pct(cash, rent_charged),
            }
        )

    totals = {
        "rent_charged": round(sum(row["rent_charged"] for row in output_rows), 2),
        "cash_collected": round(sum(row["cash_collected"] for row in output_rows), 2),
        "work_credit": round(sum(row["work_credit"] for row in output_rows), 2),
        "total_rent_applied": round(sum(row["total_rent_applied"] for row in output_rows), 2),
        "unpaid_rent": round(sum(row["unpaid_rent"] for row in output_rows), 2),
    }

    return {
        "year": period.year,
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "period_label": period.label,
        "shelter": shelter_key,
        "shelter_label": _shelter_label(shelter_key),
        "rows": output_rows,
        "totals": totals,
    }
