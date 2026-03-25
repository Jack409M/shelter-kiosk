from flask import Blueprint, render_template
from core.auth import require_login, require_shelter

shelter_operations = Blueprint(
    "shelter_operations",
    __name__,
    url_prefix="/staff/shelter-operations",
)


@shelter_operations.route("/chores")
@require_login
@require_shelter
def chore_management():
    return render_template("shelter_operations/chore_management.html")
