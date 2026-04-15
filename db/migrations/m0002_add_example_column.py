VERSION = 2
NAME = "add_example_column_to_staff_users"

def apply(kind: str):
    from core.db import db_execute

    if kind == "pg":
        sql = """
        ALTER TABLE staff_users
        ADD COLUMN IF NOT EXISTS example_flag BOOLEAN DEFAULT FALSE
        """
    else:
        sql = """
        ALTER TABLE staff_users
        ADD COLUMN example_flag INTEGER DEFAULT 0
        """

    db_execute(sql)
