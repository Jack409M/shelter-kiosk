from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (PROJECT_ROOT / "core", PROJECT_ROOT / "routes")
WRITE_SQL_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

# These helpers intentionally perform pieces of a larger atomic workflow.
# They are allowed to write more than one table only because a named parent
# service function or route wraps them in db_transaction(). New entries here
# should be rare and should be reviewed as a transaction boundary decision.
ALLOWED_NESTED_MULTI_TABLE_WRITERS = {
    ("core/NP_placement_service.py", "replace_active_placement"),
    ("core/l9_support_lifecycle.py", "start_level9_lifecycle"),
    ("routes/attendance_parts/pass_action_helpers.py", "apply_pass_approval"),
    ("routes/attendance_parts/pass_action_helpers.py", "apply_pass_check_in"),
    ("routes/attendance_parts/pass_action_helpers.py", "apply_pass_denial"),
    ("routes/case_management_parts/family.py", "delete_child_view"),
    ("routes/case_management_parts/family.py", "edit_child_view"),
    ("routes/case_management_parts/family.py", "family_intake_view"),
    ("routes/case_management_parts/income_state_sync.py", "recalculate_and_sync_income_state_atomic"),
    ("routes/case_management_parts/income_state_sync.py", "save_income_support_and_sync_snapshot_atomic"),
    ("routes/case_management_parts/intake_inserts.py", "_insert_intake_assessment"),
    ("routes/case_management_parts/promotion_review.py", "promotion_review_view"),
    ("routes/case_management_parts/transfer.py", "_apply_transfer"),
    ("routes/resident_parts/pass_request_helpers.py", "insert_pass_request"),
}

# These are the high risk user actions where a route must call one named
# atomic entry point instead of open coding separate table updates.
REQUIRED_ATOMIC_ENTRY_POINTS = {
    "routes/case_management_parts/exit.py": "_save_exit_assessment_atomic",
    "core/intake_service.py": "create_intake",
    "core/intake_service.py": "create_intake_for_existing_resident",
    "core/intake_service.py": "update_intake",
    "routes/case_management_parts/income_state_sync.py": "save_income_support_and_sync_snapshot_atomic",
    "routes/case_management_parts/income_state_sync.py": "recalculate_and_sync_income_state_atomic",
}


def _relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    return files


def _constant_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
        return "".join(parts)
    return ""


def _written_tables(node: ast.AST) -> set[str]:
    tables: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        for arg in child.args[:1]:
            sql_text = _constant_text(arg)
            if not sql_text:
                continue
            tables.update(match.group(1).lower() for match in WRITE_SQL_RE.finditer(sql_text))
    return tables


def _contains_db_transaction(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.With):
            continue
        for item in child.items:
            context_expr = item.context_expr
            if isinstance(context_expr, ast.Call):
                func = context_expr.func
                if isinstance(func, ast.Name) and func.id == "db_transaction":
                    return True
                if isinstance(func, ast.Attribute) and func.attr == "db_transaction":
                    return True
    return False


def _defined_functions(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_required_atomic_entry_points_exist_and_use_db_transaction() -> None:
    failures: list[str] = []

    for relative_path, function_name in sorted(REQUIRED_ATOMIC_ENTRY_POINTS.items()):
        path = PROJECT_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        matching_functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == function_name
        ]

        if not matching_functions:
            failures.append(f"{relative_path}: missing required atomic function {function_name}")
            continue

        if not _contains_db_transaction(matching_functions[0]):
            failures.append(
                f"{relative_path}:{function_name} must own a db_transaction() boundary"
            )

    assert not failures, "\n".join(failures)


def test_multi_table_writers_are_transactional_or_explicitly_reviewed() -> None:
    failures: list[str] = []

    for path in _python_files():
        relative_path = _relative_path(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue

            tables = _written_tables(node)
            if len(tables) < 2:
                continue

            if _contains_db_transaction(node):
                continue

            if (relative_path, node.name) in ALLOWED_NESTED_MULTI_TABLE_WRITERS:
                continue

            failures.append(
                f"{relative_path}:{node.name} writes multiple tables without db_transaction(): "
                f"{', '.join(sorted(tables))}"
            )

    assert not failures, "\n".join(failures)


def test_reviewed_nested_multi_table_writer_allowlist_stays_current() -> None:
    existing_functions: set[tuple[str, str]] = set()

    for path in _python_files():
        relative_path = _relative_path(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        for function_name in _defined_functions(tree):
            existing_functions.add((relative_path, function_name))

    stale_entries = sorted(ALLOWED_NESTED_MULTI_TABLE_WRITERS - existing_functions)

    assert not stale_entries, "stale transaction allowlist entries: " + ", ".join(
        f"{path}:{name}" for path, name in stale_entries
    )
