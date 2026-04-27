from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from routes.admin_parts.helpers import require_admin_role


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
