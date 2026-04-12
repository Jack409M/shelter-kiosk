from __future__ import annotations

from dataclasses import dataclass

from flask import g, session

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso


@dataclass
class ResidentTransferContext:
    resident: dict | object
    resident_id: int
    current_shelter: str
    from_shelter: str
    all_shelters: list[str]
    shelter_choices: list[str]
    next_url: str
    active_config: dict | None
    current_apartment_number: str | None
    current_apartment_size: str | None
    destination_shelter_prefill: str
    availability_map: dict[str, list[str]]
    apartment_options: list[str]


@dataclass
class ResidentTransferFormData:
    to_shelter: str
    note: str
    apartment_number: str | None
    apartment_size: str | None
    available_apartments: list[str]
    same_shelter_move: bool


def normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def require_transfer_role() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def return_redirect_target(next_url: str) -> str:
    return (next_url or "").strip()


def row_value(row, key: str, index: int, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def move_supporting_shelters() -> set[str]:
    return {"abba", "gratitude", "haven"}


def same_shelter_housing_update_allowed(shelter: str) -> bool:
    return shelter in {"abba", "gratitude"}


def apartment_options_for_shelter_local(shelter: str) -> list[str]:
    from routes.rent_tracking_parts.calculations import _apartment_options_for_shelter

    return _apartment_options_for_shelter(shelter)


def normalize_apartment_number_local(shelter: str, apartment_number: str | None) -> str | None:
    from routes.rent_tracking_parts.calculations import _normalize_apartment_number

    return _normalize_apartment_number(shelter, apartment_number)


def derive_apartment_size_local(shelter: str, apartment_number: str | None) -> str | None:
    from routes.rent_tracking_parts.calculations import _derive_apartment_size_from_assignment

    return _derive_apartment_size_from_assignment(shelter, apartment_number)


def occupied_apartment_numbers_for_shelter(shelter: str) -> set[str]:
    shelter = normalize_shelter_name(shelter)
    if shelter not in {"abba", "gratitude"}:
        return set()

    rows = db_fetchall(
        """
        SELECT apartment_number_snapshot
        FROM resident_rent_configs
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND COALESCE(effective_end_date, '') = ''
          AND COALESCE(apartment_number_snapshot, '') <> ''
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT apartment_number_snapshot
        FROM resident_rent_configs
        WHERE LOWER(COALESCE(shelter, '')) = ?
          AND COALESCE(effective_end_date, '') = ''
          AND COALESCE(apartment_number_snapshot, '') <> ''
        """,
        (shelter,),
    )

    occupied: set[str] = set()
    for row in rows:
        value = row["apartment_number_snapshot"] if isinstance(row, dict) else row[0]
        normalized = normalize_apartment_number_local(shelter, value)
        if normalized:
            occupied.add(normalized)
    return occupied


def available_apartment_options_for_shelter(shelter: str) -> list[str]:
    shelter = normalize_shelter_name(shelter)
    all_options = apartment_options_for_shelter_local(shelter)
    if shelter not in {"abba", "gratitude"}:
        return all_options

    occupied = occupied_apartment_numbers_for_shelter(shelter)
    return [unit for unit in all_options if unit not in occupied]


def availability_map_for_transfer() -> dict[str, list[str]]:
    return {
        "abba": available_apartment_options_for_shelter("abba"),
        "gratitude": available_apartment_options_for_shelter("gratitude"),
    }


def active_rent_config_for_resident(resident_id: int, shelter: str):
    ph = "%s" if g.get("db_kind") == "pg" else "?"
    row = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


def upsert_resident_housing_assignment(
    resident_id: int,
    destination_shelter: str,
    apartment_number: str | None,
) -> None:
    destination_shelter = normalize_shelter_name(destination_shelter)
    apartment_number = normalize_apartment_number_local(destination_shelter, apartment_number)
    apartment_size = derive_apartment_size_local(destination_shelter, apartment_number)

    if destination_shelter == "haven":
        apartment_number = None
        apartment_size = "Bed"

    now = utcnow_iso()
    effective_start_date = now[:10]
    active_config = active_rent_config_for_resident(resident_id, destination_shelter)

    if active_config:
        current_apartment = (active_config.get("apartment_number_snapshot") or "").strip() or None
        current_size = (active_config.get("apartment_size_snapshot") or "").strip() or None

        if current_apartment == apartment_number and current_size == apartment_size:
            return

        db_execute(
            """
            UPDATE resident_rent_configs
            SET effective_end_date = %s,
                updated_at = %s
            WHERE id = %s
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE resident_rent_configs
            SET effective_end_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (effective_start_date, now, active_config["id"]),
        )

        level_snapshot = active_config.get("level_snapshot")
        monthly_rent = active_config.get("monthly_rent") or 0
        is_exempt = active_config.get("is_exempt") or (False if g.get("db_kind") == "pg" else 0)
    else:
        level_snapshot = None
        monthly_rent = 0
        is_exempt = False if g.get("db_kind") == "pg" else 0

    db_execute(
        """
        INSERT INTO resident_rent_configs (
            resident_id,
            shelter,
            level_snapshot,
            apartment_number_snapshot,
            apartment_size_snapshot,
            monthly_rent,
            is_exempt,
            effective_start_date,
            effective_end_date,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO resident_rent_configs (
            resident_id,
            shelter,
            level_snapshot,
            apartment_number_snapshot,
            apartment_size_snapshot,
            monthly_rent,
            is_exempt,
            effective_start_date,
            effective_end_date,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resident_id,
            destination_shelter,
            level_snapshot,
            apartment_number,
            apartment_size,
            monthly_rent,
            is_exempt if g.get("db_kind") == "pg" else (1 if is_exempt else 0),
            effective_start_date,
            None,
            session.get("staff_user_id"),
            now,
            now,
        ),
    )


def load_resident_transfer_context(
    *,
    resident_id: int,
    current_shelter: str,
    all_shelters: list[str],
    next_url: str,
    destination_shelter_prefill: str,
):
    resident = db_fetchone(
        f"SELECT * FROM residents WHERE id = {('%s' if g.get('db_kind') == 'pg' else '?')} AND LOWER(COALESCE(shelter, '')) = {('%s' if g.get('db_kind') == 'pg' else '?')}",
        (resident_id, current_shelter),
    )
    if not resident:
        return None

    from_shelter = normalize_shelter_name(row_value(resident, "shelter", 1, ""))

    shelter_choices = [s for s in all_shelters if s in move_supporting_shelters()]
    if same_shelter_housing_update_allowed(from_shelter) and from_shelter not in shelter_choices:
        shelter_choices.append(from_shelter)

    shelter_choices = sorted(set(shelter_choices))
    active_config = active_rent_config_for_resident(resident_id, from_shelter)
    current_apartment_number = (active_config or {}).get("apartment_number_snapshot")
    current_apartment_size = (
        derive_apartment_size_local(from_shelter, current_apartment_number)
        or (active_config or {}).get("apartment_size_snapshot")
    )

    availability_map = availability_map_for_transfer()
    apartment_options = availability_map.get(destination_shelter_prefill, [])

    return ResidentTransferContext(
        resident=resident,
        resident_id=resident_id,
        current_shelter=current_shelter,
        from_shelter=from_shelter,
        all_shelters=all_shelters,
        shelter_choices=shelter_choices,
        next_url=next_url,
        active_config=active_config,
        current_apartment_number=current_apartment_number,
        current_apartment_size=current_apartment_size,
        destination_shelter_prefill=destination_shelter_prefill,
        availability_map=availability_map,
        apartment_options=apartment_options,
    )


def extract_resident_transfer_form_data(context: ResidentTransferContext, request_form) -> ResidentTransferFormData:
    to_shelter = normalize_shelter_name(request_form.get("to_shelter"))
    note = (request_form.get("note") or "").strip()
    apartment_number = normalize_apartment_number_local(to_shelter, request_form.get("apartment_number"))
    apartment_size = derive_apartment_size_local(to_shelter, apartment_number)
    available_apartments = context.availability_map.get(to_shelter, [])
    same_shelter_move = to_shelter == context.from_shelter

    if to_shelter == "haven":
        apartment_number = None
        apartment_size = "Bed"

    return ResidentTransferFormData(
        to_shelter=to_shelter,
        note=note,
        apartment_number=apartment_number,
        apartment_size=apartment_size,
        available_apartments=available_apartments,
        same_shelter_move=same_shelter_move,
    )


def validate_resident_transfer_form(
    *,
    context: ResidentTransferContext,
    form: ResidentTransferFormData,
) -> str | None:
    if form.to_shelter not in context.shelter_choices:
        return "Select a valid shelter."

    if form.to_shelter in {"abba", "gratitude"} and not form.apartment_number:
        return "Apartment number is required for Abba and Gratitude moves."

    if (
        form.to_shelter in {"abba", "gratitude"}
        and form.apartment_number not in form.available_apartments
    ):
        return "That apartment is not available."

    if form.same_shelter_move and not same_shelter_housing_update_allowed(context.from_shelter):
        return "This shelter does not use same shelter apartment reassignment here."

    if form.same_shelter_move:
        current_normalized_apartment = normalize_apartment_number_local(
            context.from_shelter,
            context.current_apartment_number,
        )
        if current_normalized_apartment == form.apartment_number:
            return "No housing change detected."

    return None


def apply_same_shelter_housing_move(
    *,
    resident_id: int,
    destination_shelter: str,
    apartment_number: str | None,
) -> None:
    upsert_resident_housing_assignment(
        resident_id=resident_id,
        destination_shelter=destination_shelter,
        apartment_number=apartment_number,
    )


def apply_cross_shelter_transfer(
    *,
    resident_id: int,
    resident_identifier: str,
    from_shelter: str,
    to_shelter: str,
    note: str,
    apartment_number: str | None,
    transfer_recorder,
) -> None:
    with db_transaction():
        transfer_recorder(
            resident_id=resident_id,
            from_shelter=from_shelter,
            to_shelter=to_shelter,
            note=note,
        )

        db_execute(
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resident_id,
                from_shelter,
                "check_out",
                utcnow_iso(),
                session.get("staff_user_id"),
                f"Transferred to {to_shelter}. {note}".strip(),
            ),
        )

        db_execute(
            """
            UPDATE resident_passes
            SET shelter = %s,
                updated_at = %s
            WHERE LOWER(COALESCE(shelter, '')) = %s
              AND resident_id = %s
              AND status IN ('pending', 'approved')
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE resident_passes
            SET shelter = ?,
                updated_at = ?
            WHERE LOWER(COALESCE(shelter, '')) = ?
              AND resident_id = ?
              AND status IN ('pending', 'approved')
            """,
            (to_shelter, utcnow_iso(), from_shelter, resident_id),
        )

        db_execute(
            f"""
            UPDATE transport_requests
            SET shelter = {('%s' if g.get('db_kind') == 'pg' else '?')}
            WHERE LOWER(COALESCE(shelter, '')) = {('%s' if g.get('db_kind') == 'pg' else '?')}
              AND resident_identifier = {('%s' if g.get('db_kind') == 'pg' else '?')}
              AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            "UPDATE residents SET shelter = %s WHERE id = %s"
            if g.get("db_kind") == "pg"
            else "UPDATE residents SET shelter = ? WHERE id = ?",
            (to_shelter, resident_id),
        )

        upsert_resident_housing_assignment(
            resident_id=resident_id,
            destination_shelter=to_shelter,
            apartment_number=apartment_number,
        )


def build_same_shelter_housing_flash(destination_shelter: str, apartment_number: str | None) -> str:
    return f"Housing updated for {destination_shelter}. Apartment {apartment_number or 'cleared'} saved."


def build_cross_shelter_transfer_flash(
    *,
    from_shelter: str,
    to_shelter: str,
    apartment_number: str | None,
) -> str:
    if to_shelter in {"abba", "gratitude"}:
        return (
            f"Resident transferred from {from_shelter} to {to_shelter} "
            f"and assigned to apartment {apartment_number}."
        )

    if to_shelter == "haven":
        return (
            f"Resident transferred from {from_shelter} to {to_shelter}. "
            "Apartment assignment cleared for dorm style housing."
        )

    return f"Resident transferred from {from_shelter} to {to_shelter}."
