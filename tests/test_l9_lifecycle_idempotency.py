from core.l9_support_lifecycle import start_level9_lifecycle
from core.db import db_fetchone


def test_start_level9_lifecycle_is_idempotent(db_session, test_resident, test_enrollment):
    """
    Calling start_level9_lifecycle twice should not create duplicates.
    """

    resident_id = test_resident.id
    enrollment_id = test_enrollment.id
    shelter = test_resident.shelter

    # First call
    first = start_level9_lifecycle(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        shelter=shelter,
    )

    # Second call (should NOT create new)
    second = start_level9_lifecycle(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        shelter=shelter,
    )

    # Both should point to same lifecycle
    assert first["id"] == second["id"]

    # Verify only ONE row exists
    row = db_fetchone(
        "SELECT COUNT(*) as count FROM level9_support_lifecycles WHERE enrollment_id = ?",
        (enrollment_id,),
    )

    assert row["count"] == 1
  
