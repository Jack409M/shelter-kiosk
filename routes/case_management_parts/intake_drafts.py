from __future__ import annotations

import json
from typing import Any

from flask import g, session

from core.db import db_execute, db_fetchone
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import draft_display_name
from routes.case_management_parts.helpers import placeholder


def _coerce_form_dict(form: Any) -> dict[str, Any]:
    if form is None:
        return {}

    if hasattr(form, "to_dict"):
        return dict(form.to_dict(flat=True))

    return dict(form)


def _save_intake_draft(
    current_shelter: str,
    form: Any,
    draft_id: int | None = None,
    status: str = "draft",
) -> int:
    ph = placeholder()
    form_dict = _coerce_form_dict(form)
    resident_name = draft_display_name(form_dict)
    entry_date = clean(form_dict.get("entry_date"))
    payload = json.dumps(form_dict, ensure_ascii=False)

    allowed_statuses = {"draft", "pending_duplicate_review"}
    if status not in allowed_statuses:
        status = "draft"

    if g.get("db_kind") == "pg":
        if draft_id is not None:
            row = db_fetchone(
                f"""
                UPDATE intake_drafts
                SET resident_name = {ph},
                    entry_date = {ph},
                    draft_data = {ph}::jsonb,
                    form_payload = {ph},
                    status = {ph},
                    updated_at = NOW()
                WHERE id = {ph}
                  AND status IN ('draft', 'pending_duplicate_review')
                  AND LOWER(COALESCE(shelter, '')) = {ph}
                RETURNING id
                """,
                (
                    resident_name,
                    entry_date,
                    payload,
                    payload,
                    status,
                    draft_id,
                    current_shelter,
                ),
            )
            if row:
                return int(row["id"])

        row = db_fetchone(
            f"""
            INSERT INTO intake_drafts
            (
                shelter,
                status,
                resident_name,
                entry_date,
                draft_data,
                form_payload,
                created_by_user_id,
                created_at,
                updated_at
            )
            VALUES
            (
                {ph},
                {ph},
                {ph},
                {ph},
                {ph}::jsonb,
                {ph},
                {ph},
                NOW(),
                NOW()
            )
            RETURNING id
            """,
            (
                current_shelter,
                status,
                resident_name,
                entry_date,
                payload,
                payload,
                session.get("user_id"),
            ),
        )
        return int(row["id"])

    if draft_id is not None:
        db_execute(
            f"""
            UPDATE intake_drafts
            SET resident_name = {ph},
                entry_date = {ph},
                draft_data = {ph},
                form_payload = {ph},
                status = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
              AND status IN ('draft', 'pending_duplicate_review')
              AND LOWER(COALESCE(shelter, '')) = {ph}
            """,
            (
                resident_name,
                entry_date,
                payload,
                payload,
                status,
                draft_id,
                current_shelter,
            ),
        )
        existing = db_fetchone(
            f"""
            SELECT id
            FROM intake_drafts
            WHERE id = {ph}
              AND status IN ('draft', 'pending_duplicate_review')
              AND LOWER(COALESCE(shelter, '')) = {ph}
            """,
            (draft_id, current_shelter),
        )
        if existing:
            return draft_id

    db_execute(
        f"""
        INSERT INTO intake_drafts
        (
            shelter,
            status,
            resident_name,
            entry_date,
            draft_data,
            form_payload,
            created_by_user_id,
            created_at,
            updated_at
        )
        VALUES
        (
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            {ph},
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (
            current_shelter,
            status,
            resident_name,
            entry_date,
            payload,
            payload,
            session.get("user_id"),
        ),
    )

    row = db_fetchone("SELECT last_insert_rowid() AS id")
    return int(row["id"])


def _load_intake_draft(current_shelter: str, draft_id: int) -> dict[str, Any] | None:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            id,
            resident_name,
            draft_data,
            form_payload,
            status,
            updated_at
        FROM intake_drafts
        WHERE id = {ph}
          AND status IN ('draft', 'pending_duplicate_review')
          AND LOWER(COALESCE(shelter, '')) = {ph}
        """,
        (draft_id, current_shelter),
    )
    if not row:
        return None

    if isinstance(row, dict):
        payload_raw = row.get("draft_data") or row.get("form_payload")
        draft_status = row.get("status")
        draft_id_value = row.get("id")
    else:
        payload_raw = row[2] or row[3]
        draft_status = row[4]
        draft_id_value = row[0]

    try:
        payload = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        payload = {}

    payload["draft_id"] = str(draft_id_value)
    payload["draft_status"] = draft_status or "draft"
    return payload


def _complete_intake_draft(draft_id: int) -> None:
    ph = placeholder()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            UPDATE intake_drafts
            SET status = 'completed',
                updated_at = NOW()
            WHERE id = {ph}
            """,
            (draft_id,),
        )
        return

    db_execute(
        f"""
        UPDATE intake_drafts
        SET status = 'completed',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {ph}
        """,
        (draft_id,),
    )


def _dismiss_intake_draft(draft_id: int) -> None:
    ph = placeholder()

    if g.get("db_kind") == "pg":
        db_execute(
            f"""
            UPDATE intake_drafts
            SET status = 'dismissed',
                updated_at = NOW()
            WHERE id = {ph}
            """,
            (draft_id,),
        )
        return

    db_execute(
        f"""
        UPDATE intake_drafts
        SET status = 'dismissed',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {ph}
        """,
        (draft_id,),
    )
