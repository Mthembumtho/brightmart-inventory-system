"""Reports, CSV export and backup - FR-18, FR-19, FR-20, NFR-03."""
import os
import sqlite3
from datetime import date


def sell(client, app, product, qty, payment="CARD", tendered=None):
    return client.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids[product], "quantity": qty}],
        "payment_type": payment, "amount_tendered": tendered}).get_json()


def test_tc38_sales_report_totals(app, as_manager, as_owner):
    """TC-38 (FR-18): totals, transaction count and best seller for a date range."""
    sell(as_manager, app, "pen", 3)                       # R105
    sell(as_manager, app, "notebook", 2, "CASH", 50)      # R25
    today = date.today().isoformat()
    page = as_owner.get(f"/reports/sales?from={today}&to={today}").data.decode()
    assert "R 130.00" in page                              # total sales
    assert ">2</div>" in page                              # transactions
    assert page.index("Blue Pen") < page.index("A4 Notebook")   # best seller first


def test_tc39_sales_report_rejects_backwards_dates(as_owner):
    """TC-39 (FR-18): start date after end date gives a clear message."""
    page = as_owner.get("/reports/sales?from=2026-11-20&to=2026-11-01").data
    assert b"Start date must be before the end date" in page


def test_tc40_inventory_report_stock_value(as_owner):
    """TC-40 (FR-19): stock value = quantity x cost price (8x8 + 30x22 + 5x6 = 754)."""
    page = as_owner.get("/reports/inventory").data.decode()
    assert "R 754.00" in page


def test_tc41_csv_export(app, as_manager):
    """TC-41 (FR-20): both reports download as CSV files."""
    sell(as_manager, app, "pen", 1)
    r = as_manager.get("/reports/inventory?export=csv")
    assert r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
    text = r.data.decode("utf-8-sig")
    assert text.startswith("Product,Category,Qty in stock") and "A4 Notebook 80pg" in text
    today = date.today().isoformat()
    r = as_manager.get(f"/reports/sales?from={today}&to={today}&export=csv")
    assert r.mimetype == "text/csv" and "Blue Pen (box),Stationery,1,35.00" in r.data.decode("utf-8-sig")


def test_tc42_backup_creates_a_restorable_copy(app, as_manager):
    """TC-42 (NFR-03): one click creates a complete, readable copy of the database."""
    sell(as_manager, app, "pen", 1)
    as_manager.post("/backup")
    folder = app.config["BACKUP_FOLDER"]
    files = os.listdir(folder)
    assert len(files) == 1
    copy = sqlite3.connect(os.path.join(folder, files[0]))
    assert copy.execute("SELECT COUNT(*) FROM Sale").fetchone()[0] == 1
    assert copy.execute("SELECT qty_in_stock FROM Product WHERE product_name = 'Blue Pen (box)'"
                        ).fetchone()[0] == 29
    copy.close()
    r = as_manager.get(f"/backup/download/{files[0]}")
    assert r.status_code == 200 and len(r.data) > 0


def test_tc43_backup_download_cannot_escape_folder(as_manager):
    """TC-43 (security): only files inside the backups folder can be downloaded."""
    assert as_manager.get("/backup/download/../app.py").status_code == 404
