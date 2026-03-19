# core/field_registry.py

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class FieldDefinition:
    key: str
    label: str

    # where collected
    form_page: Optional[str] = None
    form_field: Optional[str] = None

    # where stored
    table: Optional[str] = None
    column: Optional[str] = None

    # reporting usage
    used_in_stats: bool = False

    # notes
    notes: Optional[str] = None


# ------------------------------------------------------------
# MASTER REGISTRY (seeded from your spreadsheet)
# ------------------------------------------------------------

FIELDS: List[FieldDefinition] = [

    # --- CORE DEMOGRAPHICS (CONFIRMED WIRED) ---
    FieldDefinition(
        key="first_name",
        label="First Name",
        form_page="intake_assessment",
        form_field="first_name",
        table="residents",
        column="first_name",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="last_name",
        label="Last Name",
        form_page="intake_assessment",
        form_field="last_name",
        table="residents",
        column="last_name",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="date_entered",
        label="Date Entered",
        form_page="intake_assessment",
        form_field="date_entered",
        table="program_enrollments",
        column="entry_date",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="sobriety_date",
        label="Sobriety Date",
        form_page="intake_assessment",
        form_field="sobriety_date",
        table="intake_assessments",
        column="sobriety_date",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="race",
        label="Race",
        form_page="intake_assessment",
        form_field="race",
        table="intake_assessments",
        column="race",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="gender",
        label="Gender",
        form_page="intake_assessment",
        form_field="gender",
        table="intake_assessments",
        column="gender",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="veteran",
        label="Veteran",
        form_page="intake_assessment",
        form_field="veteran",
        table="intake_assessments",
        column="veteran",
        used_in_stats=True,
    ),
    FieldDefinition(
        key="disability",
        label="Disability",
        form_page="intake_assessment",
        form_field="disability",
        table="intake_assessments",
        column="disability",
        used_in_stats=True,
    ),

    # --- PARTIAL / NOT WIRED YET ---
    FieldDefinition(
        key="date_exit_dwc",
        label="Date Exit DWC",
        table="exit_assessments",
        column="exit_date",
        used_in_stats=True,
        notes="Schema exists but no form or route"
    ),
    FieldDefinition(
        key="reason_for_exit",
        label="Reason for Exit",
        table="exit_assessments",
        column="exit_reason",
        used_in_stats=True,
        notes="Not collected anywhere yet"
    ),

    # --- EXAMPLE UNWIRED ---
    FieldDefinition(
        key="grit_at_exit",
        label="Grit at Exit",
        notes="Not implemented anywhere"
    ),

    # ------------------------------------------------------------
    # 🔥 YOU WILL CONTINUE ADDING FROM YOUR SPREADSHEET
    # ------------------------------------------------------------
]


def get_all_fields() -> List[FieldDefinition]:
    return FIELDS
