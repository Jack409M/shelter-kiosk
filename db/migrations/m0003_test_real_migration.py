VERSION = 3
NAME = "add_test_column_to_audit_log"


def apply(kind: str) -> None:
    from core.db import db_execute

    sql = (
        "ALTER TABLE audit_log ADD COLUMN test_column TEXT"
        if kind == "sqlite"
        else "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS test_column TEXT"
    )

    db_execute(sql)
