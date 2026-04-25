from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from core import db as core_db
from core.helpers import utcnow_iso


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON_ROOTS = (
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "routes",
    PROJECT_ROOT / "db",
)
INTENTIONAL_EMPTY_FILES = {
    "routes/operations_settings_parts/kiosk_categories.py",
}
TRUNCATION_MARKERS = (
    "SNIP",
    "... unchanged",
    "rest unchanged",
    "truncated)",
    "<truncated>",
)


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_PYTHON_ROOTS:
        files.extend(sorted(root.rglob("*.py")))
    return files


def test_no_datetime_utcnow_in_production_code() -> None:
    offenders: list[str] = []

    for path in _production_python_files():
        text = path.read_text(encoding="utf-8")
        if "datetime.utcnow" in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_production_python_files_parse_and_have_no_truncation_markers() -> None:
    failures: list[str] = []

    for path in _production_python_files():
        relative_path = str(path.relative_to(PROJECT_ROOT))
        text = path.read_text(encoding="utf-8")

        if not text.strip():
            if path.name == "__init__.py" or relative_path in INTENTIONAL_EMPTY_FILES:
                continue
            failures.append(f"{relative_path}: empty file")
            continue

        for marker in TRUNCATION_MARKERS:
            if marker in text:
                failures.append(f"{relative_path}: contains truncation marker {marker!r}")

        try:
            ast.parse(text, filename=relative_path)
        except SyntaxError as exc:
            failures.append(f"{relative_path}: syntax error at line {exc.lineno}: {exc.msg}")

    assert failures == []


def test_recent_redesign_modules_import_and_expose_expected_symbols() -> None:
    expected_symbols = {
        "core.intake_service": [
            "create_intake",
            "create_intake_for_existing_resident",
            "update_intake",
            "IntakeCreateResult",
            "IntakeUpdateResult",
        ],
        "core.pass_retention": [
            "run_pass_retention_cleanup_for_shelter",
        ],
        "core.report_filters": [
            "build_resident_filters",
            "resolve_date_range",
            "mask_small_counts",
        ],
        "routes.case_management_parts.family": [
            "family_intake_view",
            "edit_child_view",
            "child_services_view",
        ],
        "routes.case_management_parts.intake_income_support": [
            "load_intake_income_support",
            "upsert_intake_income_support",
            "recalculate_intake_income_support",
        ],
        "routes.resident_detail_parts.read": [
            "load_resident_for_shelter",
            "next_appointment_for_enrollment",
            "load_enrollment_context_for_shelter",
        ],
        "routes.resident_detail_parts.timeline": [
            "load_timeline",
            "build_calendar_context",
            "parse_anchor_date",
        ],
    }

    missing: list[str] = []

    for module_name, symbols in expected_symbols.items():
        module = importlib.import_module(module_name)
        for symbol in symbols:
            if not hasattr(module, symbol):
                missing.append(f"{module_name}.{symbol}")

    assert missing == []


def test_utcnow_iso_returns_utc_iso_string() -> None:
    value = utcnow_iso()

    assert isinstance(value, str)
    assert "T" in value
    assert not value.endswith("Z")
    if "+" in value:
        assert value.endswith("+00:00")
    assert value.count(":") >= 2


def test_failed_multi_table_write_rolls_back_everything(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE parent_records (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        core_db.db_execute(
            "CREATE TABLE child_records (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, note TEXT NOT NULL)"
        )

        with pytest.raises(RuntimeError, match="forced failure"), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO parent_records (id, name) VALUES (%s, %s)",
                (1, "parent written before failure"),
            )
            core_db.db_execute(
                "INSERT INTO child_records (parent_id, note) VALUES (%s, %s)",
                (1, "child written before failure"),
            )
            raise RuntimeError("forced failure")

        parent_rows = core_db.db_fetchall("SELECT id, name FROM parent_records")
        child_rows = core_db.db_fetchall("SELECT id, parent_id, note FROM child_records")

        assert parent_rows == []
        assert child_rows == []


def test_constraint_failure_rolls_back_prior_successful_writes(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, external_key TEXT NOT NULL UNIQUE, note TEXT NOT NULL)"
        )

        with pytest.raises(Exception), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO records (external_key, note) VALUES (%s, %s)",
                ("same-key", "first write should roll back"),
            )
            core_db.db_execute(
                "INSERT INTO records (external_key, note) VALUES (%s, %s)",
                ("same-key", "constraint failure"),
            )

        rows = core_db.db_fetchall("SELECT id, external_key, note FROM records")

        assert rows == []


def test_large_text_payload_is_not_truncated_on_commit(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    payload = "resident-notes-" + ("0123456789abcdef" * 4096)

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE large_payloads (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )

        with core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO large_payloads (payload) VALUES (%s)",
                (payload,),
            )

        row = core_db.db_fetchone(
            "SELECT payload, LENGTH(payload) AS payload_length FROM large_payloads WHERE id = %s",
            (1,),
        )

        assert row is not None
        assert row["payload_length"] == len(payload)
        assert row["payload"] == payload


def test_large_text_payload_rolls_back_cleanly_after_failure(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"
    payload = "rollback-payload-" + ("abcdef0123456789" * 4096)

    with app.app_context():
        core_db.db_execute(
            "CREATE TABLE large_payloads (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )

        with pytest.raises(RuntimeError, match="fail after large payload"), core_db.db_transaction():
            core_db.db_execute(
                "INSERT INTO large_payloads (payload) VALUES (%s)",
                (payload,),
            )
            raise RuntimeError("fail after large payload")

        rows = core_db.db_fetchall("SELECT id, payload FROM large_payloads")

        assert rows == []


def test_nested_failure_rolls_back_outer_transaction(app) -> None:
    app.config["DATABASE_URL"] = "sqlite:///:memory:"

    with app.app_context():
        core_db.db_execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

        with pytest.raises(RuntimeError, match="nested failure"):
            with core_db.db_transaction():
                core_db.db_execute(
                    "INSERT INTO items (name) VALUES (%s)",
                    ("outer write",),
                )
                with core_db.db_transaction():
                    core_db.db_execute(
                        "INSERT INTO items (name) VALUES (%s)",
                        ("inner write",),
                    )
                    raise RuntimeError("nested failure")

        rows = core_db.db_fetchall("SELECT id, name FROM items ORDER BY id")

        assert rows == []
