from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CRITICAL_FILES = [
    "core/app_factory.py",
    "core/db.py",
    "core/intake_service.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_critical_files_not_empty_and_hashable() -> None:
    failures: list[str] = []

    for relative in CRITICAL_FILES:
        path = PROJECT_ROOT / relative

        if not path.exists():
            failures.append(f"missing file: {relative}")
            continue

        content = path.read_bytes()
        if not content:
            failures.append(f"empty file: {relative}")
            continue

        digest = _sha256(path)

        if len(digest) != 64:
            failures.append(f"invalid hash length: {relative}")

    assert failures == []
