# Sanitization Field Map

This document is the source of truth for creating sanitized database backups for restore validation.

The purpose of this map is to prevent resident, child, staff, case, medical, contact, location, or free text information from leaving controlled DWC systems when a backup is used for validation in GitHub Actions or another disposable restore environment.

## Core Rule

A sanitized backup must preserve database structure and enough relational shape to test restore behavior, but it must not preserve real identifying or sensitive information.

When in doubt, replace the value.

## Non Negotiable Safety Rules

1. Never upload a production backup with real resident data to GitHub Actions.
2. Never paste production database credentials into GitHub, chat, tickets, screenshots, or documentation.
3. Never restore into production from the application UI.
4. Only validate against disposable databases.
5. Treat all staff entered free text as sensitive.
6. Treat all JSON and payload fields as sensitive unless specifically proven otherwise.
7. Preserve table structure, IDs, foreign keys, status fields, dates, and category fields only when they do not identify a person.

## Transformation Types

### Identity fields

Identity fields must be replaced with deterministic fake values.

Recommended pattern:

```text
first_name: Test
last_name: Resident0001
phone: 5550000000
email: resident0001@example.invalid
emergency_contact_name: Test Contact0001
emergency_contact_phone: 5550000001
child_name: Test Child0001
```

Use `.invalid` email domains so messages cannot accidentally route to a real person.

### Location fields

Location data must be sanitized because shelter context plus city, county, zip code, or address can make a record identifiable.

Recommended pattern:

```text
city: FAKE_CITY
county: FAKE_COUNTY
last_zipcode_residence: 00000
address fields: SANITIZED
pickup_location: SANITIZED
passing destination address fields: SANITIZED
```

### Free text fields

Any staff entered free text should be replaced entirely.

Do not try to partially clean free text.

Recommended pattern:

```text
SANITIZED
```

This applies broadly to columns containing words like:

```text
notes
summary
details
reason
description
explanation
comment
message
payload
```

### Structured blobs

JSON, form payloads, draft payloads, and audit detail blobs must be replaced entirely.

Recommended pattern:

```text
draft_data: {}
form_payload: SANITIZED
action_details: SANITIZED
old_value: SANITIZED
new_value: SANITIZED
```

Do not attempt to surgically clean JSON fields until a separate parser has been reviewed and tested.

## Table Specific Map

### residents

Sanitize:

```text
resident_identifier
resident_code
first_name
last_name
phone
email
emergency_contact_name
emergency_contact_relationship
emergency_contact_phone
```

Preserve if needed for testing:

```text
id
shelter
birth_year
program_level
level_start_date
step_changed_at
is_active
created_at
updated_at
```

### resident_children

Sanitize:

```text
child_name
notes
```

Preserve if needed for testing:

```text
id
resident_id
birth_year
relationship
living_status
receives_survivor_benefit
survivor_benefit_amount
is_active
created_at
updated_at
```

### resident_child_income_supports

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
child_id
resident_id
enrollment_id
support_type
monthly_amount
amount
is_active
created_at
updated_at
```

### program_enrollments

Preserve:

```text
id
resident_id
shelter
entry_date
exit_date
program_status
case_manager_id
rad_complete
rad_completed_date
created_at
updated_at
```

No direct identity fields are currently mapped here, but the table remains tied to sanitized residents through `resident_id`.

### intake_drafts

Sanitize:

```text
resident_name
draft_data
form_payload
```

Required transformation:

```text
resident_name: Test Resident
 draft_data: {}
