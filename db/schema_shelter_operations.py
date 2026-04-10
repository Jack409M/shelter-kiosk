from __future__ import annotations

from core.db import db_execute

from .schema_helpers import create_table


def ensure_chore_tables(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS chore_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            name TEXT NOT NULL,
            when_time TEXT,
            default_day TEXT,
            description TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS chore_templates (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            name TEXT NOT NULL,
            when_time TEXT,
            default_day TEXT,
            description TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
    )

    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS chore_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            chore_id INTEGER NOT NULL,
            assigned_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (resident_id) REFERENCES residents(id),
            FOREIGN KEY (chore_id) REFERENCES chore_templates(id)
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS chore_assignments (
            id SERIAL PRIMARY KEY,
            resident_id INTEGER NOT NULL REFERENCES residents(id),
            chore_id INTEGER NOT NULL REFERENCES chore_templates(id),
            assigned_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_kiosk_activity_category_tables(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            activity_label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            counts_as_work_hours INTEGER NOT NULL DEFAULT 0,
            counts_as_productive_hours INTEGER NOT NULL DEFAULT 0,
            weekly_cap_hours REAL,
            requires_approved_pass INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS kiosk_activity_categories (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            activity_label TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            counts_as_work_hours BOOLEAN NOT NULL DEFAULT FALSE,
            counts_as_productive_hours BOOLEAN NOT NULL DEFAULT FALSE,
            weekly_cap_hours DOUBLE PRECISION,
            requires_approved_pass BOOLEAN NOT NULL DEFAULT FALSE,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_kiosk_activity_child_option_tables(kind: str) -> None:
    create_table(
        kind,

        # SQLite
        """
        CREATE TABLE IF NOT EXISTS kiosk_activity_child_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shelter TEXT NOT NULL,
            parent_activity_label TEXT NOT NULL,
            option_label TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,

        # PostgreSQL
        """
        CREATE TABLE IF NOT EXISTS kiosk_activity_child_options (
            id SERIAL PRIMARY KEY,
            shelter TEXT NOT NULL,
            parent_activity_label TEXT NOT NULL,
            option_label TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )


def ensure_chore_template_columns() -> None:
    statements = [
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS when_time TEXT",
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS default_day TEXT",
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0",
        "ALTER TABLE chore_templates ADD COLUMN IF NOT EXISTS created_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_chore_assignment_columns() -> None:
    statements = [
        "ALTER TABLE chore_assignments ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'assigned'",
        "ALTER TABLE chore_assignments ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE chore_assignments ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE chore_assignments ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_kiosk_activity_category_columns() -> None:
    statements = [
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS activity_label TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS counts_as_work_hours INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS counts_as_productive_hours INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS weekly_cap_hours DOUBLE PRECISION",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS requires_approved_pass INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE kiosk_activity_categories ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_kiosk_activity_child_option_columns() -> None:
    statements = [
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS parent_activity_label TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS option_label TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE kiosk_activity_child_options ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]

    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def ensure_default_kiosk_activity_categories(kind: str) -> None:
    seed_map = {
        "haven house": [
            ("Employment", 1, 1, None, 0),
            ("RAD", 1, 1, None, 0),
            ("Job Search", 0, 1, None, 0),
            ("AA or NA Meeting", 0, 1, None, 0),
            ("Church", 0, 1, None, 0),
            ("Doctor Appointment", 0, 1, None, 0),
            ("Counseling", 0, 1, None, 0),
            ("Step Work", 0, 1, 2.0, 0),
            ("Sponsor Meeting", 0, 1, 1.0, 0),
            ("Volunteer or Community Service", 0, 1, None, 0),
            ("School", 0, 1, None, 0),
            ("Legal Obligation", 0, 1, None, 0),
            ("Store", 0, 0, None, 0),
            ("Pass", 0, 0, None, 1),
            ("Other Approved Activity", 0, 0, None, 0),
        ],
        "gratitude house": [
            ("Employment", 1, 1, None, 0),
            ("Job Search", 0, 1, None, 0),
            ("AA or NA Meeting", 0, 1, None, 0),
            ("Church", 0, 1, None, 0),
            ("Doctor Appointment", 0, 1, None, 0),
            ("Counseling", 0, 1, None, 0),
            ("Step Work", 0, 1, 2.0, 0),
            ("Sponsor Meeting", 0, 1, 1.0, 0),
            ("Volunteer or Community Service", 0, 1, None, 0),
            ("School", 0, 1, None, 0),
            ("Daycare or School Drop Off", 0, 0, None, 0),
            ("Legal Obligation", 0, 1, None, 0),
            ("Store", 0, 0, None, 0),
            ("Pass", 0, 0, None, 1),
            ("Other Approved Activity", 0, 0, None, 0),
        ],
        "abba house": [
            ("Employment", 1, 1, None, 0),
            ("Job Search", 0, 1, None, 0),
            ("AA or NA Meeting", 0, 1, None, 0),
            ("Church", 0, 1, None, 0),
            ("Doctor Appointment", 0, 1, None, 0),
            ("Counseling", 0, 1, None, 0),
            ("Step Work", 0, 1, 2.0, 0),
            ("Sponsor Meeting", 0, 1, 1.0, 0),
            ("Volunteer or Community Service", 0, 1, None, 0),
            ("School", 0, 1, None, 0),
            ("Daycare or School Drop Off", 0, 0, None, 0),
            ("Legal Obligation", 0, 1, None, 0),
            ("Store", 0, 0, None, 0),
            ("Pass", 0, 0, None, 1),
            ("Free Time", 0, 0, None, 0),
            ("Other Approved Activity", 0, 0, None, 0),
        ],
    }

    now = "1970-01-01T00:00:00"

    for shelter, rows in seed_map.items():
        existing = None
        try:
            existing = db_execute(
                "SELECT 1"
            )
        except Exception:
            pass

        try:
            count_row = db_execute(
                "SELECT 1"
            )
        except Exception:
            count_row = None

        from core.db import db_fetchone

        placeholder = "%s" if kind == "pg" else "?"
        count_row = db_fetchone(
            f"""
            SELECT COUNT(*) AS row_count
            FROM kiosk_activity_categories
            WHERE LOWER(COALESCE(shelter, '')) = {placeholder}
            """,
            (shelter,),
        )
        row_count = int((count_row or {}).get("row_count") or 0)

        if row_count > 0:
            continue

        for sort_order, row in enumerate(rows, start=1):
            label, counts_work, counts_productive, weekly_cap_hours, requires_pass = row
            db_execute(
                (
                    """
                    INSERT INTO kiosk_activity_categories (
                        shelter,
                        activity_label,
                        active,
                        sort_order,
                        counts_as_work_hours,
                        counts_as_productive_hours,
                        weekly_cap_hours,
                        requires_approved_pass,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    if kind == "pg"
                    else
                    """
                    INSERT INTO kiosk_activity_categories (
                        shelter,
                        activity_label,
                        active,
                        sort_order,
                        counts_as_work_hours,
                        counts_as_productive_hours,
                        weekly_cap_hours,
                        requires_approved_pass,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    shelter,
                    label,
                    True if kind == "pg" else 1,
                    sort_order,
                    bool(counts_work) if kind == "pg" else int(bool(counts_work)),
                    bool(counts_productive) if kind == "pg" else int(bool(counts_productive)),
                    weekly_cap_hours,
                    bool(requires_pass) if kind == "pg" else int(bool(requires_pass)),
                    None,
                    now,
                    now,
                ),
            )


def ensure_default_kiosk_activity_child_options(kind: str) -> None:
    seed_map = {
        "haven house": [
            "Touch of Soul",
            "Clean Air",
            "12 Steps",
            "Moss",
            "Hobbs",
            "Serenity",
            "Nothing to Fear",
            "No Matter What",
            "Top of Texas",
            "DWC House Meting",
            "Online",
            "Other",
            "None",
        ],
        "gratitude house": [
            "Touch of Soul",
            "Clean Air",
            "12 Steps",
            "Moss",
            "Hobbs",
            "Serenity",
            "Nothing to Fear",
            "No Matter What",
            "Top of Texas",
            "DWC House Meting",
            "Online",
            "Other",
            "None",
        ],
        "abba house": [
            "Touch of Soul",
            "Clean Air",
            "12 Steps",
            "Moss",
            "Hobbs",
            "Serenity",
            "Nothing to Fear",
            "No Matter What",
            "Top of Texas",
            "DWC House Meting",
            "Online",
            "Other",
            "None",
        ],
    }

    now = "1970-01-01T00:00:00"
    parent_label = "AA or NA Meeting"

    from core.db import db_fetchone

    placeholder = "%s" if kind == "pg" else "?"

    for shelter, rows in seed_map.items():
        count_row = db_fetchone(
            f"""
            SELECT COUNT(*) AS row_count
            FROM kiosk_activity_child_options
            WHERE LOWER(COALESCE(shelter, '')) = {placeholder}
              AND LOWER(COALESCE(parent_activity_label, '')) = {placeholder}
            """,
            (shelter, parent_label.lower()),
        )
        row_count = int((count_row or {}).get("row_count") or 0)

        if row_count > 0:
            continue

        for sort_order, option_label in enumerate(rows, start=1):
            db_execute(
                (
                    """
                    INSERT INTO kiosk_activity_child_options (
                        shelter,
                        parent_activity_label,
                        option_label,
                        active,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    if kind == "pg"
                    else
                    """
                    INSERT INTO kiosk_activity_child_options (
                        shelter,
                        parent_activity_label,
                        option_label,
                        active,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    shelter,
                    parent_label,
                    option_label,
                    True if kind == "pg" else 1,
                    sort_order,
                    now,
                    now,
                ),
            )


def ensure_indexes() -> None:
    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_shelter_idx
            ON chore_templates (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_active_idx
            ON chore_templates (active)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_shelter_active_sort_idx
            ON chore_templates (shelter, active, sort_order)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_templates_default_day_idx
            ON chore_templates (default_day)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_resident_idx
            ON chore_assignments (resident_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_chore_idx
            ON chore_assignments (chore_id)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_assigned_date_idx
            ON chore_assignments (assigned_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_status_idx
            ON chore_assignments (status)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS chore_assignments_resident_date_idx
            ON chore_assignments (resident_id, assigned_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS chore_assignments_resident_chore_date_uniq
            ON chore_assignments (resident_id, chore_id, assigned_date)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS kiosk_activity_categories_shelter_idx
            ON kiosk_activity_categories (shelter)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS kiosk_activity_categories_shelter_active_sort_idx
            ON kiosk_activity_categories (shelter, active, sort_order)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS kiosk_activity_child_options_shelter_parent_idx
            ON kiosk_activity_child_options (shelter, parent_activity_label)
            """
        )
    except Exception:
        pass

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS kiosk_activity_child_options_shelter_parent_active_sort_idx
            ON kiosk_activity_child_options (shelter, parent_activity_label, active, sort_order)
            """
        )
    except Exception:
        pass


def ensure_tables(kind: str) -> None:
    ensure_chore_tables(kind)
    ensure_kiosk_activity_category_tables(kind)
    ensure_kiosk_activity_child_option_tables(kind)
    ensure_chore_template_columns()
    ensure_chore_assignment_columns()
    ensure_kiosk_activity_category_columns()
    ensure_kiosk_activity_child_option_columns()
    ensure_default_kiosk_activity_categories(kind)
    ensure_default_kiosk_activity_child_options(kind)
