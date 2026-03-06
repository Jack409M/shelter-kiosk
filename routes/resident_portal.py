from flask import Blueprint, render_template, redirect, url_for, session

resident_portal = Blueprint(
    "resident_portal",
    __name__,
    url_prefix="/resident"
)


@resident_portal.route("/home")
def home():
    if not session.get("resident_id"):
        return redirect(url_for("resident_signin"))

    return render_template("resident_home.html")