form_payload: SANITIZED
```

Preserve if needed for testing:

```text
id
resident_id
enrollment_id
shelter
status
entry_date
created_by_user_id
created_at
updated_at
```

### intake_assessments

Sanitize:

```text
city
county
last_zipcode_residence
notes_basic
entry_notes
initial_snapshot_notes
trauma_notes
barrier_notes
place_staying_before_entry
```

Recommended transformation:

```text
city: FAKE_CITY
county: FAKE_COUNTY
last_zipcode_residence: 00000
all notes/free text: SANITIZED
```

Preserve if needed for testing:

```text
enrollment_id
length_of_time_in_amarillo
income_at_entry
education_at_entry
treatment_grad_date
sobriety_date
days_sober_at_entry
drug_of_choice
ace_score
grit_score
veteran
disability
marital_status
entry_felony_conviction
entry_parole_probation
drug_court
sexual_survivor
dv_survivor
human_trafficking_survivor
warrants_unpaid
mh_exam_completed
med_exam_completed
car_at_entry
car_insurance_at_entry
pregnant_at_entry
dental_need_at_entry
vision_need_at_entry
employment_status_at_entry
mental_health_need_at_entry
medical_need_at_entry
substance_use_need_at_entry
id_documents_status_at_entry
has_drivers_license
has_social_security_card
parenting_class_needed
dwc_level_today
created_at
updated_at
```

### family_snapshots

Preserve:

```text
id
enrollment_id
kids_at_dwc
kids_served_outside_under_18
kids_ages_0_5
kids_ages_6_11
kids_ages_12_17
kids_reunited_while_in_program
healthy_babies_born_at_dwc
created_at
updated_at
```

### exit_assessments

Sanitize:

```text
leave_amarillo_city
```

Recommended transformation:

```text
leave_amarillo_city: FAKE_CITY
```

Preserve if needed for testing:

```text
enrollment_id
date_graduated
date_exit_dwc
exit_category
exit_reason
graduate_dwc
leave_ama
leave_amarillo_unknown
income_at_exit
graduation_income_snapshot
education_at_exit
grit_at_exit
received_car
car_insurance
dental_needs_met
vision_needs_met
obtained_public_insurance
private_insurance
created_at
updated_at
```

### followups

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
enrollment_id
followup_date
followup_type
income_at_followup
sober_at_followup
created_at
updated_at
```

### case_manager_updates

Sanitize:

```text
notes
progress_notes
setbacks_or_incidents
action_items
overall_summary
blocker_reason
override_or_exception
staff_review_note
```

Preserve if needed for testing:

```text
id
enrollment_id
staff_user_id
meeting_date
next_appointment
updated_grit
parenting_class_completed
warrants_or_fines_paid
ready_for_next_level
recommended_next_level
created_at
updated_at
```

### case_manager_update_summary

Sanitize:

```text
old_value
new_value
detail
```

Preserve if needed for testing:

```text
id
case_manager_update_id
change_group
change_type
item_key
item_label
sort_order
created_at
```

