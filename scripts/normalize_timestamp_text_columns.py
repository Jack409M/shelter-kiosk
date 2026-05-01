from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from typing import Any

from flask import g

from core.app_factory import create_app
from core.db import db_execute, db_fetchall, db_transaction

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

TIMESTAMP_COLUMN_NAMES = {
    "actual_obligation_end_time",
    "approved_at",
    "created_at",
    "delete_after_at",
    "employment_updated_at",
    "event_time",
    "expected_back_time",
    "failed_at",
    "last_backup_at",
    "last_login_at",
    "last_seen_at",
    "needed_at",
    "obligation_end_time",
    "obligation_start_time",
    "read_at",
    "reviewed_at",
    "scheduled_at",
    "sent_at",
    "sms_opt_in_at",
    "sms_opt_out_at",
    "submitted_at",
    "transferred_at",
    "updated_at",
}

TIMESTAMP_COLUMN_SUFFIXES = (
    "_at",
    "_time",
)

SKIP_COLUMN_NAMES = {
    "start_date",
    "end_date",
    "entry_date",
    "exit_date",
    "request_date",
    "service_date",
    "date_entered",
    "date_exit_dwc",
    "birth_date",
    "dob",
    "when_time",
}

TEXT_TYPES = {
    "character varying",
    "varchar",
    "text",
    "char",
    "character",
    "citext",
}


def _clean_identifier(value: str) -> str:
    if not IDENTIFIER_RE.match(value or ""):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _quoted_identifier(value: str) -> str:
    return f'"{_clean_identifier(value)}"'


def _is_timestamp_column(column_name: str) -> bool:
    normalized = column_name.strip().lower()
    if normalized in SKIP_COLUMN_NAMES:
        return False
    if normalized in TIMESTAMP_COLUMN_NAMES:
        return True
    return normalized.endswith(TIMESTAMP_COLUMN_SUFFIXES)


def _table_columns_sqlite(table_name: str) -> list[dict[str, Any]]:
    rows = db_fetchall(f"PRAGMA table_info({_quoted_identifier(table_name)})")
    columns: list[dict[str, Any]] = []
    for row in rows or []:
        column_name = str(row.get("name") or "").strip()
        column_type = str(row.get("type") or "").strip().lower()
        if column_name:
            columns.append({"name": column_name, "type": column_type})
    return columns


def _list_tables_sqlite() -> list[str]:
    rows = db_fetchall(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [str(row["name"]) for row in rows or []]


def _list_timestamp_targets_sqlite() -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for table_name in _list_tables_sqlite():
        column_names = {column["name"] for column in _table_columns_sqlite(table_name)}
        if "id" not in column_names:
            continue
        for column in _table_columns_sqlite(table_name):
            column_name = str(column["name"])
            column_type = str(column["type"])
            if not _is_timestamp_column(column_name):
                continue
            if column_type and "text" not in column_type and "char" not in column_type:
                continue
            targets.append((table_name, column_name))
    return targets


def _list_timestamp_targets_pg() -> list[tuple[str, str]]:
    rows = db_fetchall(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )

    tables_with_id = {
        str(row["table_name"])
        for row in rows or []
        if str(row["column_name"] or "").strip().lower() == "id"
    }

    targets: list[tuple[str, str]] = []
    for row in rows or []:
        table_name = str(row["table_name"] or "").strip()
        column_name = str(row["column_name"] or "").strip()
        data_type = str(row["data_type"] or "").strip().lower()

        if table_name not in tables_with_id:
            continue
        if not _is_timestamp_column(column_name):
            continue
        if data_type not in TEXT_TYPES:
            continue

        targets.append((table_name, column_name))

    return targets


def _list_timestamp_targets() -> list[tuple[str, str]]:
    if g.get("db_kind") == "pg":
        return _list_timestamp_targets_pg()
    return _list_timestamp_targets_sqlite()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if len(raw) <= 10:
            return None

        candidate = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)

    return parsed.replace(microsecond=0)


def _normalize_timestamp(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="seconds")


def _load_column_values(table_name: str, column_name: str) -> list[dict[str, Any]]:
    table_sql = _quoted_identifier(table_name)
    column_sql = _quoted_identifier(column_name)

    return db_fetchall(
        f"""
        SELECT id, {column_sql} AS value
        FROM {table_sql}
        WHERE {column_sql} IS NOT NULL
          AND TRIM(CAST({column_sql} AS TEXT)) <> ''
        ORDER BY id
        """
    )


def _update_value(table_name: str, column_name: str, row_id: int, normalized_value: str) -> None:
    table_sql = _quoted_identifier(table_name)
    column_sql = _quoted_identifier(column_name)

    db_execute(
        f"""
        UPDATE {table_sql}
        SET {column_sql} = %s
        WHERE id = %s
        """,
        (normalized_value, row_id),
    )


def normalize_timestamp_columns(*, apply: bool) -> dict[str, int]:
    targets = _list_timestamp_targets()
    scanned = 0
    would_update = 0
    updated = 0
    skipped = 0

    print(f"Discovered {len(targets)} timestamp-like text columns.")

    with db_transaction():
        for table_name, column_name in targets:
            rows = _load_column_values(table_name, column_name)
            column_changes = 0

            for row in rows or []:
                scanned += 1
                row_id = int(row["id"])
                original = row.get("value")
                normalized = _normalize_timestamp(original)

                if normalized is None:
                    skipped += 1
                    continue

                if str(original).strip() == normalized:
                    continue

                would_update += 1
                column_changes += 1

                if apply:
                    _update_value(table_name, column_name, row_id, normalized)
                    updated += 1

            if column_changes:
                action = "updated" if apply else "would update"
                print(f"{table_name}.{column_name}: {action} {column_changes} row(s)")

        if not apply:
            raise RuntimeError("Dry run complete. No database changes were written.")

    return {
        "columns": len(targets),
        "scanned": scanned,
        "would_update": would_update,
        "updated": updated,
        "skipped": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize timestamp text columns to UTC naive ISO format."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write normalized timestamp values. Without this flag, the script is a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = create_app()

    with app.app_context():
        try:
            summary = normalize_timestamp_columns(apply=bool(args.apply))
        except RuntimeError as err:
            if str(err).startswith("Dry run complete"):
                print(str(err))
                return
            raise

    print("Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
