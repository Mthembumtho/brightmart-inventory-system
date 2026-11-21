"""
BackupService - one-click local database backup (NFR-03).

SQLite's built-in backup API copies the database safely even while the
system is in use (simply copying the file while a sale is being saved
could produce a broken copy).
"""
import os
import sqlite3
from datetime import datetime


class BackupService:

    @staticmethod
    def create_backup(db, backup_folder):
        os.makedirs(backup_folder, exist_ok=True)
        filename = "brightmart_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"
        path = os.path.join(backup_folder, filename)
        target = sqlite3.connect(path)
        try:
            db.backup(target)
        finally:
            target.close()
        return filename

    @staticmethod
    def list_backups(backup_folder):
        if not os.path.isdir(backup_folder):
            return []
        files = []
        for name in sorted(os.listdir(backup_folder), reverse=True):
            if name.startswith("brightmart_backup_") and name.endswith(".db"):
                full = os.path.join(backup_folder, name)
                files.append({"name": name, "size_kb": round(os.path.getsize(full) / 1024, 1),
                              "created": datetime.fromtimestamp(os.path.getmtime(full))
                              .strftime("%Y-%m-%d %H:%M")})
        return files
