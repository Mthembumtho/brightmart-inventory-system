"""
load_test.py - checks NFR-02 (speed) and NFR-09 (scalability).

Builds a SEPARATE temporary database with 2,000 products and 50,000 sales,
then times the busiest screens. Your real database is not touched.

    python tools/load_test.py

NFR-02 target: common actions under 2 seconds, weekly report under 5 seconds.
"""
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app          # noqa: E402
from db import get_db, init_db      # noqa: E402

PRODUCTS, SALES = 2000, 50000


def build(db):
    random.seed(1)
    rows = [(f"Product {i:04d}", random.choice(["Stationery", "Household", "Snacks", "Drinks"]),
             round(random.uniform(5, 200), 2), round(random.uniform(2, 150), 2),
             random.randint(0, 500), random.randint(5, 30)) for i in range(1, PRODUCTS + 1)]
    db.execute("BEGIN")
    db.executemany("INSERT INTO Product (product_name, category, unit_price, cost_price, "
                   "qty_in_stock, reorder_level) VALUES (?, ?, ?, ?, ?, ?)", rows)
    start = datetime.now() - timedelta(days=365)
    sales, lines = [], []
    for s in range(1, SALES + 1):
        when = (start + timedelta(minutes=s * 10)).strftime("%Y-%m-%d %H:%M:%S")
        pid, qty = random.randint(1, PRODUCTS), random.randint(1, 3)
        total = round(rows[pid - 1][2] * qty, 2)
        sales.append((f"RCP-LOAD-{s:06d}", when, 1, "CARD", total, total, 0))
        lines.append((s, pid, qty, rows[pid - 1][2], total))
    db.executemany("INSERT INTO Sale (receipt_no, sale_datetime, user_id, payment_type, "
                   "total_amount, amount_tendered, change_due) VALUES (?, ?, ?, ?, ?, ?, ?)", sales)
    db.executemany("INSERT INTO SaleLine (sale_id, product_id, quantity, unit_price, line_total) "
                   "VALUES (?, ?, ?, ?, ?)", lines)
    db.execute("COMMIT")


def main():
    folder = tempfile.mkdtemp()
    app = create_app({"DATABASE": os.path.join(folder, "load.db"), "SECRET_KEY": "load",
                      "BACKUP_FOLDER": os.path.join(folder, "backups")})
    with app.app_context():
        init_db()
        print(f"Building test data: {PRODUCTS} products, {SALES} sales ...")
        build(get_db())

    client = app.test_client()
    client.post("/login", data={"username": "manager", "password": "Manager@123"})
    today = datetime.now().date()
    week_ago = (today - timedelta(days=6)).isoformat()

    checks = [
        ("Dashboard (low-stock alerts)", "/", 2),
        ("Product search", "/products?q=Product 15", 2),
        ("Product list (all 2,000)", "/products", 2),
        ("Sales history", "/sales", 2),
        ("Weekly sales report", f"/reports/sales?from={week_ago}&to={today}", 5),
        ("Full-year sales report", f"/reports/sales?from={today.replace(year=today.year - 1)}&to={today}", 5),
        ("Inventory report", "/reports/inventory", 5),
    ]
    print(f"\n{'Screen':32} {'Time (s)':>9} {'Target':>7}  Result")
    all_ok = True
    for name, url, target in checks:
        t = time.perf_counter()
        r = client.get(url)
        seconds = time.perf_counter() - t
        ok = r.status_code == 200 and seconds < target
        all_ok &= ok
        print(f"{name:32} {seconds:9.3f} {target:>6}s  {'PASS' if ok else 'FAIL'}")

    t = time.perf_counter()
    r = client.post("/sales/complete", json={"cart_lines": [{"product_id": 7, "quantity": 1}],
                                             "payment_type": "CARD"})
    seconds = time.perf_counter() - t
    ok = r.get_json()["ok"] and seconds < 2
    all_ok &= ok
    print(f"{'Record a sale':32} {seconds:9.3f} {2:>6}s  {'PASS' if ok else 'FAIL'}")
    print("\nAll targets met." if all_ok else "\nSome targets were missed.")


if __name__ == "__main__":
    main()
