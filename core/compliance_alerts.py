from core.db import db_fetchall


def get_compliance_alerts():

    alerts = []

    rows = db_fetchall(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            wrs.productive_hours,
            wrs.work_hours,
            wrs.meeting_count
        FROM residents r
        LEFT JOIN program_enrollments pe
            ON pe.resident_id = r.id
        LEFT JOIN weekly_resident_summary wrs
            ON wrs.enrollment_id = pe.id
        WHERE pe.program_status = 'active'
        """
    )

    missing = 0
    low_hours = 0
    meeting_issue = 0

    for row in rows:

        if isinstance(row, dict):
            productive = row.get("productive_hours")
            meetings = row.get("meeting_count")
        else:
            productive = row[3]
            meetings = row[5]

        if productive is None:
            missing += 1
            continue

        if productive < 35:
            low_hours += 1

        if meetings is not None and meetings < 3:
            meeting_issue += 1

    if missing:
        alerts.append(f"{missing} residents missing weekly submission")

    if low_hours:
        alerts.append(f"{low_hours} residents under 35 productive hours")

    if meeting_issue:
        alerts.append(f"{meeting_issue} residents missing meeting requirements")

    return alerts
