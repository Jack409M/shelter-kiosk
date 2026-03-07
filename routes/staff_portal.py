from flask import Blueprint, render_template
from core.auth import require_login, require_shelter
from flask import session, g, render_template

staff_portal = Blueprint("staff_portal", __name__)


@staff_portal.route("/_staff_test/attendance")
def staff_attendance_test():
    return "staff attendance blueprint working"

