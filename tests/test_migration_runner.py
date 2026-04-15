from __future__ import annotations

from core.db import db_execute, db_fetchall
from db import migration_runner


def test_migration_runner_applies_baseline_once(app):
    with app.app_context():
        import core.db as db_module
        import core.runtime as runtime
        from db import schema

        runtime._DB_INITIALIZED = False
        runtime._DB_INIT_URL = None
        db_module.PG_POOL = None
        schema._SCHEMA_INITIALIZED_KEY = None

        applied_versions = migration_runner.apply_pending_migrations()

        assert applied_versions == [1]
        assert migration_runner.get_current_schema_version() == 1
        assert migration_runner.get_required_schema_version() == 1
        assert migration_runner.database_schema_is_compatible() is True

        rows = db_fetchall(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version
            """
        )

        assert len(rows) == 1
        assert int(rows[0]["version"]) == 1
        assert rows[0]["name"] == "baseline"


def test_migration_runner_is_idempotent_after_baseline(app):
    with app.app_context():
        import core.db as db_module
        import core.runtime as runtime
        from db import schema

        runtime._DB_INITIALIZED = False
        runtime._DB_INIT_URL = None
        db_module.PG_POOL = None
        schema._SCHEMA_INITIALIZED_KEY = None

        first_applied = migration_runner.apply_pending_migrations()
        second_applied = migration_runner.apply_pending_migrations()

        assert first_applied == [1]
        assert second_applied == []

        rows = db_fetchall(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version
            """
        )

        assert len(rows) == 1
        assert int(rows[0]["version"]) == 1
        assert rows[0]["name"] == "baseline"


def test_runtime_init_db_applies_migrations_and_keeps_schema_compatible(app):
    import core.db as db_module
    import core.runtime as runtime
    from db import schema

    with app.app_context():
        runtime._DB_INITIALIZED = False
        runtime._DB_INIT_URL = None
        db_module.PG_POOL = None
        schema._SCHEMA_INITIALIZED_KEY = None

        runtime.init_db()

        assert migration_runner.get_current_schema_version() == 1
        assert migration_runner.get_required_schema_version() == 1
        assert migration_runner.database_schema_is_compatible() is True

        rows = db_fetchall(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version
            """
        )

        assert len(rows) == 1
        assert int(rows[0]["version"]) == 1
        assert rows[0]["name"] == "baseline"


def test_migration_runner_detects_applied_name_mismatch(app, monkeypatch):
    with app.app_context():
        import core.db as db_module
        import core.runtime as runtime
        from db import schema

        runtime._DB_INITIALIZED = False
        runtime._DB_INIT_URL = None
        db_module.PG_POOL = None
        schema._SCHEMA_INITIALIZED_KEY = None

        migration_runner.apply_pending_migrations()

        db_execute(
            """
            UPDATE schema_migrations
            SET name = %s
            WHERE version = %s
            """,
            ("wrong_name", 1),
        )

        original_loader = migration_runner._load_migration_definitions

        def _patched_loader():
            return original_loader()

        monkeypatch.setattr(
            migration_runner,
            "_load_migration_definitions",
            _patched_loader,
        )

        try:
            migration_runner.apply_pending_migrations()
            raise AssertionError(
                "Expected applied migration name mismatch to raise RuntimeError"
            )
        except RuntimeError as exc:
            assert "Applied migration name mismatch" in str(exc)
