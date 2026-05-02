from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.admin_rbac import require_admin_role
from core.audit import log_action

RESTORE_NOTES_CONFIRM_PHRASE = "SAVE RESTORE NOTES"


def _staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid staff_user_id in session for backup documentation route: %r",
            raw_staff_user_id,
        )
        return None


def admin_backup_documentation_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    backup_summary = {
        "hosting_backup": "Railway production database backups are performed daily.",
        "local_backup": "A daily backup copy is also saved to the authorized local computer.",
        "restore_testing": "Backups are tested to confirm that the file is not corrupted and can be restored.",
        "validation_workflow": "The repository includes a sanitized backup restore validation workflow for testing a backup against a disposable database before trusting it.",
    }

    restore_boundaries = [
        "Do not restore directly into the production database from the application UI.",
        "Validate the backup in a disposable database before any production recovery decision.",
        "Confirm the backup date, source, file size, and restore test result before using it for recovery.",
        "Keep production credentials out of GitHub Actions, screenshots, tickets, chat messages, and documentation.",
    ]

    daily_checklist = [
        "Confirm Railway daily backup completed.",
        "Confirm local daily backup copy exists on the authorized computer.",
        "Confirm the backup file opens or decompresses without corruption warnings.",
        "Confirm the most recent restore test completed successfully.",
        "Record any failure, skipped backup, missing file, or restore test problem as an operational incident.",
    ]

    recovery_steps = [
        "Identify the incident and decide whether recovery is actually required.",
        "Select the cleanest backup from before the incident.",
        "Validate the selected backup in a disposable restore environment.",
        "Confirm core tables are present after restore, including residents, program enrollments, intake assessments, and resident passes.",
        "Run the application test suite against the restored database when possible.",
        "Only after validation, perform a controlled production recovery using Railway level database tools.",
        "After recovery, document the backup used, the restore result, and any data gap between backup time and restore time.",
    ]

    return render_template(
        "admin_backup_documentation.html",
        title="Backup Documentation",
        backup_summary=backup_summary,
        restore_boundaries=restore_boundaries,
        daily_checklist=daily_checklist,
        recovery_steps=recovery_steps,
    )


def save_backup_restore_notes_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    notes = (request.form.get("restore_notes") or "").strip()
    if not notes:
        flash("Restore notes were not saved because the notes box was empty.", "warning")
        return redirect(url_for("admin.admin_backup_documentation"))

    confirm_phrase = (request.form.get("confirm_phrase") or "").strip()
    if confirm_phrase != RESTORE_NOTES_CONFIRM_PHRASE:
        flash("Restore notes were not saved because the confirmation phrase did not match.", "error")
        return redirect(url_for("admin.admin_backup_documentation"))

    validation_status = (request.form.get("validation_status") or "").strip()
    validation_run_id = (request.form.get("validation_run_id") or "").strip()
    validation_report_link = (request.form.get("validation_report_link") or "").strip()
    backup_sha256 = (request.form.get("backup_sha256") or "").strip()

    log_action(
        "backup_restore",
        None,
        None,
        _staff_user_id(),
        "restore_notes_saved",
        {
            "backup_sha256": backup_sha256,
            "notes": notes,
            "validation_report_link": validation_report_link,
            "validation_run_id": validation_run_id,
            "validation_status": validation_status,
        },
    )

    flash("Restore notes saved to the audit log.", "success")
    return redirect(url_for("admin.admin_backup_documentation"))
