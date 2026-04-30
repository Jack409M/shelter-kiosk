from __future__ import annotations

from flask import g


def audit_where_from_request(request):
    kind = g.get("db_kind")
    where = []
    params = []

    def add_eq(field, key):
        value = (request.args.get(key) or "").strip()
        if value:
            where.append(f"{field} = " + ("%s" if kind == "pg" else "?"))
            params.append(value)

    add_eq("a.shelter", "shelter")
    add_eq("a.entity_type", "entity_type")
    add_eq("a.action_type", "action_type")

    staff_user_id = (request.args.get("staff_user_id") or "").strip()
    if staff_user_id.isdigit():
        where.append("a.staff_user_id = " + ("%s" if kind == "pg" else "?"))
        params.append(int(staff_user_id))

    q = (request.args.get("q") or "").strip()
    if q:
        like_op = "ILIKE" if kind == "pg" else "LIKE"
        ph = "%s" if kind == "pg" else "?"
        where.append(
            "("
            f"CAST(a.id AS TEXT) {like_op} {ph} OR "
            f"COALESCE(a.action_details, '') {like_op} {ph} OR "
            f"COALESCE(a.action_type, '') {like_op} {ph} OR "
            f"COALESCE(a.entity_type, '') {like_op} {ph} OR "
            f"COALESCE(su.username, '') {like_op} {ph}"
            ")"
        )
        pattern = f"%{q}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, tuple(params)
