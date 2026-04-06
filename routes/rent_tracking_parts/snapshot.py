from __future__ import annotations

from core.db import db_fetchall

from .calculations import _rent_band_for_score
from .dates import _completed_month_keys, _month_label
from .utils import _placeholder


def build_rent_stability_snapshot(resident_id: int, lookback_months: int = 9) -> dict:
    month_keys = _completed_month_keys(lookback_months)
    ph = _placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            e.compliance_score,
            s.rent_year,
            s.rent_month
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        """,
        (resident_id,),
    )

    score_by_month: dict[tuple[int, int], int] = {}
    for row in rows:
        year = int(row["rent_year"])
        month = int(row["rent_month"])
        key = (year, month)
        if key not in score_by_month:
            score_by_month[key] = int(row.get("compliance_score") or 0)

    month_rows = []
    month_scores: list[int] = []

    for year, month in month_keys:
        score = score_by_month.get((year, month), 0)
        month_scores.append(score)
        month_rows.append(
            {
                "year": year,
                "month": month,
                "label": _month_label(year, month),
                "score": score,
            }
        )

    average_score = round(sum(month_scores) / len(month_scores), 1) if month_scores else 0.0
    band = _rent_band_for_score(average_score)

    return {
        "lookback_months": lookback_months,
        "average_score": average_score,
        "average_score_display": f"{average_score:.1f}",
        "graduation_target": 95,
        "passes_graduation": average_score >= 95,
        "band_key": band["band_key"],
        "band_label": band["band_label"],
        "card_style": band["card_style"],
        "value_style": band["value_style"],
        "pill_style": band["pill_style"],
        "month_rows": month_rows,
    }
