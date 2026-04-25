from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIRS = ("core", "db", "routes", "scripts")
ALLOWED_FILES = {
    Path("core/file_safety.py"),
}
UNSAFE_PATH_METHODS = {"write_text", "write_bytes"}
UNSAFE_OPEN_MODES = {"w", "a", "x", "w+", "a+", "x+", "wb", "ab", "xb", "w+b", "a+b", "x+b"}


class UnsafeWriteVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: Path) -> None:
        self.relative_path = relative_path
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        self._check_open_call(node)
        self._check_json_dump_call(node)
        self._check_path_write_call(node)
        self.generic_visit(node)

    def _check_open_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id != "open":
            return

        mode = self._extract_open_mode(node)
        if mode in UNSAFE_OPEN_MODES:
            self.violations.append(
                f"{self.relative_path}:{node.lineno} uses open(..., {mode!r}); use core.file_safety"
            )

    def _extract_open_mode(self, node: ast.Call) -> str | None:
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            return node.args[1].value if isinstance(node.args[1].value, str) else None

        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                return keyword.value.value if isinstance(keyword.value.value, str) else None

        return None

    def _check_json_dump_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        if node.func.attr != "dump":
            return
        if not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id != "json":
            return

        self.violations.append(
            f"{self.relative_path}:{node.lineno} uses json.dump(...); use safe_write_json"
        )

    def _check_path_write_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        if node.func.attr not in UNSAFE_PATH_METHODS:
            return

        self.violations.append(
            f"{self.relative_path}:{node.lineno} uses .{node.func.attr}(...); use core.file_safety"
        )


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for directory_name in APP_DIRS:
        directory = PROJECT_ROOT / directory_name
        if not directory.exists():
            continue
        files.extend(sorted(directory.rglob("*.py")))
    return files


def test_application_code_does_not_introduce_unsafe_direct_file_writes() -> None:
    violations: list[str] = []

    for path in _iter_python_files():
        relative_path = path.relative_to(PROJECT_ROOT)
        if relative_path in ALLOWED_FILES:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative_path))
        visitor = UnsafeWriteVisitor(relative_path)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    assert not violations, "Unsafe direct file writes found:\n" + "\n".join(violations)
