from flask import Blueprint, redirect, render_template, url_for


public = Blueprint("public", __name__)


@public.get("/privacy")
def privacy_policy():
    return render_template("privacy.html")


@public.get("/terms")
def terms_and_conditions():
    return render_template("terms.html")


@public.route("/")
def public_home():
    return render_template("public_home.html")
