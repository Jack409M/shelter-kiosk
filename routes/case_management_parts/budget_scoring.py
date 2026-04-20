from __future__ import annotations

from datetime import datetime

from core.db import db_fetchall
from core.helpers import utcnow_iso


_COLOR_RULES = (
    (90, "green", "Green", "background:#eef8f0; border:1px solid #9bc8a6;", "color:#1f6b33; font-weight:800;"),
    (80, "yellow", "Yellow", "background:#fff8e1; border:1px solid #e0c36c;", "color:#8a6a00; font-weight:800;"),
    (70, "orange", "Orange", "background:#fff1e8; border:1px solid #e8b184;", "color:#a65313; font-weight:800;"),
    (0, "red", "Red", "background:#fff0f0; border:1px solid #e2a0a0;", "color:#9a1f1f; font-weight:800;"),
)


def _parse_budget_month(month_text: str | None):
    month_value = str(month_text or "").strip()
    if not month_value:
        return None
    try:
        return datetime.strptime(month_value, "%Y-%m")
    except ValueError:
        return None



def _format_budget_month(month_text: str | None) -> str:
    parsed = _parse_budget_month(month_text)
    if parsed is None:
        return "Missing Month"
    return parsed.strftime("%B %Y")



def _load_budget_session_metrics(budget_id: int) -> dict:
    rows = db_fetchall(
        """
        SELECT li.line_group,
               li.projected_amount,
               li.actual_amount,
               COALESCE(SUM(CASE WHEN COALESCE(t.is_deleted, FALSE) = FALSE THEN t.amount ELSE 0 END), 0) AS txn_total
        FROM resident_budget_line_items li
        LEFT JOIN resident_budget_transactions t ON t.line_item_id = li.id
        WHERE li.budget_session_id = ?
        GROUP BY li.id
        ORDER BY li.sort_order, li.id
        """,
        (budget_id,),
    )

    projected_expenses = 0.0
    actual_expenses = 0.0

    for row in rows or []:
        group = str(row.get("line_group") or "").strip().lower()
        if group != "expense":
            continue
        projected_expenses += float(row.get("projected_amount") or 0)
        actual_expenses += float(row.get("txn_total") or 0)

    return {
        "projected_expenses": round(projected_expenses, 2),
        "actual_expenses": round(actual_expenses, 2),
    }



def _score_month(projected: float, actual: float) -> float:
    if projected <= 0 and actual <= 0:
        discipline = 100.0
        completion = 100.0
        stability = 100.0
    elif projected <= 0:
        discipline = 40.0
        completion = 50.0
        stability = 50.0
    else:
        over_pct = max((actual - projected) / projected, 0.0)
        discipline = max(40.0, 100.0 - (over_pct * 100.0))
        completion = min((actual / projected) * 100.0, 100.0)
        ratio = actual / projected
        if ratio <= 1.10:
            stability = 100.0
        elif ratio <= 1.25:
            stability = 75.0
        elif ratio <= 1.50:
            stability = 50.0
        else:
            stability = 25.0

    final_score = (discipline * 0.60) + (completion * 0.25) + (stability * 0.15)
    return round(final_score, 0)



def _band_for_score(score: float) -> dict:
    numeric_score = float(score or 0)
    for minimum, key, label, card_style, value_style in _COLOR_RULES:
        if numeric_score >= minimum:
            return {
                "band_key": key,
                "band_label": label,
                "card_style": card_style,
                "value_style": value_style,
            }
    return {
        "band_key": "red",
        "band_label": "Red",
        "card_style": "background:#fff0f0; border:1px solid #e2a0a0;",
        "value_style": "color:#9a1f1f; font-weight:800;",
    }



def load_budget_score_snapshot(resident_id: int) -> dict:
    rows = db_fetchall(
        """
        SELECT id, budget_month
        FROM resident_budget_sessions
        WHERE resident_id = ?
          AND budget_month IS NOT NULL
        ORDER BY budget_month DESC, id DESC
        """,
        (resident_id,),
    )

    current_month = utcnow_iso()[:7]
    seen_months: set[str] = set()
    eligible_rows: list[dict] = []

    for row in rows or []:
        month_key = str(row.get("budget_month") or "").strip()
        if not month_key or month_key in seen_months:
            continue
        if month_key > current_month:
            continue
        seen_months.add(month_key)
        eligible_rows.append(dict(row))
        if len(eligible_rows) >= 9:
            break

    weighted_total = 0.0
    weight_sum = 0.0
    month_rows: list[dict] = []

    for idx, row in enumerate(eligible_rows):
        metrics = _load_budget_session_metrics(int(row["id"]))
        score = _score_month(
            projected=float(metrics.get("projected_expenses") or 0),
            actual=float(metrics.get("actual_expenses") or 0),
        )
        weight = len(eligible_rows) - idx
        weighted_total += score * weight
        weight_sum += weight
        month_rows.append(
            {
                "budget_id": row["id"],
                "budget_month": row.get("budget_month"),
                "budget_month_label": _format_budget_month(row.get("budget_month")),
                "score": score,
                "projected_expenses": metrics.get("projected_expenses", 0.0),
                "actual_expenses": metrics.get("actual_expenses", 0.0),
                "weight": weight,
            }
        )

    average_score = round(weighted_total / weight_sum, 0) if weight_sum else None
    band = _band_for_score(average_score or 0)

    return {
        "average_score": average_score,
        "average_score_display": f"{int(average_score)}%" if average_score is not None else "—",
        "eligible_month_count": len(month_rows),
        "month_rows": month_rows,
        **band,
    }
