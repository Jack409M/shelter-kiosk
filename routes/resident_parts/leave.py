from __future__ import annotations

from flask import redirect, url_for


def resident_leave_view():
    return redirect(url_for("resident_requests.resident_pass_request"))
