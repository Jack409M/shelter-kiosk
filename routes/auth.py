# SNIP (full file preserved, only edited sections shown below)

# --- inside _load_allowed_shelters_for_user ---
    if staff_role in {"admin", "shelter_director", "demographics_viewer"}:
        return list(all_shelters_lower)

# --- inside staff_login redirect block ---
    if session.get("role") == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    if session.get("role") == "demographics_viewer":
        return redirect(url_for("reports.reports_index"))

    return redirect(url_for("attendance.staff_attendance"))
