from __future__ import annotations

from core.db import db_fetchall
from core.helpers import utcnow_iso


def _score_month(projected: float, actual: float) -> float:
    if projected <= 0 and actual <= 0:
        discipline = 100
        completion = 100
        stability = 100
    elif projected <= 0:
        discipline = 40
        completion = 50
        stability = 50
    else:
        over_pct = max((actual - projected) / projected, 0)
        discipline = max(40, 100 - (over_pct * 100))

        completion = min((actual / projected) * 100, 100)

        ratio = actual / projected
        if ratio <= 1.10:
            stability = 100
        elif ratio <= 1.25:
            stability = 75
        elif ratio <= 1.50:
            stability = 50
        else:
            stability = 25

    return round((discipline * 0.60) + (completion * 0.25) + (stability * 0.15), 0)


def _band(score: float):
    if score >= 90:
        return (
            "Green",
            "background:#eef8f0; border:1px solid #9bc8a6;",
            "color:#1f6b33; font-weight:800;",
        )
    elif score >= 80:
        return (
            "Yellow",
            "background:#fff8e1; border:1px solid #e0c36c;",
            "color:#8a6a00; font-weight:800;",
        )
    elif score >= 70:
        return (
            "Orange",
            "background:#fff1e8; border:1px solid #e8b184;",
            "color:#a65313; font-weight:800;",
        )
    else:
        return (
            "Red",
            "background:#fff0f0; border:1px solid #e2a0a0;",
            "color:#9a1f1f; font-weight:800;",
        )


def load_budget_score_snapshot(resident_id: int) -> dict:
    rows = db_fetchall(
        """
        SELECT id, budget_month
        FROM resident_budget_sessions
        WHERE resident_id = ?
          AND budget_month IS NOT NULL
        ORDER BY budget_month DESC
        """,
        (resident_id,),
    )

    current_month = utcnow_iso()[:7]

    months = []
    seen = set()

    for row in rows:
        m = str(row["budget_month"])
        if m > current_month:
            continue
        if m in seen:
            continue
        seen.add(m)
        months.append(row)
        if len(months) >= 9:
            break

    total = 0
    weight_sum = 0

    for i, row in enumerate(months):
        data = db_fetchall(
            """
            SELECT
                projected_amount,
                (
                    SELECT COALESCE(SUM(amount),0)
                    FROM resident_budget_transactions t
                    WHERE t.line_item_id = li.id
                    AND COALESCE(t.is_deleted, FALSE) = FALSE
                ) as actual
            FROM resident_budget_line_items li
            WHERE li.budget_session_id = ?
              AND line_group = 'expense'
            """,
            (row["id"],),
        )

        projected = sum(float(x["projected_amount"] or 0) for x in data)
        actual = sum(float(x["actual"] or 0) for x in data)

        score = _score_month(projected, actual)

        weight = len(months) - i
        total += score * weight
        weight_sum += weight

    if weight_sum == 0:
        return {}

    avg = round(total / weight_sum, 0)
    label, card, value = _band(avg)

    return {
        "average_score": avg,
        "average_score_display": f"{int(avg)}%",
        "eligible_month_count": len(months),
        "band_label": label,
        "card_style": card,
        "value_style": value,
    }
