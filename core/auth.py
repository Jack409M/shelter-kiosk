from functools import wraps
from flask import session, redirect, url_for


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "staff_user_id" not in session:
            return redirect(url_for("staff_login"))
        return f(*args, **kwargs)

    return wrapper
