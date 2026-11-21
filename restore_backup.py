"""
restore_backup.py - puts a backup copy back as the live database (NFR-03).

    python restore_backup.py backups\\brightmart_backup_20261116_170500.db

Stop the system (Ctrl + C) before restoring. The current database is kept
as instance\\brightmart_before_restore.db, just in case.
"""
import os
import shutil
import sqlite3
import sys

from app import create_app


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return
    backup = sys.argv[1]
    if not os.path.exists(backup):
        print(f"Backup file not found: {backup}")
        return

    # Check the backup is a real BrightMart database before using it
    try:
        conn = sqlite3.connect(backup)
        conn.execute("SELECT COUNT(*) FROM Product").fetchone()
        conn.close()
    except sqlite3.Error:
        print("That file is not a valid BrightMart backup. Nothing changed.")
        return

    live = create_app().config["DATABASE"]
    if os.path.exists(live):
        shutil.copy2(live, live.replace("brightmart.db", "brightmart_before_restore.db"))
    shutil.copy2(backup, live)
    print(f"Restored {backup}. Start the system again with  python app.py")


if __name__ == "__main__":
    main()
