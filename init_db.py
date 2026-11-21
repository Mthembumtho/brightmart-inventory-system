"""
init_db.py - creates a fresh, empty database with the default Store Manager.

    python init_db.py              -> empty database
    python init_db.py --demo       -> database with sample data for testing/screenshots

WARNING: this deletes the existing database. Make a backup first!
"""
import os
import sys

from app import create_app
from db import get_db, init_db


def main():
    app = create_app()
    path = app.config["DATABASE"]
    if os.path.exists(path):
        answer = input(f"{path} already exists. Delete it and start again? (yes/no): ")
        if answer.strip().lower() != "yes":
            print("Nothing changed.")
            return
        os.remove(path)

    with app.app_context():
        init_db()
        print("Database created.")
        print("Default Store Manager ->  username: manager   password: Manager@123")
        print("Change this password after the first login (Users > Edit).")
        if "--demo" in sys.argv:
            from seed_demo import seed
            seed(get_db())
            print("Demo data added (suppliers, products, staff, sales).")


if __name__ == "__main__":
    main()
