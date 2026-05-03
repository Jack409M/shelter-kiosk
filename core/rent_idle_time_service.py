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
SHELTER_CAPACITY = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
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


def _active_counts_by_shelter() -> dict[str, int]:
    rows = db_fetchall(
        """
        SELECT LOWER(COALESCE(shelter, '')) AS shelter, COUNT(*) AS active_count
        FROM program_enrollments
        WHERE program_status = 'active'
          AND COALESCE(exit_date, '') = ''
        GROUP BY LOWER(COALESCE(shelter, ''))
        """
    )
    return {_shelter_key(row.get("shelter")): int(row.get("active_count") or 0) for row in rows or []}


def _recent_exits_by_shelter(today: date) -> dict[str, list[dict]]:
    rows = db_fetchall(
        """
        SELECT pe.id, pe.resident_id, pe.shelter, pe.exit_date, r.first_name, r.last_name
        FROM program_enrollments pe
        LEFT JOIN residents r ON r.id = pe.resident_id
        WHERE pe.exit_date <= ?
          AND COALESCE(pe.exit_date, '') <> ''
        ORDER BY pe.exit_date DESC, pe.id DESC
        """,
        (today.isoformat(),),
    )
    grouped: dict[str, list[dict]] = {shelter: [] for shelter in SHELTER_ORDER}
    for row in rows or []:
        item = dict(row)
        shelter = _shelter_key(item.get("shelter"))
        if shelter in grouped:
            grouped[shelter].append(item)
    return grouped


def _current_open_slots_for_shelter(
    *,
    shelter: str,
    active_count: int,
    recent_exits: list[dict],
    today: date,
) -> list[dict]:
    capacity = SHELTER_CAPACITY.get(shelter, 0)
    open_count = max(capacity - active_count, 0)
    slots: list[dict] = []

    for index in range(open_count):
        exit_row = recent_exits[index] if index < len(recent_exits) else None
        exit_date = _parse_date(exit_row.get("exit_date")) if exit_row else None
        idle_days = max((today - exit_date).days, 0) if exit_date else None
        slots.append(
            {
                "shelter": shelter,
                "shelter_label": _shelter_label(shelter),
                "slot_label": f"Open Slot {index + 1}",
                "resident_id": int(exit_row.get("resident_id") or 0) if exit_row else None,
                "resident_name": _name(exit_row) if exit_row else "No recent exit matched",
                "exit_date": exit_date.isoformat() if exit_date else "—",
                "idle_days": idle_days,
                "capacity": capacity,
                "active_count": active_count,
            }
        )

    return slots


def build_resident_slot_idle_time_report(year: int) -> dict:
    today = date.today()
    exits, entries = _historical_rows_for_year(year)
    active_counts = _active_counts_by_shelter()
    recent_exits = _recent_exits_by_shelter(today)
    rows: list[IdleTimeShelterRow] = []
    all_idle_days: list[int] = []
    all_current_slots: list[dict] = []
    total_turnovers = 0

    for shelter in SHELTER_ORDER:
        turnover_count, idle_days = _matched_idle_days(exits, entries, shelter)
        current_slots = _current_open_slots_for_shelter(
            shelter=shelter,
            active_count=active_counts.get(shelter, 0),
            recent_exits=recent_exits.get(shelter, []),
            today=today,
        )
        current_idle_days = [int(row["idle_days"]) for row in current_slots if row.get("idle_days") is not None]
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

    all_current_idle_days = [int(row["idle_days"]) for row in all_current_slots if row.get("idle_days") is not None]
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
        "current_idle_slots": sorted(
            all_current_slots,
            key=lambda row: row.get("idle_days") if row.get("idle_days") is not None else -1,
            reverse=True,
        ),
        "definition": "Resident slot idle time measures historical days between a resident exit date and the next different resident entry date in the same shelter. Current open slots are calculated as shelter capacity minus active program enrollments. If a physical bed number is not stored, the page shows an open slot with the most recent exit used as the best available timing clue.",
    }
