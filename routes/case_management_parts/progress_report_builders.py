from __future__ import annotations

from core.helpers import fmt_pretty_dt, utcnow_iso


def append_unique_text(target: list[str], value: str | None) -> None:
    text = (value or "").strip()
    if not text:
        return
    if text not in target:
        target.append(text)


def collect_summary_group_labels(note: dict, group_key: str) -> list[str]:
    labels: list[str] = []

    for group in note.get("summary_groups") or []:
        if group.get("group_key") != group_key:
            continue

        for item in group.get("items") or []:
            item_label = (item.get("item_label") or "").strip()
            detail = (item.get("detail") or "").strip()
            new_value = (item.get("new_value") or "").strip()

            if item_label and item_label != "—":
                labels.append(item_label)
                continue

            if detail:
                labels.append(detail)
                continue

            if new_value:
                labels.append(new_value)

    deduped: list[str] = []
    for label in labels:
        append_unique_text(deduped, label)
    return deduped


def build_merge_profile_updates(
    note: dict,
    recovery_snapshot: dict | None,
    enrollment: dict | None,
) -> list[str]:
    updates: list[str] = []

    for group_key in ["employment", "sobriety", "advancement"]:
        for label in collect_summary_group_labels(note, group_key):
            append_unique_text(updates, label)

    if recovery_snapshot:
        if recovery_snapshot.get("program_level") not in (None, ""):
            append_unique_text(updates, "program level")
        if recovery_snapshot.get("sobriety_date"):
            append_unique_text(updates, "sobriety date")
        if recovery_snapshot.get("sponsor_name"):
            append_unique_text(updates, "sponsor")
        if recovery_snapshot.get("employment_status_current"):
            append_unique_text(updates, "employment status")
        if recovery_snapshot.get("monthly_income") not in (None, ""):
            append_unique_text(updates, "monthly income")

    if enrollment and enrollment.get("program_status"):
        append_unique_text(updates, "program status")

    return updates


def build_services_merge(note_services: list[dict]) -> list[str]:
    service_names: list[str] = []

    for service in note_services:
        append_unique_text(service_names, service.get("service_type"))

    return service_names


def build_needs_merge(note: dict) -> tuple[list[str], list[str], bool]:
    needs_addressed = collect_summary_group_labels(note, "need_addressed")
    needs_outstanding = collect_summary_group_labels(note, "need_outstanding")

    blocker_reason = (note.get("blocker_reason") or "").strip()
    if blocker_reason and not needs_outstanding:
        append_unique_text(needs_outstanding, blocker_reason)

    all_identified_needs_resolved = not needs_outstanding
    return needs_addressed, needs_outstanding, all_identified_needs_resolved


def build_service_rows(note_services: list[dict], meeting_date: str | None) -> list[dict]:
    rows: list[dict] = []

    for service in note_services:
        quantity_display = service.get("quantity_display")
        rows.append(
            {
                "service_type": service.get("service_type") or "—",
                "service_date": service.get("service_date") or meeting_date or "—",
                "quantity_display": (
                    quantity_display if quantity_display and quantity_display != "—" else ""
                ),
                "notes": service.get("notes") or "",
            }
        )

    return rows


def build_goal_rows(goals: list[dict]) -> list[dict]:
    rows: list[dict] = []

    for goal in goals:
        rows.append(
            {
                "goal_text": goal.get("goal_text") or "—",
                "status": goal.get("status") or "—",
                "target_date": goal.get("target_date") or "",
            }
        )

    return rows


def build_program_snapshot(enrollment: dict | None, recovery_snapshot: dict) -> list[dict]:
    return [
        {
            "label": "Program Status",
            "value": enrollment.get("program_status") if enrollment else "—",
        },
        {
            "label": "Level",
            "value": recovery_snapshot.get("program_level") or "—",
        },
        {
            "label": "Level Start Date",
            "value": recovery_snapshot.get("level_start_date") or "—",
        },
        {
            "label": "Days On Level",
            "value": (
                recovery_snapshot.get("days_on_level")
                if recovery_snapshot.get("days_on_level") is not None
                else "—"
            ),
        },
        {
            "label": "Days Sober",
            "value": (
                recovery_snapshot.get("days_sober_today")
                if recovery_snapshot.get("days_sober_today") is not None
                else "—"
            ),
        },
        {
            "label": "Sobriety Date",
            "value": recovery_snapshot.get("sobriety_date") or "—",
        },
        {
            "label": "Drug Of Choice",
            "value": recovery_snapshot.get("drug_of_choice") or "—",
        },
        {
            "label": "Sponsor",
            "value": recovery_snapshot.get("sponsor_name") or "—",
        },
        {
            "label": "Employment Status",
            "value": recovery_snapshot.get("employment_status_current") or "—",
        },
        {
            "label": "Monthly Income",
            "value": (
                recovery_snapshot.get("monthly_income")
                if recovery_snapshot.get("monthly_income") not in (None, "")
                else "—"
            ),
        },
    ]


def build_progress_report_context(
    *,
    resident: dict,
    enrollment: dict | None,
    note: dict,
    goals: list[dict],
    recovery_snapshot: dict | None,
    case_manager_name: str,
):
    recovery_snapshot = recovery_snapshot or {}
    note_services = note.get("services") or []

    resident_name = " ".join(
        part for part in [resident.get("first_name"), resident.get("last_name")] if part
    ).strip() or "Resident"

    resident_display_id = (
        resident.get("resident_identifier")
        or resident.get("resident_code")
        or str(resident.get("id") or "")
    )

    needs_addressed, needs_outstanding, all_identified_needs_resolved = build_needs_merge(note)

    generated_at = utcnow_iso()

    return {
        "report_title": "Progress Note",
        "generated_at_display": fmt_pretty_dt(generated_at),
        "resident_name": resident_name,
        "resident_display_id": resident_display_id,
        "resident": resident,
        "enrollment": enrollment,
        "note": note,
        "goals": build_goal_rows(goals),
        "case_manager_name": case_manager_name,
        "service_rows": build_service_rows(note_services, note.get("meeting_date")),
        "services_merge": build_services_merge(note_services),
        "needs_addressed_merge": needs_addressed,
        "needs_outstanding_merge": needs_outstanding,
        "all_identified_needs_resolved": all_identified_needs_resolved,
        "profile_updates_merge": build_merge_profile_updates(note, recovery_snapshot, enrollment),
        "program_snapshot": build_program_snapshot(enrollment, recovery_snapshot),
    }
