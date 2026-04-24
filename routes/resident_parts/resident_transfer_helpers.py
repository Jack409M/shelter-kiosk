from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from flask import session

from core.db import DbRow, db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.NP_placement_service import sync_placement_from_rent_config


@dataclass(frozen=True)
class ResidentTransferContext:
    resident: DbRow
    resident_id: int
    current_shelter: str
    from_shelter: str
    all_shelters: list[str]
    shelter_choices: list[str]
    next_url: str
    active_config: DbRow | None
    current_apartment_number: str | None
    current_apartment_size: str | None
    destination_shelter_prefill: str
    availability_map: dict[str, list[str]]
    apartment_options: list[str]


@dataclass(frozen=True)
class ResidentTransferFormData:
    to_shelter: str
    note: str
    apartment_number: str | None
    apartment_size: str | None
    available_apartments: list[str]
    same_shelter_move: bool


def normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalized_level_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def require_transfer_role() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def return_redirect_target(next_url: str) -> str:
    return (next_url or "").strip()


def row_value(
    row: Mapping[str, Any] | Sequence[Any] | None,
    key: str,
    index: int,
    default: Any = None,
) -> Any:
    if row is None:
        return default

    if isinstance(row, Mapping):
        return row.get(key, default)

    if isinstance(row, Sequence) and not isinstance(row, str | bytes | bytearray):
        if 0 <= index < len(row):
            return row[index]
        return default

    return default


def move_supporting_shelters() -> set[str]:
    return {"abba", "gratitude", "haven"}


def same_shelter_housing_update_allowed(shelter: str) -> bool:
    return shelter in {"abba", "gratitude"}


def apartment_options_for_shelter_local(shelter: str) -> list[str]:
    from routes.rent_tracking_parts.calculations import _apartment_options_for_shelter

    return list(_apartment_options_for_shelter(shelter))


def normalize_apartment_number_local(
    shelter: str,
    apartment_number: str | None,
) -> str | None:
    from routes.rent_tracking_parts.calculations import _normalize_apartment_number

    return _normalize_apartment_number(shelter, apartment_number)


def derive_apartment_size_local(
    shelter: str,
    apartment_number: str | None,
) -> str | None:
    from routes.rent_tracking_parts.calculations import _derive_apartment_size_from_assignment

    return _derive_apartment_size_from_assignment(shelter, apartment_number)


def _require_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise RuntimeError(f"{label} must be an integer, not boolean")
    if not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value


def _clean_note(note: str | None) -> str:
    return (note or "").strip()


def _current_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        return None


def _active_rent_config_sql() -> str:
    return """
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
    """


def occupied_apartment_numbers_for_shelter(shelter: str) -> set[str]:
    normalized_shelter = normalize_shelter_name(shelter)
    if normalized_shelter not in {"abba", "gratitude"}:
        return set()

    try:
        rows = db_fetchall(
            """
            SELECT apartment_number_snapshot
            FROM resident_rent_configs
            WHERE LOWER(COALESCE(shelter, '')) = %s
              AND COALESCE(effective_end_date, '') = ''
              AND COALESCE(apartment_number_snapshot, '') <> ''
            """,
            (normalized_shelter,),
        )
    except Exception:
        return set()

    occupied: set[str] = set()
    for row in rows:
        value = row.get("apartment_number_snapshot")
        normalized = normalize_apartment_number_local(normalized_shelter, value)
        if normalized:
            occupied.add(normalized)

    return occupied


def available_apartment_options_for_shelter(shelter: str) -> list[str]:
    normalized_shelter = normalize_shelter_name(shelter)
    all_options = apartment_options_for_shelter_local(normalized_shelter)

    if normalized_shelter not in {"abba", "gratitude"}:
        return all_options

    occupied = occupied_apartment_numbers_for_shelter(normalized_shelter)
    return [unit for unit in all_options if unit not in occupied]


def availability_map_for_transfer() -> dict[str, list[str]]:
    return {
        "abba": available_apartment_options_for_shelter("abba"),
        "gratitude": available_apartment_options_for_shelter("gratitude"),
    }


def active_rent_config_for_resident(resident_id: int, shelter: str) -> DbRow | None:
    normalized_shelter = normalize_shelter_name(shelter)
    try:
        return db_fetchone(_active_rent_config_sql(), (resident_id, normalized_shelter))
    except Exception:
        return None


