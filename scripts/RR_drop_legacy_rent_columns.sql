-- RR legacy rent column cleanup
--
-- Do not run this until operations_settings.py no longer references these columns
-- in its shelter_operation_settings UPDATE statement.
--
-- Purpose:
-- The active rent system now uses rr_rent_rules and rr_rent_policy_settings.
-- These legacy columns belonged to the old rent configuration model.
--
-- Production target: PostgreSQL.

BEGIN;

ALTER TABLE shelter_operation_settings
    DROP COLUMN IF EXISTS hh_rent_amount,
    DROP COLUMN IF EXISTS hh_rent_due_day,
    DROP COLUMN IF EXISTS hh_rent_late_day,
    DROP COLUMN IF EXISTS hh_rent_late_fee_per_day,
    DROP COLUMN IF EXISTS hh_late_arrangement_required,
    DROP COLUMN IF EXISTS hh_payment_methods_text,
    DROP COLUMN IF EXISTS hh_payment_accepted_by_roles_text,
    DROP COLUMN IF EXISTS hh_work_off_enabled,
    DROP COLUMN IF EXISTS hh_work_off_hourly_rate,
    DROP COLUMN IF EXISTS hh_work_off_required_hours,
    DROP COLUMN IF EXISTS hh_work_off_deadline_day,
    DROP COLUMN IF EXISTS hh_work_off_location_text,
    DROP COLUMN IF EXISTS hh_work_off_notes_text,
    DROP COLUMN IF EXISTS gh_rent_due_day,
    DROP COLUMN IF EXISTS gh_rent_late_fee_per_day,
    DROP COLUMN IF EXISTS gh_late_arrangement_required,
    DROP COLUMN IF EXISTS gh_level_5_one_bedroom_rent,
    DROP COLUMN IF EXISTS gh_level_5_two_bedroom_rent,
    DROP COLUMN IF EXISTS gh_level_5_townhome_rent,
    DROP COLUMN IF EXISTS gh_level_8_sliding_scale_enabled,
    DROP COLUMN IF EXISTS gh_level_8_sliding_scale_basis_text,
    DROP COLUMN IF EXISTS gh_level_8_first_increase_amount,
    DROP COLUMN IF EXISTS gh_level_8_second_increase_amount,
    DROP COLUMN IF EXISTS gh_level_8_increase_schedule_text,
    DROP COLUMN IF EXISTS rent_late_day_of_month,
    DROP COLUMN IF EXISTS rent_carry_forward_enabled;

COMMIT;
