from functools import wraps
from flask import session, redirect, url_for


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "staff_user_id" not in session:
            return redirect(url_for("staff_login"))
        return f(*args, **kwargs)

    return wrapper

def require_shelter(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "shelter" not in session:
            return redirect(url_for("staff_select_shelter"))
        return fn(*args, **kwargs)
