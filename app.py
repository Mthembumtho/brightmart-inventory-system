"""
app.py - creates and starts the BrightMart web application.

Run it with:   python app.py
Then open:     http://127.0.0.1:5000

create_app() is called an "application factory". Building the app inside a
function means the automated tests can create a separate copy of the app
that uses a temporary test database instead of the real one.
"""
import os
import secrets

from flask import Flask, g, render_template

import db
import security
from models import ROLE_LABELS


def _load_secret_key(instance_path):
    """The secret key signs the session cookie so users cannot forge a login.
    It is generated once and stored in instance/secret_key.txt (not in the code)."""
    key_file = os.path.join(instance_path, "secret_key.txt")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_file) as f:
        return f.read().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "brightmart.db"),
        BACKUP_FOLDER=os.path.join(app.root_path, "backups"),
        IDLE_TIMEOUT_MINUTES=15,                 # NFR-04
        SESSION_COOKIE_HTTPONLY=True,            # JavaScript cannot read the session cookie
        SESSION_COOKIE_SAMESITE="Lax",           # other websites cannot post forms as the user
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_secret_key(app.instance_path)

    # --- database connection: close it at the end of every request
    app.teardown_appcontext(db.close_db)

    # --- before every request: who is logged in? has the session timed out?
    app.before_request(security.load_logged_in_user)

    # --- the screens, grouped into "blueprints" (one file per area)
    from routes import auth, main, products, reports, sales, stock, users
    for bp in (auth.bp, main.bp, products.bp, sales.bp, stock.bp, reports.bp, users.bp):
        app.register_blueprint(bp)

    # --- values every template can use
    @app.context_processor
    def inject_globals():
        def can(action):
            return g.get("user") is not None and g.user.has_permission(action)
        return {"can": can, "ROLE_LABELS": ROLE_LABELS}

    @app.template_filter("money")
    def money(value):
        """Show numbers as South African rand, e.g. R 1 250.00"""
        return "R {:,.2f}".format(value or 0).replace(",", " ")

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    return app


if __name__ == "__main__":
    app = create_app()
    if not os.path.exists(app.config["DATABASE"]):
        print("No database found - run  python init_db.py  first.")
    else:
        # debug=True: auto-reload on save and detailed error pages.
        # Turn this off (debug=False) when the shop uses the system for real.
        app.run(debug=True)
