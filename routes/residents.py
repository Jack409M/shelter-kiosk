from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter
from routes.resident_parts.create import staff_residents_post_view
from routes.resident_parts.listing import staff_residents_view
from routes.resident_parts.status import staff_resident_set_active_view
from routes.resident_parts.transfer import staff_resident_transfer_view


residents = Blueprint("residents", __name__)


@residents.get("/staff/residents")
@require_login
@require_shelter
def staff_residents():
    return staff_residents_view()


@residents.post("/staff/residents")
@require_login
@require_shelter
def staff_residents_post():
    return staff_residents_post_view()


@residents.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_resident_transfer(resident_id: int):
    return staff_resident_transfer_view(resident_id)


@residents.post("/staff/residents/<int:resident_id>/set-active")
@require_login
@require_shelter
def staff_resident_set_active(resident_id: int):
    return staff_resident_set_active_view(resident_id)