### client_services

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
enrollment_id
case_manager_update_id
service_type
service_date
quantity
unit
created_at
updated_at
```

### transport_requests

Sanitize:

```text
resident_identifier
first_name
last_name
pickup_location
destination
reason
resident_notes
callback_phone
staff_notes
```

Preserve if needed for testing:

```text
id
shelter
needed_at
status
submitted_at
scheduled_at
scheduled_by
```

### resident_transfers

Sanitize:

```text
transferred_by
note
```

Preserve if needed for testing:

```text
id
resident_id
from_shelter
to_shelter
transferred_at
```

### attendance_events

Sanitize:

```text
note
destination
meeting_1
meeting_2
```

Preserve if needed for testing:

```text
id
resident_id
shelter
event_type
event_time
staff_user_id
expected_back_time
obligation_start_time
obligation_end_time
actual_obligation_end_time
meeting_count
is_recovery_meeting
```

### resident_passes

Sanitize:

```text
destination
reason
resident_notes
staff_notes
```

Preserve if needed for testing:

```text
id
resident_id
shelter
pass_type
status
start_at
end_at
start_date
end_date
approved_by
approved_at
delete_after_at
created_at
updated_at
```

### resident_pass_request_details

Sanitize:

```text
resident_phone
requirements_not_met_explanation
reason_for_request
who_with
destination_address
destination_phone
companion_names
companion_phone_numbers
reviewed_by_name
```

Preserve if needed for testing:

```text
id
pass_id
request_date
resident_level
requirements_acknowledged
budgeted_amount
approved_amount
reviewed_by_user_id
reviewed_at
created_at
updated_at
```

### resident_notifications

Sanitize:

```text
title
message
```

Preserve if needed for testing:

```text
id
resident_id
shelter
notification_type
related_pass_id
is_read
created_at
read_at
```

### resident_writeups

Sanitize:

```text
summary
full_notes
action_taken
resolution_notes
```

Preserve if needed for testing:

```text
id
resident_id
shelter_snapshot
incident_date
category
severity
status
resolved_at
disciplinary_outcome
probation_start_date
probation_end_date
pre_termination_date
blocks_passes
created_by_staff_user_id
updated_by_staff_user_id
created_at
updated_at
```

### staff_users

Sanitize:

```text
username
first_name
last_name
mobile_phone
email
```

Recommended transformation:

```text
username: user_<id>
first_name: STAFF
last_name: USER
mobile_phone: 0000000000
email: staff<id>@example.invalid
```

Password hashes may remain unchanged for structure testing, but sanitized validation environments must not expose working login credentials to non authorized users.

### security_incidents

Sanitize:

```text
details
related_ip
related_username
```

Preserve if needed for testing:

```text
incident_type
severity
title
status
created_at
updated_at
```

### security_config_history

Sanitize if value contains sensitive text:

```text
old_value
new_value
```

Preserve:

```text
setting_key
changed_by_user_id
changed_at
```

### audit_log

Sanitize:

```text
action_details
```

Preserve if needed for testing:

```text
id
entity_type
entity_id
shelter
staff_user_id
action_type
created_at
```

### field_change_audit

Sanitize:

```text
old_value
new_value
change_reason
```

Preserve if needed for testing:

```text
id
entity_type
entity_id
table_name
field_name
changed_by_user_id
shelter
created_at
```

### child_services

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
resident_child_id
enrollment_id
service_date
service_type
outcome
quantity
unit
is_deleted
deleted_at
deleted_by_staff_user_id
created_at
updated_at
```

### resident_needs

Sanitize:

```text
source_value
resolution_note
```

Preserve if needed for testing:

```text
id
enrollment_id
need_key
need_label
source_field
status
resolved_at
resolved_by_staff_user_id
created_at
updated_at
```

### resident_medications

Sanitize:

```text
medication_name
dosage
frequency
purpose
prescribed_by
notes
```

Preserve if needed for testing:

```text
id
resident_id
enrollment_id
started_on
ended_on
is_active
created_by_staff_user_id
updated_by_staff_user_id
created_at
updated_at
```

### resident_ua_log

Sanitize:

```text
substances_detected
notes
```

Preserve if needed for testing:

```text
id
resident_id
enrollment_id
ua_date
result
administered_by_staff_user_id
created_at
updated_at
```

### resident_living_area_inspections

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
resident_id
enrollment_id
inspection_date
passed
inspected_by_staff_user_id
created_at
updated_at
```

### resident_budget_sessions

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
resident_id
enrollment_id
session_date
staff_user_id
created_at
updated_at
```

### chore_templates

Sanitize:

```text
description
```

Preserve if needed for testing:

```text
id
shelter
name
when_time
default_day
active
sort_order
created_at
```

### chore_assignments

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
resident_id
chore_id
assigned_date
status
created_at
updated_at
```

### kiosk_activity_categories

Sanitize:

```text
notes
```

Preserve if needed for testing:

```text
id
shelter
activity_label
active
sort_order
counts_as_work_hours
counts_as_productive_hours
weekly_cap_hours
requires_approved_pass
created_at
updated_at
```

## Script Requirements

The sanitizer script must:

1. Refuse to run against production like targets.
2. Require an explicit disposable database URL.
3. Apply this field map.
4. Replace JSON and payload fields completely.
5. Replace free text fields completely.
6. Export a `.sql.gz` file.
7. Generate a `.sha256` checksum file.
8. Print the output file path and checksum.
9. Never upload the sanitized file automatically.

## Locked Decision

The first sanitizer script must be conservative.

It is acceptable to over sanitize.

It is not acceptable to under sanitize.
