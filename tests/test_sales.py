"""Recording sales - FR-12, FR-13, FR-14, FR-15, FR-16, NFR-08."""
import re
import sqlite3

import pytest


def stock(db, product_id):
    return db.execute("SELECT qty_in_stock FROM Product WHERE product_id = ?",
                      (product_id,)).fetchone()[0]


def test_tc19_complete_cash_sale_updates_everything(app, as_sales, db):
    """TC-19 (FR-13, FR-14, FR-12): sale saved, stock drops, movement logged, change correct."""
    ids = app.ids
    r = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": ids["notebook"], "quantity": 2},
                       {"product_id": ids["pen"], "quantity": 1}],
        "payment_type": "CASH", "amount_tendered": 100})
    body = r.get_json()
    assert body["ok"] and body["total"] == 60.00 and body["change_due"] == 40.00   # mock-up figures
    assert re.fullmatch(r"RCP-\d{4}-\d{6}", body["receipt_no"])
    assert stock(db, ids["notebook"]) == 6 and stock(db, ids["pen"]) == 29
    moves = db.execute("SELECT product_id, qty_change FROM StockMovement "
                       "WHERE movement_type = 'SALE' AND sale_id = ?", (body["sale_id"],)).fetchall()
    assert sorted((m[0], m[1]) for m in moves) == sorted([(ids["notebook"], -2), (ids["pen"], -1)])


def test_tc20_cannot_add_more_than_in_stock(app, as_sales):
    """TC-20 (FR-15): 10 notebooks when only 8 are in stock is blocked."""
    r = as_sales.post("/sales/validate-line", json={"product_id": app.ids["notebook"],
                                                    "quantity": 10, "cart_lines": []})
    assert r.status_code == 400 and "Only 8 in stock" in r.get_json()["message"]


def test_tc21_cart_quantity_is_counted(app, as_sales):
    """TC-21 (FR-15): 5 in the cart + another 5 = 10 > 8, so the second line is blocked."""
    nb = app.ids["notebook"]
    r = as_sales.post("/sales/validate-line", json={
        "product_id": nb, "quantity": 5, "cart_lines": [{"product_id": nb, "quantity": 5}]})
    assert r.status_code == 400
    r = as_sales.post("/sales/validate-line", json={
        "product_id": nb, "quantity": 3, "cart_lines": [{"product_id": nb, "quantity": 5}]})
    assert r.status_code == 200 and r.get_json()["ok"]


def test_tc22_stock_changed_on_another_till_rolls_back(app, as_sales, as_manager, db):
    """TC-22 (FR-15, NFR-08): if another till sold the stock first, the whole sale is cancelled."""
    ids = app.ids
    # Till 1 (manager) sells 6 of the 8 notebooks
    as_manager.post("/sales/complete", json={
        "cart_lines": [{"product_id": ids["notebook"], "quantity": 6}], "payment_type": "CARD"})
    sales_before = db.execute("SELECT COUNT(*) FROM Sale").fetchone()[0]
    # Till 2 had a cart with pens AND 5 notebooks, built before till 1 saved
    r = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": ids["pen"], "quantity": 2},
                       {"product_id": ids["notebook"], "quantity": 5}],
        "payment_type": "CARD"})
    assert r.status_code == 400 and "has changed" in r.get_json()["message"]
    assert db.execute("SELECT COUNT(*) FROM Sale").fetchone()[0] == sales_before   # no half sale
    assert stock(db, ids["pen"]) == 30          # the pen deduction was rolled back too
    assert stock(db, ids["notebook"]) == 2


def test_tc23_cash_tendered_less_than_total_is_rejected(app, as_sales, db):
    """TC-23 (FR-13): cash sale needs enough money tendered."""
    r = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["pen"], "quantity": 2}],
        "payment_type": "CASH", "amount_tendered": 50})
    assert r.status_code == 400 and "less than the total" in r.get_json()["message"]
    assert db.execute("SELECT COUNT(*) FROM Sale").fetchone()[0] == 0


def test_tc24_prices_come_from_database_not_browser(app, as_sales, db):
    """TC-24 (security): a price sent by the browser is ignored."""
    r = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["pen"], "quantity": 1, "unit_price": 0.01}],
        "payment_type": "CARD"})
    assert r.get_json()["total"] == 35.00


def test_tc25_card_sale_has_no_change(app, as_sales):
    """TC-25 (FR-13): card payment - tendered equals total, change is zero."""
    body = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["cloth"], "quantity": 3}],
        "payment_type": "CARD"}).get_json()
    assert body["ok"] and body["total"] == 30.00 and body["change_due"] == 0


def test_tc26_sales_staff_see_only_their_own_sales(app, as_sales, as_manager):
    """TC-26 (FR-16): history is filtered by role."""
    mine = as_sales.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["pen"], "quantity": 1}], "payment_type": "CARD"}).get_json()
    theirs = as_manager.post("/sales/complete", json={
        "cart_lines": [{"product_id": app.ids["pen"], "quantity": 1}], "payment_type": "CARD"}).get_json()
    page = as_sales.get("/sales").data.decode()
    assert mine["receipt_no"] in page and theirs["receipt_no"] not in page
    assert as_sales.get(f"/sales/{theirs['sale_id']}").status_code == 403
    page = as_manager.get("/sales").data.decode()
    assert mine["receipt_no"] in page and theirs["receipt_no"] in page


def test_tc27_database_refuses_negative_stock(app, db):
    """TC-27 (NFR-08): the CHECK constraint is the final safety net."""
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE Product SET qty_in_stock = -1 WHERE product_id = ?", (app.ids["pen"],))


def test_tc28_empty_cart_is_rejected(as_sales):
    """TC-28 (FR-13): a sale needs at least one item."""
    r = as_sales.post("/sales/complete", json={"cart_lines": [], "payment_type": "CARD"})
    assert r.status_code == 400 and "at least one item" in r.get_json()["message"]