def _close_active_rent_config(config_id: int, effective_end_date: str, now: str) -> None:
    db_execute(
        """
        UPDATE resident_rent_configs
        SET effective_end_date = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (effective_end_date, now, config_id),
    )


def _insert_rent_config(
    *,
    resident_id: int,
    destination_shelter: str,
    level_snapshot: Any,
    apartment_number: str | None,
    apartment_size: str | None,
    monthly_rent: Any,
    is_exempt: bool,
    effective_start_date: str,
    now: str,
    created_by_staff_user_id: int | None,
) -> None:
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
        """,
        (
            resident_id,
            destination_shelter,
            level_snapshot,
            apartment_number,
            apartment_size,
            monthly_rent,
            is_exempt,
            effective_start_date,
            None,
            created_by_staff_user_id,
            now,
            now,
        ),
    )


def upsert_resident_housing_assignment(
    resident_id: int,
    destination_shelter: str,
    apartment_number: str | None,
) -> None:
    normalized_destination_shelter = normalize_shelter_name(destination_shelter)
    normalized_apartment_number = normalize_apartment_number_local(
        normalized_destination_shelter,
        apartment_number,
    )
    apartment_size = derive_apartment_size_local(
        normalized_destination_shelter,
        normalized_apartment_number,
    )

    if normalized_destination_shelter == "haven":
        normalized_apartment_number = None
        apartment_size = "Bed"

    now = utcnow_iso()
    effective_start_date = now[:10]
    active_config = active_rent_config_for_resident(resident_id, normalized_destination_shelter)

    if active_config is not None:
        active_config_id = _require_int(active_config.get("id"), label="active rent config id")
        current_apartment = (active_config.get("apartment_number_snapshot") or "").strip() or None
        current_size = (active_config.get("apartment_size_snapshot") or "").strip() or None

        if current_apartment == normalized_apartment_number and current_size == apartment_size:
            return

        _close_active_rent_config(active_config_id, effective_start_date, now)

        level_snapshot = active_config.get("level_snapshot")
        monthly_rent = active_config.get("monthly_rent") or 0
        is_exempt = bool(active_config.get("is_exempt"))
    else:
        level_snapshot = None
        monthly_rent = 0
        is_exempt = False

    try:
        _insert_rent_config(
            resident_id=resident_id,
            destination_shelter=normalized_destination_shelter,
            level_snapshot=level_snapshot,
            apartment_number=normalized_apartment_number,
            apartment_size=apartment_size,
            monthly_rent=monthly_rent,
            is_exempt=is_exempt,
            effective_start_date=effective_start_date,
            now=now,
            created_by_staff_user_id=_current_staff_user_id(),
        )
        sync_placement_from_rent_config(
            resident_id=resident_id,
            enrollment_id=None,
            shelter=normalized_destination_shelter,
            program_level=level_snapshot,
            apartment_number=normalized_apartment_number,
            effective_date=effective_start_date,
            change_reason="housing_assignment",
            note="Synced from apartment assignment.",
            now=now,
        )
    except Exception:
        return


def load_resident_transfer_context(
    *,
    resident_id: int,
    current_shelter: str,
    all_shelters: list[str],
    next_url: str,
    destination_shelter_prefill: str,
) -> ResidentTransferContext | None:
    normalized_current_shelter = normalize_shelter_name(current_shelter)
    normalized_prefill = (
        normalize_shelter_name(destination_shelter_prefill) or normalized_current_shelter
    )

    resident = db_fetchone(
        """
        SELECT *
        FROM residents
        WHERE id = %s
          AND LOWER(COALESCE(shelter, '')) = %s
        """,
        (resident_id, normalized_current_shelter),
    )
    if resident is None:
        return None

    from_shelter = normalize_shelter_name(str(resident.get("shelter") or ""))

    shelter_choices = [s for s in all_shelters if s in move_supporting_shelters()]
    if same_shelter_housing_update_allowed(from_shelter) and from_shelter not in shelter_choices:
        shelter_choices.append(from_shelter)

    shelter_choices = sorted(set(shelter_choices))
    active_config = active_rent_config_for_resident(resident_id, from_shelter)
    current_apartment_number = (
        (active_config or {}).get("apartment_number_snapshot")
        if active_config is not None
        else None
    )
    current_apartment_size = derive_apartment_size_local(
        from_shelter, current_apartment_number
    ) or ((active_config or {}).get("apartment_size_snapshot") if active_config else None)

    availability_map = availability_map_for_transfer()
    apartment_options = list(availability_map.get(normalized_prefill, []))

    return ResidentTransferContext(
        resident=resident,
        resident_id=resident_id,
        current_shelter=normalized_current_shelter,
        from_shelter=from_shelter,
        all_shelters=list(all_shelters),
        shelter_choices=shelter_choices,
        next_url=return_redirect_target(next_url),
        active_config=active_config,
        current_apartment_number=current_apartment_number,
        current_apartment_size=current_apartment_size,
        destination_shelter_prefill=normalized_prefill,
        availability_map=availability_map,
        apartment_options=apartment_options,
    )


