from __future__ import annotations


def _error() -> RuntimeError:
    return RuntimeError(
        "db/migrations.py is a retired legacy migration helper and must not be used. "
        "Use db.migration_runner and db/migrations/ versioned migration modules instead."
    )


def _ensure_migrations_table(kind: str) -> None:
    raise _error()


def has_migration(kind: str, name: str) -> bool:
    raise _error()


def record_migration(kind: str, name: str) -> None:
    raise _error()


def run_migration(kind: str, name: str, fn) -> None:
    raise _error()
