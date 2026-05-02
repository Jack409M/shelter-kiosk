from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.db import db_execute, db_fetchall, db_transaction
from core.time_utils import utc_naive_iso

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

POSTGRES_DB_KINDS = {"pg", "postgres", "postgresql"}

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

TIMESTAMP_COLUMN_SUFFIXES = ("_at", "_time")

SKIP_COLUMN_NAMES = {
    "birth_date",
    "date_entered",
    "date_exit_dwc",
    "dob",
    "end_date",
    "entry_date",
    "exit_date",
    "request_date",
    "service_date",
    "start_date",
    "when_time",
}

TEXT_TYPES = {
    "char",
    "character",
    "character varying",
    "citext",
    "text",
    "varchar",
}


@dataclass(slots=True)
class TimestampColumnResult:
    table_name: str
    column_name: str
    scanned: int = 0
    would_update: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass(slots=True)
class TimestampNormalizationResult:
    applied: bool
    columns_discovered: int = 0
    scanned: int = 0
    would_update: int = 0
    updated: int = 0
    skipped: int = 0
    details: list[TimestampColumnResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "columns_discovered": self.columns_discovered,
            "scanned": self.scanned,
            "would_update": self.would_update,
            "updated": self.updated,
            "skipped": self.skipped,
            "details": [
                {
                    "table_name": detail.table_name,
                    "column_name": detail.column_name,
                    "scanned": detail.scanned,
                    "would_update": detail.would_update,
                    "updated": detail.updated,
                    "skipped": detail.skipped,
                }
                for detail in self.details
            ],
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
        columns = _table_columns_sqlite(table_name)
        column_names = {str(column["name"]) for column in columns}

        if "id" not in column_names:
            continue

        for column in columns:
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


def _db_kind() -> str:
    import os
    url = str(os.environ.get("DATABASE_URL") or "").lower()
    if url.startswith("postgres"):
        return "postgres"
    return ""


def list_timestamp_targets() -> list[tuple[str, str]]:
    if _db_kind() in POSTGRES_DB_KINDS:
        return _list_timestamp_targets_pg()
    return _list_timestamp_targets_sqlite()


def normalize_timestamp_value(value: Any) -> str | None:
    if value is None:
        return None

    if not hasattr(value, "tzinfo"):
        raw = str(value or "").strip()
        if not raw or len(raw) <= 10:
            return None

    return utc_naive_iso(value)


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


def normalize_timestamp_columns(*, apply: bool) -> TimestampNormalizationResult:
    targets = list_timestamp_targets()
    result = TimestampNormalizationResult(
        applied=apply,
        columns_discovered=len(targets),
    )

    transaction_context = db_transaction() if apply else None

    if transaction_context is None:
        return _normalize_timestamp_columns_inner(targets, apply=False, result=result)

    with transaction_context:
        return _normalize_timestamp_columns_inner(targets, apply=True, result=result)


def _normalize_timestamp_columns_inner(
    targets: list[tuple[str, str]],
    *,
    apply: bool,
    result: TimestampNormalizationResult,
) -> TimestampNormalizationResult:
    for table_name, column_name in targets:
        detail = TimestampColumnResult(table_name=table_name, column_name=column_name)
        rows = _load_column_values(table_name, column_name)

        for row in rows or []:
            detail.scanned += 1
            result.scanned += 1

            row_id = int(row["id"])
            original = row.get("value")
            normalized = normalize_timestamp_value(original)

            if normalized is None:
                detail.skipped += 1
                result.skipped += 1
                continue

            if str(original).strip() == normalized:
                continue

            detail.would_update += 1
            result.would_update += 1

            if apply:
                _update_value(table_name, column_name, row_id, normalized)
                detail.updated += 1
                result.updated += 1

        if detail.scanned or detail.would_update or detail.skipped or detail.updated:
            result.details.append(detail)

    return result
