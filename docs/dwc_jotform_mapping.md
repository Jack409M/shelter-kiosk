# DWC Program Operations Platform
Jotform Mapping

This document maps the current Jotform based workflow into the planned program operations platform.

The goal is to preserve familiar workflows while storing the data in a normalized and modular system.

---

## Form 1
Itinerary Sheet

Purpose:
Weekly forward looking planning form for the next week.

Tracks:
- planned volunteer or community service
- planned appointments
- planned meetings
- cooking duties
- deep clean participation
- extra classes
- total work hours
- total productive hours
- total meetings
- level at submission
- employment snapshot

Mapped module:
- Weekly Accountability

Mapped tables:
- weekly_submissions
- weekly_submission_entries

Mapping notes:
- this form becomes a weekly_submissions record with submission_type of plan
- each daily activity becomes a weekly_submission_entries row
- total work hours, productive hours, and meetings are calculated from the entries
- the app may still render the form in a day by day layout for familiarity, but the database should store normalized rows

---

## Form 2
Productive Sheet

Purpose:
Weekly backward looking actual activity form for the prior week.

Tracks:
- actual volunteer or community service
- actual appointments
- actual meetings
- cooking duties completed
- deep clean participation
- extra classes
- total work hours
- total productive hours
- total meetings
- level at submission
- employment snapshot

Mapped module:
- Weekly Accountability

Mapped tables:
- weekly_submissions
- weekly_submission_entries

Mapping notes:
- this form becomes a weekly_submissions record with submission_type of actual
- each actual activity becomes a weekly_submission_entries row
- productive and work hour compliance should be calculated from these entries
- plan versus actual comparison can be built by comparing plan and actual weekly submissions for the same week

---

## Form 3
Meeting Sheet

Purpose:
Weekly recovery engagement form.

Tracks:
- sponsor name
- sponsor phone
- sponsor relationship duration
- recovery program
- current step
- step duration
- recovery meetings attended by day
- meeting topics
- resident reported current needs
- total number of meetings

Mapped module:
- Recovery Engagement

Mapped tables:
- recovery_profiles
- recovery_meeting_submissions
- recovery_meeting_entries

Mapping notes:
- sponsor and step related information should update recovery_profiles
- each weekly submission creates a recovery_meeting_submissions record
- each daily meeting becomes a recovery_meeting_entries row
- total meetings should be calculated from meeting entry rows
- resident needs reported here should remain visible to staff and may later feed a cross module needs dashboard

---

## Form 4
Case Management Sheet

Purpose:
Weekly operational case management status form.

Tracks:
- level at submission
- employment snapshot
- sponsor status
- assigned case manager
- whether a one on one meeting happened
- transportation status
- bus ticket need
- open checklist needs
- other written needs

Mapped module:
- Weekly Case Management Check In

Mapped tables:
- weekly_case_management_checkins
- weekly_case_management_needs

Related tables:
- case_manager_updates
- recovery_profiles

Mapping notes:
- this form should remain a lightweight weekly operational check in
- detailed one on one staff meeting records belong in case_manager_updates
- sponsor truth remains in recovery_profiles, while this form may capture a weekly has_sponsor snapshot if needed
- checkbox needs should be stored as weekly_case_management_needs rows rather than a single text blob

---

## Cross Form Overlaps

Several concepts appear in more than one Jotform.
These overlaps must follow the source of truth rules.

### Employment
Appears in:
- Itinerary Sheet
- Productive Sheet
- Case Management Sheet

Rule:
- weekly forms may capture snapshots
- current operational employment context belongs in case_manager_updates or a later dedicated employment history design

### Program Level
Appears in:
- Itinerary Sheet
- Productive Sheet
- Meeting Sheet
- Case Management Sheet

Rule:
- weekly forms may store level_at_submission snapshots
- current level should not depend on weekly forms alone

### Sponsor
Appears in:
- Meeting Sheet
- Case Management Sheet

Rule:
- recovery_profiles is the source of truth

### Meetings
Appears in:
- Itinerary Sheet
- Productive Sheet
- Meeting Sheet

Rule:
- recovery meeting details belong in recovery_meeting_entries
- general weekly accountability meeting counts belong in weekly_submission_entries only when they represent broader weekly meeting activity

### Needs
Appears in:
- Meeting Sheet
- Case Management Sheet

Rule:
- each form may keep its own weekly needs context
- long term or actionable needs may later be promoted into a broader needs workflow or case manager update process

---

## Design Intent

The platform should feel familiar to staff and residents by preserving the recognizable form workflows, but the database and application structure must remain normalized, modular, and maintainable.
