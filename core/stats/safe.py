from __future__ import annotations

from typing import Any, Callable


def safe_stat(name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "data": fn(*args, **kwargs),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "data": {},
            "error": f"{name}: {exc}",
        }
