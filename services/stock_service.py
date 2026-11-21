"""
StockService - stock coming IN and the audit trail.
GRN (FR-08), adjustments (FR-09), purchase orders (FR-10), low stock (FR-11),
movement log (FR-12). Pseudocode: Part 1, Sections 5.4 - 5.7.
"""
import sqlite3
from datetime import date

from db import now
from models import StockMovement
from services import ServiceError


class StockService:

    # ------------------------------------------------------------------
    # 5.4 The shared movement helper
    # ------------------------------------------------------------------
    @staticmethod
    def write_movement(db, product_id, user_id, movement_type, qty_change,
                       reason=None, sale_id=None, grn_id=None):
        """Write one line to the stock movement log.

        It is ALWAYS called inside the caller's transaction. It does not catch
        its own errors: if it raises, the caller's `except` block runs the
        ROLLBACK, so the whole sale / GRN / adjustment is cancelled.
        """
        # 1. Validate the movement type
        if movement_type not in StockMovement.TYPES:
            raise ServiceError("Unknown movement type")
        # 2. Validate the quantity
        if qty_change == 0:
            raise ServiceError("Quantity change cannot be zero")
        # 3. Enforce the mandatory reason for adjustments (FR-09)
        if StockMovement.is_adjustment(movement_type) and (not reason or not reason.strip()):
            raise ServiceError("A reason is required for a stock adjustment")
        # 4. Log the movement
        db.execute(
            "INSERT INTO StockMovement (product_id, user_id, movement_type, qty_change, reason, "
            "sale_id, grn_id, movement_datetime) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, user_id, movement_type, qty_change, reason, sale_id, grn_id, now()),
        )

    # ------------------------------------------------------------------
    # 5.5 Receive goods (GRN)
    # ------------------------------------------------------------------
    @staticmethod
    def receive_grn(db, user_id, supplier_id, po_id, delivery_note_no, received_date, grn_lines):
        """grn_lines = [{"product_id": 3, "qty_received": 100, "unit_cost": 8.0}, ...]
        Returns the new grn_number."""
        # 1. Basic validation (nothing is written yet)
        if not grn_lines:
            raise ServiceError("Add at least one product")
        if not delivery_note_no or not delivery_note_no.strip():
            raise ServiceError("Delivery note number is required")
        if not received_date:
            raise ServiceError("Date received is required")
        if received_date > date.today().isoformat():
            raise ServiceError("Date received cannot be in the future")
        supplier = db.execute("SELECT * FROM Supplier WHERE supplier_id = ? AND is_active = 1",
                              (supplier_id,)).fetchone()
        if supplier is None:
            raise ServiceError("Supplier not found or inactive")

        # 2. Purchase order checks (only if a PO was chosen)
        po_id = int(po_id) if po_id else None
        if po_id is not None:
            po = db.execute("SELECT * FROM PurchaseOrder WHERE po_id = ?", (po_id,)).fetchone()
            if po is None or po["supplier_id"] != int(supplier_id):
                raise ServiceError("Invalid purchase order for this supplier")
            if po["status"] == "CLOSED":
                raise ServiceError("This purchase order is already closed")

        # 3. Line validation (still before any database writes)
        for line in grn_lines:
            if line["qty_received"] <= 0:
                raise ServiceError("Quantity received must be greater than zero")
            if line["unit_cost"] < 0:
                raise ServiceError("Unit cost cannot be negative")
            product = db.execute("SELECT 1 FROM Product WHERE product_id = ? AND is_active = 1",
                                 (line["product_id"],)).fetchone()
            if product is None:
                raise ServiceError("Product not found or inactive")
            if po_id is not None:
                po_line = db.execute(
                    "SELECT * FROM PurchaseOrderLine WHERE po_id = ? AND product_id = ?",
                    (po_id, line["product_id"])).fetchone()
                if po_line is None or (po_line["qty_received"] + line["qty_received"]
                                       > po_line["qty_ordered"]):
                    raise ServiceError("Invalid quantity or product not on the purchase order")

        # 4. Transaction - all or nothing (NFR-08)
        try:
            db.execute("BEGIN IMMEDIATE")
            year = received_date[:4]
            count = db.execute("SELECT COUNT(*) FROM GRN WHERE grn_number LIKE ?",
                               (f"GRN-{year}-%",)).fetchone()[0]
            grn_number = f"GRN-{year}-{count + 1:04d}"
            grn_id = db.execute(
                "INSERT INTO GRN (grn_number, supplier_id, po_id, received_by, delivery_note_no, "
                "received_date) VALUES (?, ?, ?, ?, ?, ?)",
                (grn_number, supplier_id, po_id, user_id, delivery_note_no.strip(), received_date),
            ).lastrowid
            for line in grn_lines:
                db.execute(
                    "INSERT INTO GRNLine (grn_id, product_id, qty_received, unit_cost) "
                    "VALUES (?, ?, ?, ?)",
                    (grn_id, line["product_id"], line["qty_received"], line["unit_cost"]))
                db.execute("UPDATE Product SET qty_in_stock = qty_in_stock + ? WHERE product_id = ?",
                           (line["qty_received"], line["product_id"]))
                StockService.write_movement(db, line["product_id"], user_id, "GRN",
                                            line["qty_received"], grn_id=grn_id)
                if po_id is not None:
                    db.execute(
                        "UPDATE PurchaseOrderLine SET qty_received = qty_received + ? "
                        "WHERE po_id = ? AND product_id = ?",
                        (line["qty_received"], po_id, line["product_id"]))
            if po_id is not None:
                StockService.update_po_status(db, po_id)
            db.execute("COMMIT")
            return grn_number
        except ServiceError:
            db.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            db.execute("ROLLBACK")
            raise ServiceError("GRN could not be saved - no changes were made")

    @staticmethod
    def update_po_status(db, po_id):
        """Mark a PO CLOSED when everything has arrived, PARTIALLY_RECEIVED when some has."""
        lines = db.execute("SELECT * FROM PurchaseOrderLine WHERE po_id = ?", (po_id,)).fetchall()
        all_closed = all(l["qty_received"] >= l["qty_ordered"] for l in lines)
        any_received = any(l["qty_received"] > 0 for l in lines)
        if all_closed:
            db.execute("UPDATE PurchaseOrder SET status = 'CLOSED' WHERE po_id = ?", (po_id,))
        elif any_received:
            db.execute("UPDATE PurchaseOrder SET status = 'PARTIALLY_RECEIVED' WHERE po_id = ?",
                       (po_id,))

    # ------------------------------------------------------------------
    # 5.6 Stock adjustment
    # ------------------------------------------------------------------
    @staticmethod
    def adjust_stock(db, user_id, product_id, direction, quantity, reason):
        """direction is 'INCREASE' or 'DECREASE'. Reason is compulsory (FR-09)."""
        if direction not in ("INCREASE", "DECREASE"):
            raise ServiceError("Choose whether stock goes up or down")
        if quantity <= 0:
            raise ServiceError("Quantity must be greater than zero")
        if not reason or not reason.strip():
            raise ServiceError("A reason is required for a stock adjustment")
        qty_change = quantity if direction == "INCREASE" else -quantity
        try:
            db.execute("BEGIN IMMEDIATE")
            product = db.execute("SELECT * FROM Product WHERE product_id = ? AND is_active = 1",
                                 (product_id,)).fetchone()
            if product is None:
                raise ServiceError("Product not found or inactive")
            if product["qty_in_stock"] + qty_change < 0:
                raise ServiceError(
                    f"Only {product['qty_in_stock']} in stock - cannot remove {quantity}")
            db.execute("UPDATE Product SET qty_in_stock = qty_in_stock + ? WHERE product_id = ?",
                       (qty_change, product_id))
            StockService.write_movement(db, product_id, user_id, "ADJUSTMENT", qty_change,
                                        reason=reason.strip())
            db.execute("COMMIT")
        except ServiceError:
            db.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            db.execute("ROLLBACK")
            raise ServiceError("Adjustment could not be saved - no changes were made")

    # ------------------------------------------------------------------
    # 5.7 Low-stock query (FR-11)
    # ------------------------------------------------------------------
    @staticmethod
    def get_low_stock_products(db, limit=None):
        sql = """
            SELECT p.product_id, p.product_name, p.qty_in_stock, p.reorder_level,
                   (p.reorder_level - p.qty_in_stock) AS shortfall,
                   s.supplier_name, s.phone AS supplier_phone
            FROM Product p
            LEFT JOIN Supplier s ON s.supplier_id = p.supplier_id
            WHERE p.is_active = 1
              AND p.qty_in_stock <= p.reorder_level
            ORDER BY shortfall DESC
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        return db.execute(sql).fetchall()

    # ------------------------------------------------------------------
    # Purchase orders (FR-10)
    # ------------------------------------------------------------------
    @staticmethod
    def create_po(db, user_id, supplier_id, po_lines):
        """po_lines = [{"product_id": 1, "qty_ordered": 50}, ...]. Returns po_id."""
        if not po_lines:
            raise ServiceError("Add at least one product")
        supplier = db.execute("SELECT 1 FROM Supplier WHERE supplier_id = ? AND is_active = 1",
                              (supplier_id,)).fetchone()
        if supplier is None:
            raise ServiceError("Supplier not found or inactive")
        seen = set()
        for line in po_lines:
            if line["qty_ordered"] <= 0:
                raise ServiceError("Quantity ordered must be greater than zero")
            if line["product_id"] in seen:
                raise ServiceError("Each product can only appear once on a purchase order")
            seen.add(line["product_id"])
        try:
            db.execute("BEGIN IMMEDIATE")
            po_id = db.execute(
                "INSERT INTO PurchaseOrder (supplier_id, created_by, order_date) VALUES (?, ?, ?)",
                (supplier_id, user_id, date.today().isoformat())).lastrowid
            for line in po_lines:
                db.execute("INSERT INTO PurchaseOrderLine (po_id, product_id, qty_ordered) "
                           "VALUES (?, ?, ?)", (po_id, line["product_id"], line["qty_ordered"]))
            db.execute("COMMIT")
            return po_id
        except sqlite3.Error:
            db.execute("ROLLBACK")
            raise ServiceError("Purchase order could not be saved - no changes were made")

    @staticmethod
    def list_pos(db, open_only=False):
        sql = """SELECT po.*, s.supplier_name, u.username AS created_by_name
                 FROM PurchaseOrder po
                 JOIN Supplier s ON s.supplier_id = po.supplier_id
                 JOIN User u ON u.user_id = po.created_by"""
        if open_only:
            sql += " WHERE po.status <> 'CLOSED'"
        return db.execute(sql + " ORDER BY po.po_id DESC").fetchall()

    @staticmethod
    def get_po(db, po_id):
        po = db.execute("""SELECT po.*, s.supplier_name, u.username AS created_by_name
                           FROM PurchaseOrder po
                           JOIN Supplier s ON s.supplier_id = po.supplier_id
                           JOIN User u ON u.user_id = po.created_by
                           WHERE po.po_id = ?""", (po_id,)).fetchone()
        lines = db.execute("""SELECT l.*, p.product_name FROM PurchaseOrderLine l
                              JOIN Product p ON p.product_id = l.product_id
                              WHERE l.po_id = ? ORDER BY l.po_line_id""", (po_id,)).fetchall()
        return po, lines

    # ------------------------------------------------------------------
    # Read-only lists for screens
    # ------------------------------------------------------------------
    @staticmethod
    def list_grns(db):
        return db.execute("""SELECT g.*, s.supplier_name, u.username AS received_by_name,
                                    (SELECT SUM(qty_received * unit_cost) FROM GRNLine
                                     WHERE grn_id = g.grn_id) AS total_cost
                             FROM GRN g
                             JOIN Supplier s ON s.supplier_id = g.supplier_id
                             JOIN User u ON u.user_id = g.received_by
                             ORDER BY g.grn_id DESC""").fetchall()

    @staticmethod
    def get_grn(db, grn_id):
        grn = db.execute("""SELECT g.*, s.supplier_name, u.username AS received_by_name
                            FROM GRN g JOIN Supplier s ON s.supplier_id = g.supplier_id
                            JOIN User u ON u.user_id = g.received_by
                            WHERE g.grn_id = ?""", (grn_id,)).fetchone()
        lines = db.execute("""SELECT l.*, p.product_name FROM GRNLine l
                              JOIN Product p ON p.product_id = l.product_id
                              WHERE l.grn_id = ?""", (grn_id,)).fetchall()
        return grn, lines

    @staticmethod
    def list_movements(db, product_id=None, movement_type=None, limit=500):
        sql = """SELECT m.*, p.product_name, u.username, s.receipt_no, g.grn_number
                 FROM StockMovement m
                 JOIN Product p ON p.product_id = m.product_id
                 JOIN User u ON u.user_id = m.user_id
                 LEFT JOIN Sale s ON s.sale_id = m.sale_id
                 LEFT JOIN GRN g ON g.grn_id = m.grn_id
                 WHERE 1 = 1"""
        params = []
        if product_id:
            sql += " AND m.product_id = ?"
            params.append(product_id)
        if movement_type:
            sql += " AND m.movement_type = ?"
            params.append(movement_type)
        sql += " ORDER BY m.movement_id DESC LIMIT ?"
        params.append(limit)
        return db.execute(sql, params).fetchall()
