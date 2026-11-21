"""User management (FR-03) - Store Manager only."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db
from security import permission_required
from services import ServiceError
from services.auth_service import AuthService

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@permission_required("manage_users")
def list_users():
    return render_template("users/list.html", users=AuthService.list_users(get_db()))


@bp.route("/new", methods=["GET", "POST"])
@permission_required("manage_users")
def new_user():
    if request.method == "POST":
        try:
            AuthService.create_user(get_db(), request.form.get("username", ""),
                                    request.form.get("password", ""), request.form.get("role", ""))
            flash("User created.", "success")
            return redirect(url_for("users.list_users"))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("users/form.html", user=request.form, is_new=True)


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required("manage_users")
def edit_user(user_id):
    db = get_db()
    user = AuthService.get_user(db, user_id)
    if user is None:
        abort(404)
    if request.method == "POST":
        try:
            AuthService.update_user(db, user_id, request.form.get("username", ""),
                                    request.form.get("role", ""),
                                    request.form.get("password", "") or None,
                                    current_user_id=g.user.user_id)
            flash("User updated.", "success")
            return redirect(url_for("users.list_users"))
        except ServiceError as e:
            flash(str(e), "error")
            user = request.form
    return render_template("users/form.html", user=user, is_new=False, user_id=user_id)


@bp.route("/<int:user_id>/toggle", methods=["POST"])
@permission_required("manage_users")
def toggle_user(user_id):
    db = get_db()
    user = AuthService.get_user(db, user_id)
    if user is None:
        abort(404)
    try:
        AuthService.set_active(db, user_id, not user["is_active"], g.user.user_id)
        flash(f"{user['username']} {'deactivated' if user['is_active'] else 're-activated'}.",
              "success")
    except ServiceError as e:
        flash(str(e), "error")
    return redirect(url_for("users.list_users"))