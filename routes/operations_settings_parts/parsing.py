from __future__ import annotations


def _to_bool(value: str | None, default: bool = False) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return default


def _to_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip() or str(default))
    except Exception:
        return default


def _to_float(value: str | None, default: float) -> float:
    try:
        return float((value or "").strip() or str(default))
    except Exception:
        return default


def _merge_text(name: str, form, existing, default: str = "") -> str:
    if name in form:
        return (form.get(name) or "").strip()
    if existing in (None, ""):
        return default
    return str(existing).strip()


def _merge_bool(name: str, form, existing, default: bool = False) -> bool:
    if name in form:
        return _to_bool(form.get(name), default)
    if existing is None:
        return default
    return bool(existing)


def _merge_int(name: str, form, existing, default: int) -> int:
    if name in form:
        return _to_int(form.get(name), default)
    if existing in (None, ""):
        return default
    try:
        return int(existing)
    except Exception:
        return default


def _merge_float(name: str, form, existing, default: float) -> float:
    if name in form:
        return _to_float(form.get(name), default)
    if existing in (None, ""):
        return default
    try:
        return float(existing)
    except Exception:
        return default
