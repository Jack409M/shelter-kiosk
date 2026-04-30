from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_notes_history_form(form: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    return dict(form or {}), []
