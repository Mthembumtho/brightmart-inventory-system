"""Login, passwords, access log and idle timeout - FR-01, FR-03, FR-04, NFR-04."""
import time

from conftest import login


def test_tc01_valid_login_opens_dashboard(app):
    """TC-01 (FR-01): correct username and password logs the user in."""
    c = app.test_client()
    r = login(c, "manager")
    assert r.status_code == 302 and r.headers["Location"] == "/"
    assert b"Low-stock alerts" in c.get("/").data


def test_tc02_wrong_password_and_unknown_user_give_same_message(app):
    """TC-02 (FR-01, NFR-04): the error never reveals whether the username exists."""
    c = app.test_client()
    wrong_pw = c.post("/login", data={"username": "manager", "password": "wrong-password"})
    no_user = c.post("/login", data={"username": "nobody", "password": "whatever123"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert b"Invalid username or password" in wrong_pw.data
    assert b"Invalid username or password" in no_user.data


def test_tc03_passwords_are_stored_hashed_with_pbkdf2(db):
    """TC-03 (NFR-04): no plain-text passwords in the database."""
    rows = db.execute("SELECT username, password_hash FROM User").fetchall()
    for row in rows:
        assert row["password_hash"].startswith("pbkdf2:sha256")
        assert "Manager@123" not in row["password_hash"]


def test_tc04_deactivated_user_cannot_log_in(app, as_manager, db):
    """TC-04 (FR-03): a deactivated account is refused even with the right password."""
    musa = db.execute("SELECT user_id FROM User WHERE username = 'musa'").fetchone()[0]
    as_manager.post(f"/users/{musa}/toggle")
    r = login(app.test_client(), "musa")
    assert r.status_code == 401


def test_tc05_login_and_logout_are_logged(app, db):
    """TC-05 (FR-04): access log records LOGIN and LOGOUT with date and time."""
    c = app.test_client()
    login(c, "owner")
    c.post("/logout")
    events = [r["event_type"] for r in db.execute(
        "SELECT event_type FROM AccessLog a JOIN User u ON u.user_id = a.user_id "
        "WHERE u.username = 'owner' ORDER BY log_id")]
    assert events == ["LOGIN", "LOGOUT"]


def test_tc06_idle_timeout_logs_user_out(app, db):
    """TC-06 (NFR-04): after 15 idle minutes the next click goes to the login page."""
    c = app.test_client()
    login(c, "lindelwe")
    with c.session_transaction() as s:              # pretend the last click was 16 minutes ago
        s["last_activity"] = time.time() - 16 * 60
    r = c.get("/sales/new")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    last = db.execute("SELECT event_type FROM AccessLog ORDER BY log_id DESC LIMIT 1").fetchone()
    assert last["event_type"] == "TIMEOUT"


def test_tc07_activity_within_15_minutes_keeps_session(app):
    """TC-07 (NFR-04): a user active 14 minutes ago is NOT logged out."""
    c = app.test_client()
    login(c, "lindelwe")
    with c.session_transaction() as s:
        s["last_activity"] = time.time() - 14 * 60
    assert c.get("/sales/new").status_code == 200


def test_tc08_short_passwords_are_rejected(as_manager, db):
    """TC-08 (NFR-04): passwords must be at least 8 characters."""
    r = as_manager.post("/users/new", data={"username": "thabo", "password": "short", "role": "SALES"},
                        follow_redirects=True)
    assert b"at least 8 characters" in r.data
    assert db.execute("SELECT 1 FROM User WHERE username = 'thabo'").fetchone() is None
