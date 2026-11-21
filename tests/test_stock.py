"""Stock in, adjustments, purchase orders and low stock - FR-08 to FR-12."""
import sqlite3
from datetime import date, timedelta

import pytest


def stock(db, product_id):
    return db.execute("SELECT qty_in_stock FROM Product WHERE product_id = ?",
                      (product_id,)).fetchone()[0]


def grn_form(app, lines, po_id="", delivery="DN-2026-118", day=None):
    return {"supplier_id": app.ids["paperco"], "po_id": po_id, "delivery_note_no": delivery,
            "received_date": day or date.today().isoformat(),
            "product_id": [l[0] for l in lines], "qty_received": [l[1] for l in lines],
            "unit_cost": [l[2] for l in lines]}


def test_tc29_grn_increases_stock_and_is_logged(app, as_manager, db):
    """TC-29 (FR-08, FR-12): saving a GRN adds stock and writes a GRN movement."""
    nb = app.ids["notebook"]
    r = as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 100, 8)]), follow_redirects=True)
    assert b"saved. Stock levels have been increased" in r.data
    assert stock(db, nb) == 108
    move = db.execute("SELECT * FROM StockMovement WHERE product_id = ? AND movement_type = 'GRN' "
                      "ORDER BY movement_id DESC LIMIT 1", (nb,)).fetchone()
    assert move["qty_change"] == 100 and move["grn_id"] is not None
    grn = db.execute("SELECT * FROM GRN WHERE grn_id = ?", (move["grn_id"],)).fetchone()
    assert grn["received_by"] == 1 and grn["grn_number"].startswith("GRN-")


def test_tc30_partial_receipt_against_purchase_order(app, as_manager, db):
    """TC-30 (FR-10): 50 of 100 -> PARTIALLY_RECEIVED; the other 50 -> CLOSED; more is refused."""
    nb = app.ids["notebook"]
    as_manager.post("/stock/po/new", data={"supplier_id": app.ids["paperco"],
                                           "product_id": [nb], "qty_ordered": [100]})
    po_id = db.execute("SELECT MAX(po_id) FROM PurchaseOrder").fetchone()[0]

    as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 50, 8)], po_id, "DN-1"))
    assert db.execute("SELECT status FROM PurchaseOrder WHERE po_id = ?", (po_id,)).fetchone()[0] \
        == "PARTIALLY_RECEIVED"

    as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 50, 8)], po_id, "DN-2"))
    assert db.execute("SELECT status FROM PurchaseOrder WHERE po_id = ?", (po_id,)).fetchone()[0] \
        == "CLOSED"
    assert stock(db, nb) == 108

    r = as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 1, 8)], po_id, "DN-3"))
    assert b"already closed" in r.data


def test_tc31_over_receiving_a_po_is_refused(app, as_manager, db):
    """TC-31 (FR-10): cannot receive more than was ordered."""
    nb = app.ids["notebook"]
    as_manager.post("/stock/po/new", data={"supplier_id": app.ids["paperco"],
                                           "product_id": [nb], "qty_ordered": [20]})
    po_id = db.execute("SELECT MAX(po_id) FROM PurchaseOrder").fetchone()[0]
    r = as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 25, 8)], po_id))
    assert b"Invalid quantity" in r.data
    assert stock(db, nb) == 8


def test_tc32_grn_validation(app, as_manager, db):
    """TC-32 (FR-08): future dates and zero quantities are refused; nothing is saved."""
    nb = app.ids["notebook"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    r = as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 10, 8)], day=tomorrow))
    assert b"cannot be in the future" in r.data
    r = as_manager.post("/stock/grn/new", data=grn_form(app, [(nb, 0, 8)]))
    assert b"greater than zero" in r.data
    assert stock(db, nb) == 8


def test_tc33_adjustment_needs_a_reason(app, as_manager, db):
    """TC-33 (FR-09): no reason -> refused by the service AND by the database."""
    r = as_manager.post("/stock/adjust", data={"product_id": app.ids["pen"], "direction": "DECREASE",
                                               "quantity": 2, "reason": "   "})
    assert b"reason is required" in r.data
    assert stock(db, app.ids["pen"]) == 30
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO StockMovement (product_id, user_id, movement_type, qty_change, "
                   "movement_datetime) VALUES (?, 1, 'ADJUSTMENT', -1, '2026-11-16 10:00:00')",
                   (app.ids["pen"],))


def test_tc34_adjustment_with_reason_is_saved_and_logged(app, as_manager, db):
    """TC-34 (FR-09, FR-12): damaged stock is written off and logged with the reason."""
    as_manager.post("/stock/adjust", data={"product_id": app.ids["pen"], "direction": "DECREASE",
                                           "quantity": 2, "reason": "Boxes crushed in delivery"})
    assert stock(db, app.ids["pen"]) == 28
    move = db.execute("SELECT * FROM StockMovement WHERE movement_type = 'ADJUSTMENT'").fetchone()
    assert move["qty_change"] == -2 and move["reason"] == "Boxes crushed in delivery"


def test_tc35_adjustment_cannot_make_stock_negative(app, as_manager, db):
    """TC-35 (NFR-08): removing 6 dish cloths when there are 5 is refused."""
    r = as_manager.post("/stock/adjust", data={"product_id": app.ids["cloth"], "direction": "DECREASE",
                                               "quantity": 6, "reason": "Count correction"})
    assert b"Only 5 in stock" in r.data
    assert stock(db, app.ids["cloth"]) == 5


def test_tc36_low_stock_list_sorted_by_shortfall(app, as_sales):
    """TC-36 (FR-11): notebook (15-8=7) is listed above dish cloth (10-5=5); pen is not low."""
    page = as_sales.get("/stock/low").data.decode()
    assert page.index("A4 Notebook") < page.index("Dish Cloth")
    assert "Blue Pen" not in page


def test_tc37_movement_log_records_every_change(app, as_manager, db):
    """TC-37 (FR-12): sum of all movements equals stock on hand for every product."""
    as_manager.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["pen"], "quantity": 4}], "payment_type": "CARD"})
    as_manager.post("/stock/adjust", data={"product_id": app.ids["cloth"], "direction": "INCREASE",
                                           "quantity": 3, "reason": "Found in storeroom"})
    rows = db.execute("""SELECT p.product_id, p.qty_in_stock,
                                COALESCE(SUM(m.qty_change), 0) AS logged
                         FROM Product p LEFT JOIN StockMovement m ON m.product_id = p.product_id
                         GROUP BY p.product_id""").fetchall()
    for r in rows:
        assert r["qty_in_stock"] == r["logged"]


def test_tc44_grn_form_keeps_typed_lines_after_error(app, as_manager, db):
    """TC-44 (bug fix): after a refused GRN, the lines the user typed are sent back to the form."""
    nb = app.ids["notebook"]
    as_manager.post("/stock/po/new", data={"supplier_id": app.ids["paperco"],
                                           "product_id": [nb], "qty_ordered": [20]})
    po_id = db.execute("SELECT MAX(po_id) FROM PurchaseOrder").fetchone()[0]
    r = as_manager.post(f"/stock/grn/new?po_id={po_id}", data=grn_form(app, [(nb, 50, 8)], po_id))
    page = r.data.decode()
    assert "Invalid quantity" in page
    assert '"qty_received": "50"' in page          # the typed 50 is kept, not replaced by 20