def extract_resident_transfer_form_data(
    context: ResidentTransferContext,
    request_form: Mapping[str, Any],
) -> ResidentTransferFormData:
    to_shelter = normalize_shelter_name(str(request_form.get("to_shelter") or ""))
    note = _clean_note(str(request_form.get("note") or ""))
    apartment_number = normalize_apartment_number_local(
        to_shelter,
        str(request_form.get("apartment_number") or ""),
    )
    apartment_size = derive_apartment_size_local(to_shelter, apartment_number)
    available_apartments = list(context.availability_map.get(to_shelter, []))
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

    resident_level = _normalized_level_text(context.resident.get("program_level"))
    if (
        resident_level == "9"
        and form.to_shelter in {"abba", "gratitude"}
        and form.apartment_number
    ):
        return "Level 9 residents cannot be assigned to DWC apartments."

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


def _update_pending_passes_for_transfer(
    *,
    resident_id: int,
    from_shelter: str,
    to_shelter: str,
    updated_at: str,
) -> None:
    db_execute(
        """
        UPDATE resident_passes
        SET shelter = %s,
            updated_at = %s
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND resident_id = %s
          AND status IN ('pending', 'approved')
        """,
        (to_shelter, updated_at, from_shelter, resident_id),
    )


def _update_pending_transport_requests_for_transfer(
    *,
    resident_identifier: str,
    from_shelter: str,
    to_shelter: str,
) -> None:
    if not resident_identifier:
        return

    db_execute(
        """
        UPDATE transport_requests
        SET shelter = %s
        WHERE LOWER(COALESCE(shelter, '')) = %s
          AND resident_identifier = %s
          AND status = 'pending'
        """,
        (to_shelter, from_shelter, resident_identifier),
    )


def _update_resident_shelter(
    *,
    resident_id: int,
    to_shelter: str,
) -> None:
    db_execute(
        """
        UPDATE residents
        SET shelter = %s
        WHERE id = %s
        """,
        (to_shelter, resident_id),
    )


def _insert_transfer_checkout_event(
    *,
    resident_id: int,
    from_shelter: str,
    to_shelter: str,
    note: str,
) -> None:
    note_text = f"Transferred to {to_shelter}. {note}".strip()
    db_execute(
        """
        INSERT INTO attendance_events (
            resident_id,
            shelter,
            event_type,
            event_time,
            staff_user_id,
            note
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            from_shelter,
            "check_out",
            utcnow_iso(),
            _current_staff_user_id(),
            note_text,
        ),
    )


def apply_cross_shelter_transfer(
    *,
    resident_id: int,
    resident_identifier: str,
    from_shelter: str,
    to_shelter: str,
    note: str,
    apartment_number: str | None,
    transfer_recorder: Callable[..., Any],
) -> None:
    normalized_from_shelter = normalize_shelter_name(from_shelter)
    normalized_to_shelter = normalize_shelter_name(to_shelter)
    cleaned_note = _clean_note(note)
    now = utcnow_iso()

    with db_transaction():
        transfer_recorder(
            resident_id=resident_id,
            from_shelter=normalized_from_shelter,
            to_shelter=normalized_to_shelter,
            note=cleaned_note,
        )

        _insert_transfer_checkout_event(
            resident_id=resident_id,
            from_shelter=normalized_from_shelter,
            to_shelter=normalized_to_shelter,
            note=cleaned_note,
        )

        _update_pending_passes_for_transfer(
            resident_id=resident_id,
            from_shelter=normalized_from_shelter,
            to_shelter=normalized_to_shelter,
            updated_at=now,
        )

        _update_pending_transport_requests_for_transfer(
            resident_identifier=resident_identifier.strip(),
            from_shelter=normalized_from_shelter,
            to_shelter=normalized_to_shelter,
        )

        _update_resident_shelter(
            resident_id=resident_id,
            to_shelter=normalized_to_shelter,
        )

        upsert_resident_housing_assignment(
            resident_id=resident_id,
            destination_shelter=normalized_to_shelter,
            apartment_number=apartment_number,
        )


def build_same_shelter_housing_flash(
    destination_shelter: str,
    apartment_number: str | None,
) -> str:
    return (
        f"Housing updated for {destination_shelter}. "
        f"Apartment {apartment_number or 'cleared'} saved."
    )


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
