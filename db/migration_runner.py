from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import Final

from flask import current_app, g

from core.db import db_execute, db_fetchall, db_transaction, get_db


_SCHEMA_MIGRATIONS_POSTGRES_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""

_SCHEMA_MIGRATIONS_SQLITE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class MigrationDefinition:
    version: int
    name: str
    module_name: str
    module: ModuleType


def _utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _require_kind() -> str:
    kind_value = g.get("db_kind")
    if not kind_value:
        raise RuntimeError("Database kind is not set on flask.g")

    kind = str(kind_value).strip().lower()
    if kind not in {"pg", "sqlite"}:
        raise RuntimeError(f"Unsupported database kind: {kind!r}")

    return kind


def _sql_for_kind(kind: str) -> str:
    if kind == "pg":
        return _SCHEMA_MIGRATIONS_POSTGRES_SQL
    return _SCHEMA_MIGRATIONS_SQLITE_SQL


def _ensure_schema_migrations_table(kind: str) -> None:
    db_execute(_sql_for_kind(kind))


def _load_migration_package() -> ModuleType:
    try:
        return importlib.import_module("db.migrations")
    except Exception as exc:
        raise RuntimeError(
            "Failed to load migration package 'db.migrations'"
        ) from exc


def _iter_migration_module_names() -> list[str]:
    package = _load_migration_package()

    package_path = getattr(package, "__path__", None)
    if not package_path:
        raise RuntimeError(
            "Migration package has no __path__; cannot load migrations"
        )

    module_names: list[str] = []
    for module_info in pkgutil.iter_modules(
        package_path, prefix="db.migrations."
    ):
        full_name = str(module_info.name)
        short_name = full_name.rsplit(".", 1)[-1]

        if short_name == "__init__":
            continue

        module_names.append(full_name)

    return sorted(module_names)


def _coerce_migration_definition(module: ModuleType) -> MigrationDefinition:
    version = getattr(module, "VERSION", None)
    name = getattr(module, "NAME", None)
    apply_func = getattr(module, "apply", None)

    if not isinstance(version, int) or version <= 0:
        raise RuntimeError(
            f"Migration module {module.__name__} must define a positive integer VERSION."
        )

    if not isinstance(name, str) or not name.strip():
        raise RuntimeError(
            f"Migration module {module.__name__} must define a non empty NAME."
        )

    if not callable(apply_func):
        raise RuntimeError(
            f"Migration module {module.__name__} must define an apply(kind) function."
        )

    return MigrationDefinition(
        version=version,
        name=name.strip(),
        module_name=module.__name__,
        module=module,
    )


def _load_migration_definitions() -> list[MigrationDefinition]:
    definitions: list[MigrationDefinition] = []

    for module_name in _iter_migration_module_names():
        module = importlib.import_module(module_name)
        definitions.append(_coerce_migration_definition(module))

    if not definitions:
        raise RuntimeError("No migration definitions found in db.migrations")

    definitions.sort(key=lambda item: item.version)

    seen_versions: set[int] = set()
    for definition in definitions:
        if definition.version in seen_versions:
            raise RuntimeError(
                f"Duplicate migration version detected: {definition.version}"
            )
        seen_versions.add(definition.version)

    return definitions


def _fetch_applied_migrations() -> dict[int, dict[str, object]]:
    rows = db_fetchall(
        """
        SELECT version, name, applied_at
        FROM schema_migrations
        ORDER BY version
        """
    )

    applied: dict[int, dict[str, object]] = {}
    for row in rows:
        version_value = row.get("version")
        if version_value is None:
            continue

        version = int(version_value)
        applied[version] = row

    return applied


def _record_applied_migration(kind: str, definition: MigrationDefinition) -> None:
    sql = (
        """
        INSERT INTO schema_migrations (version, name, applied_at)
        VALUES (%s, %s, %s)
        """
        if kind == "pg"
        else
        """
        INSERT INTO schema_migrations (version, name, applied_at)
        VALUES (?, ?, ?)
        """
    )

    db_execute(
        sql,
        (
            definition.version,
            definition.name,
            _utcnow_iso(),
        ),
    )


def _apply_one_migration(kind: str, definition: MigrationDefinition) -> None:
    current_app.logger.info(
        "Applying migration version=%s name=%s module=%s",
        definition.version,
        definition.name,
        definition.module_name,
    )

    with db_transaction():
        definition.module.apply(kind)
        _record_applied_migration(kind, definition)

    current_app.logger.info(
        "Applied migration version=%s name=%s",
        definition.version,
        definition.name,
    )


def apply_pending_migrations() -> list[int]:
    get_db()
    kind = _require_kind()

    _ensure_schema_migrations_table(kind)

    definitions = _load_migration_definitions()
    applied = _fetch_applied_migrations()

    applied_versions_now: list[int] = []

    for definition in definitions:
        existing = applied.get(definition.version)
        if existing is not None:
            existing_name = str(existing.get("name") or "").strip()
            if existing_name and existing_name != definition.name:
                raise RuntimeError(
                    f"Applied migration mismatch version={definition.version}"
                )
            continue

        _apply_one_migration(kind, definition)
        applied_versions_now.append(definition.version)

    return applied_versions_now


def get_current_schema_version() -> int:
    get_db()
    kind = _require_kind()
    _ensure_schema_migrations_table(kind)

    rows = db_fetchall(
        """
        SELECT version
        FROM schema_migrations
        ORDER BY version DESC
        """
    )

    if not rows:
        return 0

    return int(rows[0]["version"])


def get_required_schema_version() -> int:
    definitions = _load_migration_definitions()
    return definitions[-1].version


def database_schema_is_compatible() -> bool:
    current = get_current_schema_version()
    required = get_required_schema_version()

    if current < required:
        return False

    if current > required:
        raise RuntimeError(
            f"Database schema version {current} is newer than code version {required}"
        )

    return True
