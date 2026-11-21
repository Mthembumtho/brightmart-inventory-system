"""
security.py - login checks, role checks and the idle timeout.

A "decorator" is the @something line placed above a route. It runs BEFORE
the route, and can stop the request. That way the security rule is written
once here, instead of being copied into every route.
"""
import time
from functools import wraps

from flask import (abort, current_app, flash, g, jsonify, redirect, request, session,
                   url_for)

from db import get_db
from models import User
from services.auth_service import AuthService


def load_logged_in_user():
    """Runs before EVERY request (registered in app.py).

    1. Finds who is logged in and puts them in g.user.
    2. Enforces the 15-minute idle timeout (NFR-04, check_session in Part 1 5.2).
    """
    g.user = None
    user_id = session.get("user_id")
    if user_id is None or request.endpoint == "static":
        return

    db = get_db()
    row = db.execute("SELECT * FROM User WHERE user_id = ?", (user_id,)).fetchone()
    if row is None or not row["is_active"]:
        # account was deactivated while they were logged in (FR-03)
        session.clear()
        return

    timeout_seconds = current_app.config["IDLE_TIMEOUT_MINUTES"] * 60
    last_activity = session.get("last_activity", 0)
    if time.time() - last_activity > timeout_seconds:
        AuthService.log_access(db, user_id, "TIMEOUT")
        session.clear()
        flash("You were logged out after "
              f"{current_app.config['IDLE_TIMEOUT_MINUTES']} minutes of inactivity.", "info")
        return

    session["last_activity"] = time.time()   # reset the idle timer
    g.user = User(row["user_id"], row["username"], row["role"], bool(row["is_active"]))


def _wants_json():
    return request.is_json or request.path.startswith("/api/")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if _wants_json():
                return jsonify(ok=False, message="Your session has expired. Please log in again.",
                               login=True), 401
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def permission_required(action):
    """Use as @permission_required("record_sale"). Refuses other roles (FR-02, NFR-04)."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not g.user.has_permission(action):
                # Refused attempts are written to the access log (NFR-05)
                AuthService.log_access(get_db(), g.user.user_id, "ACCESS_DENIED", request.path)
                if _wants_json():
                    return jsonify(ok=False, message="You do not have permission to do that."), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
