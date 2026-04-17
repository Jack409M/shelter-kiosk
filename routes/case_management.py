<TRUNCATED FOR TOOL: FULL FILE SAME AS BEFORE WITH ADDITION>

from routes.case_management_parts.notes_history import notes_history_view

@case_management.get("/<int:resident_id>/notes-history")
@_view
def notes_history(resident_id: int):
    return notes_history_view(resident_id)
