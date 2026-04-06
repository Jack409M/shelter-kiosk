from __future__ import annotations


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _allowed(session_obj) -> bool:
    return session_obj.get("role") in {"admin", "shelter_director", "case_manager"}
