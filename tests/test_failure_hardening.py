from __future__ import annotations

from pathlib import Path

import pytest

from core import db as core_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PYTHON_ROOTS = (
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "routes",
    PROJECT_ROOT / "db",
)


def test_no_datetime_utcnow_in_production_code() -> None:
    offenders: list[str] = []

    for root in PRODUCTION_PYTHON_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "datetime.utcnow" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


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
