from __future__ import annotations

from typing import Any

from core.intake_service import IntakeCreateResult, create_intake


def finalize_intake(
    *,
    current_shelter: str,
    data: dict[str, Any],
    draft_id: int | None,
) -> IntakeCreateResult:
    """
    Finalize a new resident intake and write the official entry baseline.

    Contract:
    - Draft data is not reportable.
    - Final submit creates the official intake baseline.
    - The baseline write is owned by the intake service layer.
    - Routes should call this boundary instead of owning cross table writes.
    """
    return create_intake(
        current_shelter=current_shelter,
        data=data,
        draft_id=draft_id,
    )
