"""
seed_demo.py - fills the database with realistic sample data, matching the
Part 1 mock-ups (PaperCo, A4 Notebook with 8 in stock, etc.).

All stock goes in through the real services (GRN, sales, adjustments), so the
movement log is complete and consistent - just like real use.
Only the dates of the demo sales are moved back afterwards, so the reports
have a week of history to show.
"""
import random
from datetime import date, datetime, timedelta

from services.auth_service import AuthService
from services.product_service import ProductService
from services.sales_service import SalesService
from services.stock_service import StockService

SUPPLIERS = [
    {"supplier_name": "PaperCo", "contact_person": "Thandi Mokoena", "phone": "015 307 1100",
     "email": "orders@paperco.co.za", "address": "12 Danie Joubert St, Tzaneen"},
    {"supplier_name": "HomeSupplies", "contact_person": "Pieter van Wyk", "phone": "015 307 2200",
     "email": "sales@homesupplies.co.za", "address": "4 Agatha St, Tzaneen"},
    {"supplier_name": "Limpopo Snacks & Drinks", "contact_person": "Rudzani Netshivhambe",
     "phone": "015 291 3300", "email": "info@limpoposnacks.co.za", "address": "Polokwane"},
]

# name, category, unit price, cost price, reorder level, supplier index, qty received, qty to sell
PRODUCTS = [
    ("A4 Notebook 80pg", "Stationery", 12.50, 8.00, 15, 0, 40, 32),
    ("Blue Pen (box)", "Stationery", 35.00, 22.00, 10, 0, 20, 17),
    ("HB Pencil (12)", "Stationery", 24.00, 15.00, 10, 0, 30, 9),
    ("Exam Pad A4", "Stationery", 18.00, 11.50, 12, 0, 36, 14),
    ("Dish Cloth", "Kitchenware", 10.00, 6.00, 10, 1, 25, 18),
    ("Sunlight Dishwashing Liquid 750ml", "Household", 32.00, 24.00, 8, 1, 24, 10),
    ("Handy Andy 500ml", "Household", 29.50, 21.00, 8, 1, 20, 6),
    ("Plastic Bucket 10L", "Household", 45.00, 30.00, 5, 1, 12, 4),
    ("Simba Chips 120g", "Snacks", 19.99, 13.50, 20, 2, 60, 35),
    ("Coca-Cola 2L", "Drinks", 27.99, 19.00, 12, 2, 48, 30),
    ("Bottled Water 500ml", "Drinks", 9.50, 5.00, 24, 2, 96, 41),
]


def seed(db):
    random.seed(2026)
    manager_id = db.execute("SELECT user_id FROM User WHERE username = 'manager'").fetchone()[0]

    AuthService.create_user(db, "owner", "Owner@1234", "OWNER")
    AuthService.create_user(db, "lindelwe", "Sales@1234", "SALES")
    AuthService.create_user(db, "musa", "Sales@1234", "SALES")
    sales_ids = [r[0] for r in db.execute("SELECT user_id FROM User WHERE role IN ('SALES','MANAGER')")]

    supplier_ids = [ProductService.create_supplier(db, s) for s in SUPPLIERS]

    product_ids = []
    for name, cat, price, cost, reorder, sup, _, _ in PRODUCTS:
        product_ids.append(ProductService.create_product(db, {
            "product_name": name, "category": cat, "unit_price": price, "cost_price": cost,
            "reorder_level": reorder, "supplier_id": supplier_ids[sup], "description": ""}))

    # Opening stock: one GRN per supplier, dated 8 days ago
    received = (date.today() - timedelta(days=8)).isoformat()
    for s_index, supplier_id in enumerate(supplier_ids):
        lines = [{"product_id": product_ids[i], "qty_received": p[6], "unit_cost": p[3]}
                 for i, p in enumerate(PRODUCTS) if p[5] == s_index]
        StockService.receive_grn(db, manager_id, supplier_id, None,
                                 f"DN-{date.today().year}-{100 + s_index}", received, lines)

    # Sales over the last 7 days, until each product reaches its target
    remaining = {product_ids[i]: p[7] for i, p in enumerate(PRODUCTS)}
    while any(remaining.values()):
        cart = []
        for pid in random.sample(list(remaining), k=random.randint(1, 3)):
            if remaining[pid]:
                qty = min(remaining[pid], random.randint(1, 4))
                cart.append({"product_id": pid, "quantity": qty})
                remaining[pid] -= qty
        if not cart:
            continue
        price_total = sum(db.execute("SELECT unit_price FROM Product WHERE product_id = ?",
                                     (l["product_id"],)).fetchone()[0] * l["quantity"] for l in cart)
        if random.random() < 0.6:
            sale_id, *_ = SalesService.record_sale(db, random.choice(sales_ids), cart, "CASH",
                                                   float(int(price_total / 50) * 50 + 50))
        else:
            sale_id, *_ = SalesService.record_sale(db, random.choice(sales_ids), cart, "CARD", None)
        # demo only: spread the sales over the past week (8:00 - 17:59)
        when = datetime.now() - timedelta(days=random.randint(0, 6))
        when = when.replace(hour=random.randint(8, 17), minute=random.randint(0, 59))
        if when > datetime.now():
            when = datetime.now()
        stamp = when.strftime("%Y-%m-%d %H:%M:%S")
        db.execute("UPDATE Sale SET sale_datetime = ? WHERE sale_id = ?", (stamp, sale_id))
        db.execute("UPDATE StockMovement SET movement_datetime = ? WHERE sale_id = ?", (stamp, sale_id))

    # Receipt numbers follow the (now shuffled) dates, so renumber them in date order
    for n, row in enumerate(db.execute("SELECT sale_id FROM Sale ORDER BY sale_datetime").fetchall(), 1):
        db.execute("UPDATE Sale SET receipt_no = ? WHERE sale_id = ?",
                   (f"TMP-{n}", row[0]))
    for n, row in enumerate(db.execute("SELECT sale_id FROM Sale ORDER BY sale_datetime").fetchall(), 1):
        db.execute("UPDATE Sale SET receipt_no = ? WHERE sale_id = ?",
                   (f"RCP-{date.today().year}-{n:06d}", row[0]))

    # One adjustment: 2 dish cloths damaged
    StockService.adjust_stock(db, manager_id, product_ids[4], "DECREASE", 2,
                              "Damaged - water leak in storeroom")

    # One open purchase order to PaperCo for the low stationery
    StockService.create_po(db, manager_id, supplier_ids[0], [
        {"product_id": product_ids[0], "qty_ordered": 50},
        {"product_id": product_ids[1], "qty_ordered": 20}])
