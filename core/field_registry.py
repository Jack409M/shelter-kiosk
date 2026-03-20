from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FieldDefinition:
    key: str
    label: str

    # lifecycle placement
    lifecycle_stage: Optional[str] = None  # demographics, intake, exit, followup_6m, followup_1y, derived, reporting_only

    # wiring status
    wiring_status: Optional[str] = None  # complete, partial, missing, derived, misaligned

    # where collected
    form_page: Optional[str] = None
    form_field: Optional[str] = None

    # where stored
    table: Optional[str] = None
    column: Optional[str] = None

    # reporting usage
    used_in_stats: bool = False

    # notes
    notes: Optional[str] = None


FIELDS: List[FieldDefinition] = [
    FieldDefinition(key="last_updated", label="Last updated", notes="System managed or PDF only. Not part of resident metrics dataset."),
    FieldDefinition(key="prog_eval_months", label="Prog. Eval. Months", notes="Not wired. No table or route found."),
    FieldDefinition(key="name_last_first", label="Name (Last, First)", form_page="intake_assessment", notes="Collected as separate first_name and last_name fields."),
    FieldDefinition(key="first_name", label="First Name", form_page="intake_assessment", form_field="first_name", table="residents", column="first_name", notes="Collected and stored."),
    FieldDefinition(key="last_name", label="Last Name", form_page="intake_assessment", form_field="last_name", table="residents", column="last_name", notes="Collected and stored."),
    FieldDefinition(key="date_entered", label="Date Entered", form_page="intake_assessment", form_field="date_entered", table="program_enrollments", column="entry_date", used_in_stats=True),
    FieldDefinition(key="sobriety_date", label="Sobriety Date", form_page="intake_assessment", form_field="sobriety_date", table="intake_assessments", column="sobriety_date", used_in_stats=True),
    FieldDefinition(key="treatment_grad_date", label="Treatment Grad Date", notes="Not wired."),
    FieldDefinition(key="rad_graduation", label="RAD graduation", notes="Not wired."),
    FieldDefinition(key="days_sober_at_entry", label="Days Sober At Entry", table="intake_assessments", column="days_sober_at_entry", notes="Schema exists but not populated."),
    FieldDefinition(key="days_sober_today", label="Days Sober Today", notes="Derived or later update."),
    FieldDefinition(key="drug_of_choice", label="Drug of Choice", form_page="intake_assessment", form_field="drug_of_choice", table="intake_assessments", column="drug_of_choice", used_in_stats=True),
    FieldDefinition(key="race_dataset", label="Race", form_page="intake_assessment", form_field="race", table="residents", column="race", used_in_stats=True),
    FieldDefinition(key="gender_dataset", label="Gender", form_page="intake_assessment", form_field="gender", table="residents", column="gender", used_in_stats=True),
    FieldDefinition(key="woman_age", label="Woman Age", form_page="intake_assessment", form_field="birth_year", table="residents", column="birth_year", notes="Derived from birth_year."),
    FieldDefinition(key="kids_at_dwc", label="Kids @ DWC", table="family_snapshots", column="kids_at_dwc", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="kids_served_outside_under_18", label="Kids served Outside under 18", table="family_snapshots", column="kids_served_outside_under_18", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="kids_ages_0_5", label="Kids ages 0-5", table="family_snapshots", column="kids_ages_0_5", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="kids_ages_6_11", label="Kids ages 6-11", table="family_snapshots", column="kids_ages_6_11", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="kids_ages_12_17", label="Kids ages 12-17", table="family_snapshots", column="kids_ages_12_17", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="young_adults_18_21", label="Young adults 18-21", notes="Not wired."),
    FieldDefinition(key="adult_children_21_65", label="Adult children 21-65", notes="Not wired."),
    FieldDefinition(key="kids_reunited_while_in_program", label="Kids reunited while in program", table="family_snapshots", column="kids_reunited_while_in_program", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="healthy_babies_born_at_dwc", label="Healthy Babies born at DWC", table="family_snapshots", column="healthy_babies_born_at_dwc", used_in_stats=True, notes="Should be derived."),
    FieldDefinition(key="shelter", label="SHELTER", form_page="intake_assessment", form_field="shelter", table="program_enrollments", column="shelter", used_in_stats=True),
    FieldDefinition(key="income_at_entry", label="Income at Entry", form_page="intake_assessment", form_field="income_at_entry", table="intake_assessments", column="income_at_entry", used_in_stats=True),
    FieldDefinition(key="last_zipcode_of_residence", label="Last Zipcode of residence", form_page="intake_assessment", form_field="last_zipcode_residence", table="intake_assessments", column="last_zipcode_residence"),
    FieldDefinition(key="city", label="City", form_page="intake_assessment", form_field="city", table="intake_assessments", column="city"),
    FieldDefinition(key="veteran", label="Veteran", form_page="intake_assessment", form_field="veteran", table="intake_assessments", column="veteran", used_in_stats=True),
    FieldDefinition(key="disability", label="Disability", form_page="intake_assessment", form_field="disability", table="intake_assessments", column="disability", used_in_stats=True),
    FieldDefinition(key="education_at_entry", label="Edu at Entry", form_page="intake_assessment", form_field="education_at_entry", table="intake_assessments", column="education_at_entry", used_in_stats=True),
    FieldDefinition(key="educational_programs_entered_after_intake", label="Educational Programs entered after intake", notes="Followup or progress."),
    FieldDefinition(key="car_at_entry", label="Car at Entry", form_page="intake_assessment", form_field="car_at_entry", table="intake_assessments", column="car_at_entry"),
    FieldDefinition(key="car_insurance_at_entry", label="Car Ins Entry", form_page="intake_assessment", form_field="car_insurance_at_entry", table="intake_assessments", column="car_insurance_at_entry"),
    FieldDefinition(key="length_of_time_in_amarillo", label="Length of time in Amarillo upon entry", form_page="intake_assessment", form_field="length_of_time_in_amarillo", table="intake_assessments", column="length_of_time_in_amarillo"),
    FieldDefinition(key="marital_status", label="Marital Status", form_page="intake_assessment", form_field="marital_status", table="intake_assessments", column="marital_status", used_in_stats=True),
    FieldDefinition(key="place_staying_before_entry", label="Place staying before entry", form_page="intake_assessment", form_field="place_staying_before_entry", table="intake_assessments", column="place_staying_before_entry"),
    FieldDefinition(key="ace_score", label="ACE score at entry", form_page="intake_assessment", form_field="ace_score", table="intake_assessments", column="ace_score", used_in_stats=True),
    FieldDefinition(key="grit_score_at_entry", label="Grit score at entry", form_page="intake_assessment", form_field="grit_score", table="intake_assessments", column="grit_score"),
    FieldDefinition(key="updated_grit", label="Updated Grit", notes="Followup or progress."),
    FieldDefinition(key="sexual_survivor", label="Sexual Survivor", form_page="intake_assessment", form_field="sexual_survivor", table="intake_assessments", column="sexual_survivor", used_in_stats=True),
    FieldDefinition(key="dv_survivor", label="DV Survivor", form_page="intake_assessment", form_field="dv_survivor", table="intake_assessments", column="dv_survivor", used_in_stats=True),
    FieldDefinition(key="human_trafficking_survivor", label="Human Trafficking Survivor", form_page="intake_assessment", form_field="human_trafficking_survivor", table="intake_assessments", column="human_trafficking_survivor", used_in_stats=True),
    FieldDefinition(key="entry_felony_conviction", label="Entry Felony Conviction", form_page="intake_assessment", form_field="entry_felony_conviction", table="intake_assessments", column="entry_felony_conviction", used_in_stats=True),
    FieldDefinition(key="entry_parole_probation", label="Entry Parole/Probation", form_page="intake_assessment", form_field="entry_parole_probation", table="intake_assessments", column="entry_parole_probation", used_in_stats=True),
    FieldDefinition(key="drug_court", label="Drug Court", form_page="intake_assessment", form_field="drug_court", table="intake_assessments", column="drug_court", used_in_stats=True),
    FieldDefinition(key="warrants_unpaid", label="Warrants or Fines Unpaid", form_page="intake_assessment", form_field="warrants_unpaid", table="intake_assessments", column="warrants_unpaid"),
    FieldDefinition(key="dental_need_at_entry", label="Need Dental on Entry", form_page="intake_assessment", form_field="dental_need_at_entry", table="intake_assessments", column="dental_need_at_entry"),
    FieldDefinition(key="vision_need_at_entry", label="Need Vision on Entry", form_page="intake_assessment", form_field="vision_need_at_entry", table="intake_assessments", column="vision_need_at_entry"),
    FieldDefinition(key="mh_exam_completed", label="MH Exam", form_page="intake_assessment", form_field="mh_exam_completed", table="intake_assessments", column="mh_exam_completed"),
    FieldDefinition(key="med_exam_completed", label="Med Exam", form_page="intake_assessment", form_field="med_exam_completed", table="intake_assessments", column="med_exam_completed"),
    FieldDefinition(key="date_graduated", label="Date Graduated", form_page="exit_assessment", form_field="date_graduated", table="exit_assessments", column="date_graduated", used_in_stats=True),
    FieldDefinition(key="date_exit_dwc", label="Date Exit DWC", form_page="exit_assessment", form_field="date_exit_dwc", table="exit_assessments", column="date_exit_dwc", used_in_stats=True),
    FieldDefinition(key="reason_for_exit", label="Reason for exit", form_page="exit_assessment", form_field="exit_reason", table="exit_assessments", column="exit_reason", used_in_stats=True),
    FieldDefinition(key="graduate_dwc", label="Graduate DWC", form_page="exit_assessment", form_field="graduate_dwc", table="exit_assessments", column="graduate_dwc", used_in_stats=True),
    FieldDefinition(key="leave_ama_upon_exit", label="Leave AMA upon exit", form_page="exit_assessment", form_field="leave_ama", table="exit_assessments", column="leave_ama", used_in_stats=True),
    FieldDefinition(key="received_car_at_exit", label="Received Car at exit", form_page="exit_assessment", form_field="received_car", table="exit_assessments", column="received_car"),
    FieldDefinition(key="car_insurance_at_exit", label="Car insurance at exit", form_page="exit_assessment", form_field="car_insurance", table="exit_assessments", column="car_insurance"),
    FieldDefinition(key="current_income", label="Current income", form_page="exit_assessment", form_field="income_at_exit", table="exit_assessments", column="income_at_exit", used_in_stats=True),
    FieldDefinition(key="education_at_exit", label="Education at exit", form_page="exit_assessment", form_field="education_at_exit", table="exit_assessments", column="education_at_exit", used_in_stats=True),
    FieldDefinition(key="dental_needs_met", label="Dental Needs Met", form_page="exit_assessment", form_field="dental_needs_met", table="exit_assessments", column="dental_needs_met"),
    FieldDefinition(key="vision_needs_met", label="Vision Needs Met", form_page="exit_assessment", form_field="vision_needs_met", table="exit_assessments", column="vision_needs_met"),
    FieldDefinition(key="phone", label="Phone", form_page="intake_assessment", form_field="phone", table="residents", column="phone"),
    FieldDefinition(key="email", label="Email", form_page="intake_assessment", form_field="email", table="residents", column="email"),
    FieldDefinition(key="income_6_month_graduation", label="Income 6 mo", table="followups", column="income_at_followup"),
    FieldDefinition(key="income_1_year_graduation", label="Income 1 yr", table="followups", column="income_at_followup"),
    FieldDefinition(key="sober_6_month_graduation", label="Sober 6 mo", table="followups", column="sober_at_followup"),
    FieldDefinition(key="sober_1_year_graduation", label="Sober 1 yr", table="followups", column="sober_at_followup"),
    FieldDefinition(key="new_mailing_address", label="New mailing address", notes="Followup or profile update."),
]


def get_all_fields() -> List[FieldDefinition]:
    return FIELDS
