"""Products, suppliers and search - FR-05, FR-06, FR-07, FR-17, NFR-08."""


def test_tc14_new_product_starts_with_zero_stock(as_manager, db):
    """TC-14 (FR-05): products are created by the manager; stock only via GRN/adjustment."""
    r = as_manager.post("/products/new", data={"product_name": "Stapler", "category": "Stationery",
                                               "unit_price": "45", "cost_price": "30",
                                               "reorder_level": "3", "supplier_id": ""})
    assert r.status_code == 302
    row = db.execute("SELECT * FROM Product WHERE product_name = 'Stapler'").fetchone()
    assert row["qty_in_stock"] == 0 and row["supplier_id"] is None


def test_tc15_invalid_product_data_is_rejected(as_manager, db):
    """TC-15 (FR-05): empty name or negative price is refused with a clear message."""
    r = as_manager.post("/products/new", data={"product_name": "", "unit_price": "10"})
    assert b"Product name is required" in r.data
    r = as_manager.post("/products/new", data={"product_name": "Glue", "unit_price": "-5"})
    assert b"cannot be less than 0" in r.data
    assert db.execute("SELECT 1 FROM Product WHERE product_name = 'Glue'").fetchone() is None


def test_tc16_search_and_low_stock_filter(as_manager):
    """TC-16 (FR-17): search by name/category and show only low-stock items."""
    page = as_manager.get("/products?q=pen").data
    assert b"Blue Pen" in page and b"A4 Notebook" not in page
    page = as_manager.get("/products?category=Kitchenware").data
    assert b"Dish Cloth" in page and b"Blue Pen" not in page
    page = as_manager.get("/products?low=1").data     # notebook 8<=15, cloth 5<=10, pen 30>10
    assert b"A4 Notebook" in page and b"Dish Cloth" in page and b"Blue Pen" not in page


def test_tc17_deactivate_product_keeps_sales_history(app, as_manager, db):
    """TC-17 (NFR-08): a deactivated product with past sales stays in the history."""
    ids = app.ids
    r = as_manager.post("/sales/complete", json={
        "cart_lines": [{"product_id": ids["notebook"], "quantity": 1}],
        "payment_type": "CARD"})
    sale_id = r.get_json()["sale_id"]
    as_manager.post(f"/products/{ids['notebook']}/toggle")

    assert b"A4 Notebook" in as_manager.get(f"/sales/{sale_id}").data      # history intact
    assert b"A4 Notebook" not in as_manager.get("/products").data          # hidden from list
    r = as_manager.post("/sales/validate-line", json={"product_id": ids["notebook"],
                                                      "quantity": 1, "cart_lines": []})
    assert r.status_code == 400 and "no longer available" in r.get_json()["message"]


def test_tc18_supplier_create_and_validation(as_manager, db):
    """TC-18 (FR-06): suppliers need a name and a valid email."""
    r = as_manager.post("/suppliers/new", data={"supplier_name": "Mopani Wholesalers",
                                                "email": "not-an-email"})
    assert b"valid email" in r.data
    as_manager.post("/suppliers/new", data={"supplier_name": "Mopani Wholesalers",
                                            "email": "orders@mopani.co.za"})
    assert db.execute("SELECT 1 FROM Supplier WHERE supplier_name = 'Mopani Wholesalers'").fetchone()
