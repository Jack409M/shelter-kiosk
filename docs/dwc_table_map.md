# DWC Program Operations Platform
Database Table Map

This document defines the planned database tables and the schema module file where each table belongs.

## Schema Module Layout

The database schema should be split into these files:

- outcomes_core.py
- outcomes_assessments.py
- weekly_accountability.py
- recovery_engagement.py
- case_management.py
- appointments.py
- goals.py

This keeps schema creation modular and avoids a giant monolithic schema file.

---

## outcomes_core.py

### program_enrollments
Purpose: anchor record for a resident's participation in the program.

Core fields:
- id
- resident_id
- shelter
- entry_date
- exit_date
- program_status
- case_manager_id
- created_at
- updated_at

### level_history
Purpose: optional later table to track program level changes over time.

Core fields:
- id
- enrollment_id
- level_value
- effective_date
- changed_by
- created_at

---

## outcomes_assessments.py

### intake_assessments
Purpose: one intake record per enrollment.

Core fields:
- id
- enrollment_id
- city
- last_zipcode_residence
- income_at_entry
- education_at_entry
- sobriety_date
- days_sober_at_entry
- drug_of_choice
- ace_score
- grit_score
- veteran
- disability
- marital_status
- place_staying_before_entry
- entry_felony_conviction
- entry_parole_probation
- drug_court
- sexual_survivor
- dv_survivor
- human_trafficking_survivor
- created_at
- updated_at

### family_snapshots
Purpose: family and child impact data tied to enrollment.

Core fields:
- id
- enrollment_id
- kids_at_dwc
- kids_served_outside_under_18
- kids_ages_0_5
- kids_ages_6_11
- kids_ages_12_17
- kids_reunited_while_in_program
- healthy_babies_born_at_dwc
- created_at
- updated_at

### exit_assessments
Purpose: exit record for enrollment.

Core fields:
- id
- enrollment_id
- date_graduated
- date_exit_dwc
- exit_reason
- graduate_dwc
- leave_ama
- income_at_exit
- education_at_exit
- received_car
- car_insurance
- dental_needs_met
- vision_needs_met
- obtained_insurance
- created_at
- updated_at

### followups
Purpose: dated follow up outcomes.

Core fields:
- id
- enrollment_id
- followup_date
- followup_type
- income_at_followup
- sober_at_followup
- notes
- created_at
- updated_at

---

## weekly_accountability.py

### weekly_submissions
Purpose: weekly header record for either a plan or actual submission.

Core fields:
- id
- enrollment_id
- week_start_date
- week_end_date
- submission_type
- level_at_submission
- employed
- deep_clean
- extra_classes
- other_appointments
- total_work_hours
- total_productive_hours
- total_meetings
- submitted_at
- created_at
- updated_at

Allowed submission_type values:
- plan
- actual

### weekly_submission_entries
Purpose: one row per weekly activity.

Core fields:
- id
- submission_id
- day_of_week
- entry_type
- location
- description
- start_time
- end_time
- hours
- counts_as_work
- counts_as_productive
- counts_as_meeting
- created_at
- updated_at

Suggested entry_type values:
- employment
- volunteer
- community_service
- appointment
- meeting
- cooking
- class
- deep_clean
- other

---

## recovery_engagement.py

### recovery_profiles
Purpose: current sponsor and recovery program profile for the enrollment.

Core fields:
- id
- enrollment_id
- sponsor_first_name
- sponsor_last_name
- sponsor_phone
- recovery_program
- current_step
- step_duration
- sponsor_relationship_duration
- created_at
- updated_at

### recovery_meeting_submissions
Purpose: weekly recovery meeting header record.

Core fields:
- id
- enrollment_id
- week_start_date
- week_end_date
- level_at_submission
- needs_text
- total_meetings
- submitted_at
- created_at
- updated_at

### recovery_meeting_entries
Purpose: one row per recovery meeting attended.

Core fields:
- id
- submission_id
- day_of_week
- meeting_location
- meeting_topic
- created_at
- updated_at

---

## case_management.py

### weekly_case_management_checkins
Purpose: weekly resident case management check in.

Core fields:
- id
- enrollment_id
- week_start_date
- week_end_date
- level_at_submission
- employed
- has_sponsor
- case_manager_id
- met_one_on_one_this_week
- takes_bus
- needs_bus_tickets
- other_needs_text
- submitted_at
- created_at
- updated_at

### weekly_case_management_needs
Purpose: one row per checked need item.

Core fields:
- id
- checkin_id
- need_code
- need_label_snapshot
- created_at

### case_manager_updates
Purpose: dated staff one on one meeting records.

Core fields:
- id
- enrollment_id
- meeting_date
- staff_user_id
- dwc_level
- income_current
- education_current
- notes
- barriers
- goals_summary
- created_at
- updated_at

### services
Purpose: dated service records.

Core fields:
- id
- enrollment_id
- service_type
- service_date
- service_status
- notes
- created_at
- updated_at

---

## appointments.py

### appointments
Purpose: structured appointment records for reminders and resident appointment slips.

Core fields:
- id
- enrollment_id
- staff_user_id
- appointment_date
- appointment_type
- location
- notes_for_resident
- reminder_sms_enabled
- reminder_app_enabled
- reminder_sent_at
- created_at
- updated_at

---

## goals.py

### goals
Purpose: structured resident goals.

Core fields:
- id
- enrollment_id
- case_update_id
- goal_text
- status
- target_date
- sort_order
- created_at
- completed_at
- updated_at

Suggested status values:
- active
- completed
- archived

---

## Phase One Table Set

Minimum strong phase one build:

- program_enrollments
- intake_assessments
- family_snapshots
- case_manager_updates
- services
- appointments
- goals
- weekly_submissions
- weekly_submission_entries
- recovery_profiles
- recovery_meeting_submissions
- recovery_meeting_entries
- weekly_case_management_checkins
- weekly_case_management_needs
- exit_assessments
- followups

---

## Later Optional Tables

Potential later additions:

- level_history
- metric_snapshots
- import_jobs
- import_row_results
