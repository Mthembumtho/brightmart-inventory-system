"""Login and logout (FR-01, FR-04, NFR-04) - Figure 4.6.1."""
import time

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from db import get_db
from services import ServiceError
from services.auth_service import AuthService

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        try:
            user = AuthService.authenticate(get_db(), username, password)
        except ServiceError as e:
            flash(str(e), "error")
            return render_template("login.html", username=username), 401

        # 4. Create the session and set the initial idle timer
        session.clear()                       # throw away any old session first
        session["user_id"] = user.user_id
        session["last_activity"] = time.time()

        next_page = request.args.get("next", "")
        if next_page.startswith("/") and not next_page.startswith("//"):
            return redirect(next_page)        # only redirect inside this site
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        AuthService.log_access(get_db(), g.user.user_id, "LOGOUT")
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
