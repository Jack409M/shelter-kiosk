"""
DWC Shelter Operations System
People Schema

This module defines tables related to residents and their family structure.

Tables
------

residents
Primary resident record.

resident_children
Child records associated with a resident.

resident_substances
Substance history records for a resident.
"""

from core.db import db_execute


def init_schema_people():
    """
    Initialize people related database tables.
    """

    # ------------------------------------------------------------------
    # Residents
    # ------------------------------------------------------------------

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS residents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            shelter TEXT NOT NULL,
            resident_identifier TEXT,
            resident_code TEXT,

            first_name TEXT,
            last_name TEXT,

            dob TEXT,
            birth_year INTEGER,

            phone TEXT,
            email TEXT,

            emergency_contact_name TEXT,
            emergency_contact_relationship TEXT,
            emergency_contact_phone TEXT,

            medical_alerts TEXT,
            medical_notes TEXT,

            gender TEXT,
            race TEXT,
            veteran INTEGER DEFAULT 0,
            disability INTEGER DEFAULT 0,
            marital_status TEXT,

            city TEXT,
            last_zipcode_of_residence TEXT,

            place_staying_before_entry TEXT,
            length_of_time_in_amarillo_upon_entry TEXT,

            date_entered TEXT,
            date_exit_dwc TEXT,

            graduate_dwc INTEGER DEFAULT 0,
            reason_for_exit TEXT,
            leave_ama_upon_exit INTEGER DEFAULT 0,

            status TEXT,

            is_active INTEGER DEFAULT 1,

            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    # Indexes for reporting performance
    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_residents_shelter
        ON residents (shelter)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_residents_status
        ON residents (status)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_residents_entry
        ON residents (date_entered)
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_residents_exit
        ON residents (date_exit_dwc)
        """
    )

    # ------------------------------------------------------------------
    # Resident Children
    # ------------------------------------------------------------------

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS resident_children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            resident_id INTEGER NOT NULL,

            child_name TEXT,
            birth_year INTEGER,

            relationship TEXT,

            living_status TEXT,

            is_active INTEGER DEFAULT 1,

            notes TEXT,

            created_at TEXT,
            updated_at TEXT,

            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_children_resident
        ON resident_children (resident_id)
        """
    )

    # ------------------------------------------------------------------
    # Resident Substances
    # ------------------------------------------------------------------

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS resident_substances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            resident_id INTEGER NOT NULL,

            substance TEXT,
            is_primary INTEGER DEFAULT 0,

            created_at TEXT,
            updated_at TEXT,

            FOREIGN KEY (resident_id) REFERENCES residents(id)
        )
        """
    )

    db_execute(
        """
        CREATE INDEX IF NOT EXISTS idx_substances_resident
        ON resident_substances (resident_id)
        """
    )
