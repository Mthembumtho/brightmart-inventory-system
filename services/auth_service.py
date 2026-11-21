"""
AuthService - login, access logging and user management.
Covers FR-01, FR-03, FR-04 and NFR-04 (Part 1, Section 5.2).
"""
from werkzeug.security import check_password_hash, generate_password_hash

from db import now
from models import ROLE_LABELS, User
from services import ServiceError

MIN_PASSWORD_LENGTH = 8   # NFR-04


def hash_password(password):
    # PBKDF2 with SHA-256, as promised in Part 1 (Section 6.1, NFR-04).
    # (Werkzeug's default is scrypt, so we name the method explicitly.)
    return generate_password_hash(password, method="pbkdf2:sha256")


class AuthService:

    @staticmethod
    def authenticate(db, username, password):
        """Return a User if the details are correct, otherwise raise ServiceError."""
        # 1. Check for empty fields first
        if not username or not password:
            raise ServiceError("Please enter username and password")

        # 2. Find the user and ensure they are active (FR-03)
        row = db.execute(
            "SELECT * FROM User WHERE username = ? AND is_active = 1", (username.strip(),)
        ).fetchone()

        # 3. Verify the password against the stored hash (NFR-04).
        #    The message is the SAME for a wrong username and a wrong password,
        #    so an attacker cannot discover which usernames exist.
        if row is None or not check_password_hash(row["password_hash"], password):
            raise ServiceError("Invalid username or password")

        # 5. Log the successful login (step 4, creating the session, is done in the route)
        AuthService.log_access(db, row["user_id"], "LOGIN")
        return User(row["user_id"], row["username"], row["role"], bool(row["is_active"]))

    @staticmethod
    def log_access(db, user_id, event_type, detail=None):
        """FR-04: write one line to the access log."""
        db.execute(
            "INSERT INTO AccessLog (user_id, event_type, event_detail, event_datetime) "
            "VALUES (?, ?, ?, ?)",
            (user_id, event_type, detail, now()),
        )

    # ------------------------------------------------------------------
    # User management (FR-03) - Store Manager only
    # ------------------------------------------------------------------
    @staticmethod
    def _validate(username, role, password=None, password_required=True):
        if not username or not username.strip():
            raise ServiceError("Username is required")
        if role not in ROLE_LABELS:
            raise ServiceError("Please choose a valid role")
        if password_required or password:
            if not password or len(password) < MIN_PASSWORD_LENGTH:
                raise ServiceError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    @staticmethod
    def create_user(db, username, password, role):
        AuthService._validate(username, role, password)
        exists = db.execute("SELECT 1 FROM User WHERE username = ?", (username.strip(),)).fetchone()
        if exists:
            raise ServiceError("That username is already taken")
        db.execute(
            "INSERT INTO User (username, password_hash, role) VALUES (?, ?, ?)",
            (username.strip(), hash_password(password), role),
        )

    @staticmethod
    def update_user(db, user_id, username, role, new_password=None, current_user_id=None):
        AuthService._validate(username, role, new_password, password_required=False)
        clash = db.execute(
            "SELECT 1 FROM User WHERE username = ? AND user_id <> ?", (username.strip(), user_id)
        ).fetchone()
        if clash:
            raise ServiceError("That username is already taken")
        if user_id == current_user_id and role != "MANAGER":
            raise ServiceError("You cannot remove your own Store Manager role")
        db.execute("UPDATE User SET username = ?, role = ? WHERE user_id = ?",
                   (username.strip(), role, user_id))
        if new_password:
            db.execute("UPDATE User SET password_hash = ? WHERE user_id = ?",
                       (hash_password(new_password), user_id))

    @staticmethod
    def set_active(db, user_id, active, current_user_id):
        """Deactivate (or re-activate) a user. Users are never deleted."""
        if user_id == current_user_id and not active:
            raise ServiceError("You cannot deactivate your own account")
        db.execute("UPDATE User SET is_active = ? WHERE user_id = ?", (1 if active else 0, user_id))

    @staticmethod
    def list_users(db):
        return db.execute("SELECT * FROM User ORDER BY is_active DESC, username").fetchall()

    @staticmethod
    def get_user(db, user_id):
        return db.execute("SELECT * FROM User WHERE user_id = ?", (user_id,)).fetchone()

    @staticmethod
    def access_log(db, limit=500):
        return db.execute(
            "SELECT a.*, u.username FROM AccessLog a JOIN User u ON u.user_id = a.user_id "
            "ORDER BY a.log_id DESC LIMIT ?", (limit,)
        ).fetchall()
