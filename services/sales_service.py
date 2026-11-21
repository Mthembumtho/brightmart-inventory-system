"""
SalesService - recording sales (FR-13, FR-14, FR-15, FR-16).
Pseudocode: Part 1, Section 5.3.
"""
import sqlite3
from datetime import datetime

from db import now
from models import Sale
from services import ServiceError
from services.stock_service import StockService


class SalesService:

    # ------------------------------------------------------------------
    # 5.3.1 Adding a line (live validation while the cashier works)
    # ------------------------------------------------------------------
    @staticmethod
    def add_line_to_cart(db, product_id, requested_qty, cart_lines):
        """Check one new line against stock, counting what is ALREADY in the cart.

        cart_lines = [{"product_id": 1, "quantity": 5}, ...]
        Returns the new line (with price and line total) or raises ServiceError.
        """
        product = db.execute("SELECT * FROM Product WHERE product_id = ?", (product_id,)).fetchone()
        if product is None or not product["is_active"]:
            raise ServiceError("Product is no longer available")

        if requested_qty <= 0:
            raise ServiceError("Quantity must be greater than zero")

        # Without this, a cashier could add 5, then another 5, when only 8 exist.
        already_in_cart = sum(l["quantity"] for l in cart_lines
                              if int(l["product_id"]) == int(product_id))

        if requested_qty + already_in_cart > product["qty_in_stock"]:
            available = product["qty_in_stock"] - already_in_cart
            raise ServiceError(f"Only {product['qty_in_stock']} in stock"
                               + (f" ({available} more can be added)" if already_in_cart else "")
                               + " - reduce quantity")

        return {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "quantity": requested_qty,
            "unit_price": product["unit_price"],
            "line_total": round(requested_qty * product["unit_price"], 2),
        }

    @staticmethod
    def calculate_total(lines):
        return round(sum(l["line_total"] for l in lines), 2)

    # ------------------------------------------------------------------
    # 5.3.2 Completing the sale (database transaction)
    # ------------------------------------------------------------------
    @staticmethod
    def record_sale(db, user_id, cart_lines, payment_type, amount_tendered):
        """Save a sale, deduct stock and log movements - all or nothing (NFR-08).

        cart_lines only needs product_id and quantity. Prices are read again
        from the database, so a changed price in the browser cannot be used
        to sell goods cheaper.
        Returns (sale_id, receipt_no, total, change_due).
        """
        if not cart_lines:
            raise ServiceError("Add at least one item")
        if payment_type not in ("CASH", "CARD"):
            raise ServiceError("Choose Cash or Card")
        for line in cart_lines:
            if int(line["quantity"]) <= 0:
                raise ServiceError("Quantity must be greater than zero")

        try:
            # BEGIN IMMEDIATE locks the database for writing straight away.
            # If a second till tries to save at the same moment it has to wait,
            # so the stock re-check below cannot be "overtaken" by another sale.
            db.execute("BEGIN IMMEDIATE")

            # Work out prices and the total from the database (not the browser)
            priced_lines = []
            for line in cart_lines:
                product = db.execute("SELECT * FROM Product WHERE product_id = ?",
                                     (line["product_id"],)).fetchone()
                if product is None or not product["is_active"]:
                    raise ServiceError("A product in the cart is no longer available")
                qty = int(line["quantity"])
                priced_lines.append({
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "quantity": qty,
                    "unit_price": product["unit_price"],
                    "line_total": round(qty * product["unit_price"], 2),
                })
            total = SalesService.calculate_total(priced_lines)

            if payment_type == "CASH":
                if amount_tendered is None or amount_tendered < total:
                    raise ServiceError("Tendered amount is less than the total")
                change_due = Sale.calculate_change(total, amount_tendered)
            else:
                amount_tendered, change_due = total, 0.0

            receipt_no = SalesService._next_receipt_number(db)
            sale_id = db.execute(
                "INSERT INTO Sale (receipt_no, sale_datetime, user_id, payment_type, total_amount, "
                "amount_tendered, change_due) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (receipt_no, now(), user_id, payment_type, total, round(amount_tendered, 2),
                 change_due),
            ).lastrowid

            for line in priced_lines:
                # Re-check stock just before deduction (two-step check, FR-15)
                current = db.execute("SELECT qty_in_stock FROM Product WHERE product_id = ?",
                                     (line["product_id"],)).fetchone()
                if current["qty_in_stock"] < line["quantity"]:
                    raise ServiceError(f"Stock for {line['product_name']} has changed "
                                       f"(only {current['qty_in_stock']} left) - sale not saved")

                db.execute(
                    "INSERT INTO SaleLine (sale_id, product_id, quantity, unit_price, line_total) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sale_id, line["product_id"], line["quantity"], line["unit_price"],
                     line["line_total"]))

                # FR-14: deduct stock
                db.execute("UPDATE Product SET qty_in_stock = qty_in_stock - ? WHERE product_id = ?",
                           (line["quantity"], line["product_id"]))

                # FR-12: log the movement
                StockService.write_movement(db, line["product_id"], user_id, "SALE",
                                            -line["quantity"], sale_id=sale_id)

            db.execute("COMMIT")
            return sale_id, receipt_no, total, change_due

        except ServiceError:
            db.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            # e.g. the CHECK (qty_in_stock >= 0) constraint fired - the final safety net
            db.execute("ROLLBACK")
            raise ServiceError("Sale could not be saved - no changes were made")

    @staticmethod
    def _next_receipt_number(db):
        """Receipt numbers look like RCP-2026-000145 (Part 1, Figure 4.6.4).
        Called inside the transaction, so two tills can never get the same number."""
        year = datetime.now().year
        count = db.execute("SELECT COUNT(*) FROM Sale WHERE receipt_no LIKE ?",
                           (f"RCP-{year}-%",)).fetchone()[0]
        return f"RCP-{year}-{count + 1:06d}"

    # ------------------------------------------------------------------
    # FR-16 Transaction history
    # ------------------------------------------------------------------
    @staticmethod
    def list_sales(db, user_id=None, date_from=None, date_to=None, limit=500):
        """user_id is set for Sales Staff, who may only see their own sales."""
        sql = """SELECT s.*, u.username,
                        (SELECT SUM(quantity) FROM SaleLine WHERE sale_id = s.sale_id) AS items
                 FROM Sale s JOIN User u ON u.user_id = s.user_id WHERE 1 = 1"""
        params = []
        if user_id:
            sql += " AND s.user_id = ?"
            params.append(user_id)
        if date_from:
            sql += " AND s.sale_datetime >= ?"
            params.append(date_from + " 00:00:00")
        if date_to:
            sql += " AND s.sale_datetime <= ?"
            params.append(date_to + " 23:59:59")
        sql += " ORDER BY s.sale_id DESC LIMIT ?"
        params.append(limit)
        return db.execute(sql, params).fetchall()

    @staticmethod
    def get_sale(db, sale_id):
        sale = db.execute("""SELECT s.*, u.username FROM Sale s
                             JOIN User u ON u.user_id = s.user_id
                             WHERE s.sale_id = ?""", (sale_id,)).fetchone()
        lines = db.execute("""SELECT l.*, p.product_name FROM SaleLine l
                              JOIN Product p ON p.product_id = l.product_id
                              WHERE l.sale_id = ? ORDER BY l.sale_line_id""", (sale_id,)).fetchall()
        return sale, lines
