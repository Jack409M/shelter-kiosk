from __future__ import annotations

from core.db import db_execute
from db import migration_runner


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
            raise AssertionError("Expected applied migration name mismatch to raise RuntimeError")
        except RuntimeError as exc:
            # ✅ Updated to match real message
            assert "Applied migration mismatch" in str(exc)
