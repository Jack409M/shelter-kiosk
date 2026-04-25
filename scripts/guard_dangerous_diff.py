from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_ROOTS = (
    "core/",
    "db/",
    "routes/",
    "templates/",
    "static/",
)
PROTECTED_SUFFIXES = (
    ".py",
    ".html",
    ".css",
    ".js",
    ".sql",
)
CRITICAL_FILES = {
    "app.py": ("app = create_app()",),
    "core/app_factory.py": ("def create_app", "def register_blueprints", "_register_csrf"),
    "core/db.py": ("def db_transaction", "def db_execute", "def db_fetchone", "def db_fetchall"),
    "core/runtime.py": ("def init_db", "def load_runtime_config"),
    "core/intake_service.py": ("def create_intake", "def update_intake"),
    "db/schema.py": ("def init_db", "def _run_schema_initialization"),
    "routes/resident_portal.py": ("def home", "def resident_chores"),
    "routes/residents.py": ("Blueprint",),
}
PROTECTED_DELETE_EXCEPTIONS = {
    "__init__.py",
}
MAX_PROTECTED_FILES_CHANGED = 35
MAX_TOTAL_DELETED_LINES = 3000
DEFAULT_SHRINK_RATIO = 0.70
CRITICAL_SHRINK_RATIO = 0.85
MINIMUM_OLD_LINES_FOR_SHRINK_CHECK = 40


def _run_git(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_protected_path(path: str) -> bool:
    if path in CRITICAL_FILES:
        return True
    if not path.endswith(PROTECTED_SUFFIXES):
        return False
    return path.startswith(PROTECTED_ROOTS)


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _git_file_text(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _line_count(text: str | None) -> int:
    if text is None:
        return 0
    return len(text.splitlines())


def _parse_name_status(base_ref: str, head_ref: str) -> list[tuple[str, str, str | None]]:
    output = _run_git(["diff", "--name-status", base_ref, head_ref])
    changes: list[tuple[str, str, str | None]] = []

    for raw_line in output.splitlines():
        parts = raw_line.split("\t")
        if not parts:
            continue

        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                changes.append((status[0], parts[2], parts[1]))
            continue

        if len(parts) >= 2:
            changes.append((status[0], parts[1], None))

    return changes


def _parse_numstat(base_ref: str, head_ref: str) -> dict[str, tuple[int, int]]:
    output = _run_git(["diff", "--numstat", base_ref, head_ref])
    stats: dict[str, tuple[int, int]] = {}

    for raw_line in output.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 3:
            continue

        added_raw, deleted_raw, path = parts[0], parts[1], parts[2]
        if added_raw == "-" or deleted_raw == "-":
            continue

        try:
            added = int(added_raw)
            deleted = int(deleted_raw)
        except ValueError:
            continue

        if " => " in path:
            path = path.split(" => ", 1)[1].replace("}", "")
            if "/" in path and "{" in path:
                prefix, suffix = path.split("{", 1)
                path = prefix + suffix

        stats[path] = (added, deleted)

    return stats


def _validate_refs(base_ref: str, head_ref: str) -> None:
    _run_git(["rev-parse", "--verify", base_ref])
    _run_git(["rev-parse", "--verify", head_ref])


def _check_deleted_files(
    changes: list[tuple[str, str, str | None]],
    failures: list[str],
) -> None:
    for status, path, old_path in changes:
        checked_paths = [path]
        if old_path:
            checked_paths.append(old_path)

        for checked_path in checked_paths:
            if not _is_protected_path(checked_path):
                continue
            if _basename(checked_path) in PROTECTED_DELETE_EXCEPTIONS:
                continue
            if status == "D":
                failures.append(f"protected file deleted: {checked_path}")


def _check_large_or_suspicious_change_set(
    changes: list[tuple[str, str, str | None]],
    stats: dict[str, tuple[int, int]],
    failures: list[str],
) -> None:
    protected_changed = sorted(
        path for _, path, _ in changes if _is_protected_path(path)
    )
    deleted_lines = sum(deleted for path, (_, deleted) in stats.items() if _is_protected_path(path))

    if len(protected_changed) > MAX_PROTECTED_FILES_CHANGED and not _env_truthy("ALLOW_LARGE_DIFF"):
        failures.append(
            "too many protected files changed in one diff: "
            f"{len(protected_changed)} files, limit {MAX_PROTECTED_FILES_CHANGED}; "
            "set ALLOW_LARGE_DIFF=1 only for an intentional large migration"
        )

    if deleted_lines > MAX_TOTAL_DELETED_LINES and not _env_truthy("ALLOW_LARGE_DIFF"):
        failures.append(
            "too many protected lines deleted in one diff: "
            f"{deleted_lines} lines, limit {MAX_TOTAL_DELETED_LINES}; "
            "set ALLOW_LARGE_DIFF=1 only for an intentional large migration"
        )


def _check_suspicious_shrinkage(
    base_ref: str,
    head_ref: str,
    changes: list[tuple[str, str, str | None]],
    failures: list[str],
) -> None:
    if _env_truthy("ALLOW_FILE_SHRINK"):
        return

    for status, path, old_path in changes:
        if status in {"A", "D"}:
            continue
        if not _is_protected_path(path):
            continue

        previous_path = old_path or path
        old_text = _git_file_text(base_ref, previous_path)
        new_text = _git_file_text(head_ref, path)
        old_lines = _line_count(old_text)
        new_lines = _line_count(new_text)

        if old_lines < MINIMUM_OLD_LINES_FOR_SHRINK_CHECK:
            continue

        ratio = CRITICAL_SHRINK_RATIO if path in CRITICAL_FILES else DEFAULT_SHRINK_RATIO
        minimum_allowed = int(old_lines * ratio)

        if new_lines < minimum_allowed:
            failures.append(
                f"suspicious file shrink: {path} went from {old_lines} lines to {new_lines}; "
                f"minimum allowed without ALLOW_FILE_SHRINK=1 is {minimum_allowed}"
            )


def _check_critical_symbols(
    base_ref: str,
    head_ref: str,
    failures: list[str],
) -> None:
    for path, required_symbols in CRITICAL_FILES.items():
        old_text = _git_file_text(base_ref, path)
        new_text = _git_file_text(head_ref, path)

        if old_text is None and new_text is None:
            failures.append(f"critical file missing in both refs: {path}")
            continue

        if old_text is not None and new_text is None:
            failures.append(f"critical file removed: {path}")
            continue

        if new_text is None:
            continue

        for symbol in required_symbols:
            if symbol in (old_text or "") and symbol not in new_text:
                failures.append(f"critical symbol removed from {path}: {symbol}")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/guard_dangerous_diff.py <base-ref> <head-ref>")
        return 2

    base_ref = sys.argv[1]
    head_ref = sys.argv[2]

    if _env_truthy("ALLOW_DANGEROUS_DIFF"):
        print("Dangerous diff guard skipped because ALLOW_DANGEROUS_DIFF=1")
        return 0

    try:
        _validate_refs(base_ref, head_ref)
        changes = _parse_name_status(base_ref, head_ref)
        stats = _parse_numstat(base_ref, head_ref)
    except RuntimeError as exc:
        print(f"Dangerous diff guard could not inspect diff: {exc}")
        return 1

    failures: list[str] = []
    _check_deleted_files(changes, failures)
    _check_large_or_suspicious_change_set(changes, stats, failures)
    _check_suspicious_shrinkage(base_ref, head_ref, changes, failures)
    _check_critical_symbols(base_ref, head_ref, failures)

    if failures:
        print("Dangerous diff guard failed. Review these changes before merging:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Dangerous diff guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
