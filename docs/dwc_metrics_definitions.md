# DWC Program Operations Platform
Metrics Definitions

This document defines the official formulas and meanings for dashboard metrics, report metrics, and program statistics.

The purpose of this file is to make sure that reports, dashboards, exports, and summaries all use the same definitions.

---

## Rule

A metric must be defined in one place only.

No route, dashboard, or export should invent its own version of a metric.

---

## Women Served

Definition:
Count of distinct residents with a program enrollment active during the selected reporting period.

Suggested logic:
- distinct resident_id
- from program_enrollments
- where entry_date is on or before report end date
- and exit_date is null or exit_date is on or after report start date

Meaning:
The number of unique women participating in the program during the time period.

---

## Women Admitted

Definition:
Count of enrollments with entry_date inside the selected reporting period.

Meaning:
The number of women who entered the program during the reporting period.

---

## Women Exited

Definition:
Count of enrollments with exit_date inside the selected reporting period.

Meaning:
The number of women who left the program during the reporting period, regardless of exit reason.

---

## Graduates

Definition:
Count of exit_assessments where graduate_dwc is true and the exit date falls inside the selected reporting period.

Meaning:
The number of women who completed the program during the reporting period.

---

## Graduation Rate

Definition:
Graduates divided by women exited for the selected reporting period.

Formula:
graduates / exited_women

Meaning:
The share of women leaving the program who graduated successfully.

Important:
Do not divide by total women served.

---

## Active Residents

Definition:
Count of enrollments with no exit date or with exit date after the current date.

Meaning:
Residents currently active in program participation.

---

## Average Length of Stay

Definition:
Average number of days between entry_date and exit_date for exited enrollments in the selected reporting period.

Meaning:
Average time spent in the program for completed or exited program enrollments.

Important:
Use only exited enrollments unless a separate active stay metric is created.

---

## Days at DWC

Definition:
Current date minus entry_date for an active enrollment.

Meaning:
The number of days a resident has been in the program so far.

Important:
This should be calculated, not manually stored.

---

## Average Income at Entry

Definition:
Average income_at_entry across intake assessments linked to enrollments in the selected reporting period.

Meaning:
Average resident income at intake.

---

## Average Income at Exit

Definition:
Average income_at_exit across exit assessments in the selected reporting period.

Meaning:
Average resident income at program exit.

---

## Average Income Improvement

Definition:
Average of income_at_exit minus income_at_entry for enrollments with both values present.

Formula:
avg(income_at_exit - income_at_entry)

Meaning:
Average improvement in resident income across comparable records.

Important:
Only include residents with both values available.

---

## Residents Employed

Definition:
Count of residents whose most recent employment related status indicates employed.

Meaning:
Residents currently employed based on the current operational context.

Important:
This should eventually rely on a clearly defined current employment source rather than weekly snapshots alone.

---

## Residents Receiving Counseling

Definition:
Count of distinct enrollments with at least one service record where service_type is counseling within the selected reporting period.

Meaning:
Number of residents who received counseling services.

---

## Residents Receiving Dental Services

Definition:
Count of distinct enrollments with at least one service record where service_type is dental or dental_completed within the selected reporting period.

Meaning:
Number of residents who received dental related services.

---

## Residents Receiving Vision Services

Definition:
Count of distinct enrollments with at least one service record where service_type is vision or vision_completed within the selected reporting period.

Meaning:
Number of residents who received vision related services.

---

## Residents Receiving Transportation Support

Definition:
Count of case management checkins where needs_bus_tickets is true within the selected reporting period.

Meaning:
Residents reporting transportation support needs.

---

## Children Served

Definition:
Sum of child counts from family_snapshots for enrollments in scope.

Meaning:
Total children impacted by the program.

Important:
A separate metric may later distinguish children physically at DWC versus children served outside the shelter.

---

## Children Reunited

Definition:
Sum of kids_reunited_while_in_program from family_snapshots in the selected reporting period.

Meaning:
Number of children reunited with their mother during the program.

---

## Healthy Babies Born

Definition:
Sum of healthy_babies_born_at_dwc from family_snapshots in the selected reporting period.

Meaning:
Count of healthy babies born while the resident was in program participation.

---

## Average Recovery Meetings Per Week

Definition:
Total recovery meeting entries divided by the number of resident weeks in the selected reporting period.

Meaning:
Average weekly recovery meeting participation.

Important:
This uses recovery_meeting_entries, not general weekly accountability meeting counts.

---

## Residents With Sponsor

Definition:
Count of active recovery profiles with sponsor information present.

Meaning:
Residents currently reporting an active sponsor relationship.

---

## Residents Without Sponsor

Definition:
Count of active enrollments without sponsor information in recovery_profiles.

Meaning:
Residents currently lacking sponsor support.

---

## Weekly Productive Hours

Definition:
Sum of weekly_submission_entries.hours where counts_as_productive is true.

Meaning:
Total productive hours for a weekly submission.

Important:
Should be calculated from entry rows.

---

## Weekly Work Hours

Definition:
Sum of weekly_submission_entries.hours where counts_as_work is true.

Meaning:
Total work qualified hours for a weekly submission.

Important:
Should be calculated from entry rows.

---

## Weekly Meetings Count

Definition:
Sum of weekly_submission_entries rows where counts_as_meeting is true for a weekly submission.

Meaning:
Total meetings counted in a weekly accountability submission.

Important:
Do not confuse this with detailed recovery meeting attendance.

---

## Productive Hour Compliance Rate

Definition:
Percentage of weekly actual submissions meeting the 35 hour productive threshold.

Formula:
actual_submissions_meeting_35 / total_actual_submissions

Meaning:
How often residents meet the minimum productive hour requirement.

---

## Work Hour Compliance Rate

Definition:
Percentage of weekly actual submissions meeting the 29 hour work threshold.

Formula:
actual_submissions_meeting_29 / total_actual_submissions

Meaning:
How often residents meet the minimum work hour requirement.

---

## Residents Missing Weekly Submission

Definition:
Count of active enrollments lacking a required weekly submission for the expected week.

Meaning:
Residents missing required accountability paperwork.

---

## Residents Meeting With Case Manager

Definition:
Count of weekly_case_management_checkins where met_one_on_one_this_week is true in the selected reporting period.

Meaning:
Residents who report completing a weekly one on one case management meeting.

---

## Open Needs Count

Definition:
Count of weekly_case_management_needs rows in the selected reporting period.

Meaning:
Total number of reported operational need items.

---

## Sobriety at Six Month Follow Up

Definition:
Count or percentage of followup records with followup_type of 6_month and sober_at_followup true.

Meaning:
Residents maintaining sobriety at six month follow up.

---

## Sobriety at One Year Follow Up

Definition:
Count or percentage of followup records with followup_type of 12_month and sober_at_followup true.

Meaning:
Residents maintaining sobriety at one year follow up.

---

## Data Quality Rule

When a metric depends on dates, the report must clearly define the reporting period used.

When a metric depends on averages, records with missing values should be excluded rather than treated as zero unless explicitly intended.

When a metric depends on distinct people, use distinct resident or enrollment counts carefully to avoid double counting.

---

## Implementation Rule

All metric formulas should ultimately live in the centralized metrics engine service and not be duplicated in route files or templates.
