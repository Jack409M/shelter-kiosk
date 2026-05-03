from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean, median

from core.db import db_fetchall

SHELTER_ORDER = ("abba", "haven", "gratitude")
SHELTER_LABELS = {
    "abba": "Abba House",
    "haven": "Haven House",
    "gratitude": "Gratitude House",
}


@dataclass(slots=True)
class IdleTimeShelterRow:
    shelter: str
    shelter_label: str
    turnover_count: int
    matched_fill_count: int
    avg_idle_days: float | None
    median_idle_days: float | None
    longest_idle_days: int | None
    over_two_day_count: int
    over_seven_day_count: int
    current_idle_count: int
    current_over_two_day_count: int
    current_over_seven_day_count: int
    current_longest_idle_days: int | None


def _shelter_key(value: object | None) -> str:
    text = str(value or "").strip().lower()
    if text.endswith(" house"):
        text = text.removesuffix(" house").strip()
    return text


def _shelter_label(value: object | None) -> str:
    key = _shelter_key(value)
    return SHELTER_LABELS.get(key, key.title() if key else "Unknown")


def _parse_date(value: object | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _name(row: dict) -> str:
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()


def _historical_rows_for_year(year: int) -> tuple[list[dict], list[dict]]:
    exits = db_fetchall(
        """
        SELECT pe.id, pe.resident_id, pe.shelter, pe.entry_date, pe.exit_date, r.first_name, r.last_name
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE pe.exit_date >= ?
          AND pe.exit_date <= ?
          AND COALESCE(pe.exit_date, '') <> ''
        ORDER BY LOWER(COALESCE(pe.shelter, '')) ASC, pe.exit_date ASC, pe.id ASC
        """,
        (f"{year:04d}-01-01", f"{year:04d}-12-31"),
    )
    entries = db_fetchall(
        """
        SELECT pe.id, pe.resident_id, pe.shelter, pe.entry_date, pe.exit_date, r.first_name, r.last_name
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE pe.entry_date >= ?
          AND pe.entry_date <= ?
          AND COALESCE(pe.entry_date, '') <> ''
        ORDER BY LOWER(COALESCE(pe.shelter, '')) ASC, pe.entry_date ASC, pe.id ASC
        """,
        (f"{year:04d}-01-01", f"{year:04d}-12-31"),
    )
    return [dict(row) for row in exits or []], [dict(row) for row in entries or []]


def _live_rows(today: date) -> tuple[list[dict], list[dict]]:
    exits = db_fetchall(
        """
        SELECT pe.id, pe.resident_id, pe.shelter, pe.entry_date, pe.exit_date, r.first_name, r.last_name
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE pe.exit_date <= ?
          AND COALESCE(pe.exit_date, '') <> ''
        ORDER BY LOWER(COALESCE(pe.shelter, '')) ASC, pe.exit_date ASC, pe.id ASC
        """,
        (today.isoformat(),),
    )
    entries = db_fetchall(
        """
        SELECT pe.id, pe.resident_id, pe.shelter, pe.entry_date, pe.exit_date, r.first_name, r.last_name
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE COALESCE(pe.entry_date, '') <> ''
        ORDER BY LOWER(COALESCE(pe.shelter, '')) ASC, pe.entry_date ASC, pe.id ASC
        """,
    )
    return [dict(row) for row in exits or []], [dict(row) for row in entries or []]


def _matched_idle_days(exits: list[dict], entries: list[dict], shelter: str) -> tuple[int, list[int]]:
    shelter_exits = [row for row in exits if _shelter_key(row.get("shelter")) == shelter]
    shelter_entries = [row for row in entries if _shelter_key(row.get("shelter")) == shelter]
    used_entry_ids: set[int] = set()
    idle_days: list[int] = []

    for exit_row in shelter_exits:
        exit_date = _parse_date(exit_row.get("exit_date"))
        if not exit_date:
            continue

        match = None
        match_date = None
        for entry_row in shelter_entries:
            entry_id = int(entry_row.get("id") or 0)
            if entry_id in used_entry_ids:
                continue
            if int(entry_row.get("resident_id") or 0) == int(exit_row.get("resident_id") or 0):
                continue
            entry_date = _parse_date(entry_row.get("entry_date"))
            if not entry_date or entry_date < exit_date:
                continue
            if match_date is None or entry_date < match_date:
                match = entry_row
                match_date = entry_date

        if match and match_date:
            used_entry_ids.add(int(match.get("id") or 0))
            idle_days.append(max((match_date - exit_date).days, 0))

    return len(shelter_exits), idle_days


def _current_idle_slots_for_shelter(exits: list[dict], entries: list[dict], shelter: str, today: date) -> list[dict]:
    shelter_exits = [row for row in exits if _shelter_key(row.get("shelter")) == shelter]
    shelter_entries = [row for row in entries if _shelter_key(row.get("shelter")) == shelter]
    current: list[dict] = []

    for exit_row in shelter_exits:
        exit_date = _parse_date(exit_row.get("exit_date"))
        if not exit_date:
            continue
        filled = False
        for entry_row in shelter_entries:
            if int(entry_row.get("resident_id") or 0) == int(exit_row.get("resident_id") or 0):
                continue
            entry_date = _parse_date(entry_row.get("entry_date"))
            if entry_date and entry_date >= exit_date:
                filled = True
                break
        if filled:
            continue
        idle_days = max((today - exit_date).days, 0)
        current.append(
            {
                "shelter": shelter,
                "shelter_label": _shelter_label(shelter),
                "resident_id": int(exit_row.get("resident_id") or 0),
                "resident_name": _name(exit_row) or "Unknown resident",
                "exit_date": exit_date.isoformat(),
                "idle_days": idle_days,
            }
        )

    return sorted(current, key=lambda row: row["idle_days"], reverse=True)


def build_resident_slot_idle_time_report(year: int) -> dict:
    today = date.today()
    exits, entries = _historical_rows_for_year(year)
    live_exits, live_entries = _live_rows(today)
    rows: list[IdleTimeShelterRow] = []
    all_idle_days: list[int] = []
    all_current_slots: list[dict] = []
    total_turnovers = 0

    for shelter in SHELTER_ORDER:
        turnover_count, idle_days = _matched_idle_days(exits, entries, shelter)
        current_slots = _current_idle_slots_for_shelter(live_exits, live_entries, shelter, today)
        current_idle_days = [int(row["idle_days"]) for row in current_slots]
        total_turnovers += turnover_count
        all_idle_days.extend(idle_days)
        all_current_slots.extend(current_slots)
        rows.append(
            IdleTimeShelterRow(
                shelter=shelter,
                shelter_label=_shelter_label(shelter),
                turnover_count=turnover_count,
                matched_fill_count=len(idle_days),
                avg_idle_days=round(mean(idle_days), 1) if idle_days else None,
                median_idle_days=round(median(idle_days), 1) if idle_days else None,
                longest_idle_days=max(idle_days) if idle_days else None,
                over_two_day_count=sum(1 for value in idle_days if value > 2),
                over_seven_day_count=sum(1 for value in idle_days if value > 7),
                current_idle_count=len(current_slots),
                current_over_two_day_count=sum(1 for value in current_idle_days if value > 2),
                current_over_seven_day_count=sum(1 for value in current_idle_days if value > 7),
                current_longest_idle_days=max(current_idle_days) if current_idle_days else None,
            )
        )

    all_current_idle_days = [int(row["idle_days"]) for row in all_current_slots]
    totals = IdleTimeShelterRow(
        shelter="total_program",
        shelter_label="Total Program",
        turnover_count=total_turnovers,
        matched_fill_count=len(all_idle_days),
        avg_idle_days=round(mean(all_idle_days), 1) if all_idle_days else None,
        median_idle_days=round(median(all_idle_days), 1) if all_idle_days else None,
        longest_idle_days=max(all_idle_days) if all_idle_days else None,
        over_two_day_count=sum(1 for value in all_idle_days if value > 2),
        over_seven_day_count=sum(1 for value in all_idle_days if value > 7),
        current_idle_count=len(all_current_slots),
        current_over_two_day_count=sum(1 for value in all_current_idle_days if value > 2),
        current_over_seven_day_count=sum(1 for value in all_current_idle_days if value > 7),
        current_longest_idle_days=max(all_current_idle_days) if all_current_idle_days else None,
    )

    return {
        "year": year,
        "rows": rows,
        "totals": totals,
        "current_idle_slots": all_current_slots,
        "definition": "Resident slot idle time measures days between a resident exit date and the next different resident entry date in the same shelter. Live idle slots are exits that do not yet have a later different resident entry in the same shelter. This is a practical refill speed metric, not a waitlist or intake speed metric.",
    }
