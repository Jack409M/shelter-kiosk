from __future__ import annotations

from core.app_factory import create_app
from core.db import db_fetchall
from db.migration_runner import (
    database_schema_is_compatible,
    get_current_schema_version,
    get_required_schema_version,
)


def main() -> int:
    app = create_app()

    with app.app_context():
        current_version = get_current_schema_version()
        required_version = get_required_schema_version()
        compatible = database_schema_is_compatible()

        rows = db_fetchall(
            """
            SELECT version, name, applied_at
            FROM schema_migrations
            ORDER BY version
            """
        )

        print("Migration status")
        print("----------------")
        print(f"Current version:  {current_version}")
        print(f"Required version: {required_version}")
        print(f"Compatible:       {compatible}")
        print("")

        if not rows:
            print("No applied migrations recorded.")
            return 1

        print("Applied migrations")
        print("------------------")
        for row in rows:
            version = row.get("version")
            name = row.get("name")
            applied_at = row.get("applied_at")
            print(f"{version}: {name}  applied_at={applied_at}")

        return 0 if compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())
