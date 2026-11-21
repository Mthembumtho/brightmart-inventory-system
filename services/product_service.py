"""
ProductService - product and supplier records (FR-05, FR-06, FR-07, FR-17).

Note: this service NEVER changes qty_in_stock. Only SalesService and
StockService may do that, so every stock change is logged (Part 1, 5.1).
A new product therefore starts at 0 and gets stock through a GRN or an
adjustment.
"""
from services import ServiceError


def _to_number(value, label, kind=float, minimum=0):
    """Turn form text into a number, with a friendly error message."""
    try:
        number = kind(str(value).strip())
    except (TypeError, ValueError):
        raise ServiceError(f"{label} must be a number")
    if number < minimum:
        raise ServiceError(f"{label} cannot be less than {minimum}")
    return number


PRODUCT_SELECT = """
    SELECT p.*, s.supplier_name
    FROM Product p
    LEFT JOIN Supplier s ON s.supplier_id = p.supplier_id
"""


class ProductService:

    # ------------------------------------------------------------------ products
    @staticmethod
    def search_products(db, text="", category="", low_only=False, include_inactive=False):
        """FR-17: search by name or category, filter to low-stock only."""
        sql = PRODUCT_SELECT + " WHERE 1 = 1"
        params = []
        if not include_inactive:
            sql += " AND p.is_active = 1"
        if text:
            sql += " AND (p.product_name LIKE ? OR p.category LIKE ? OR p.description LIKE ?)"
            like = f"%{text.strip()}%"
            params += [like, like, like]
        if category:
            sql += " AND p.category = ?"
            params.append(category)
        if low_only:
            sql += " AND p.qty_in_stock <= p.reorder_level"
        sql += " ORDER BY p.is_active DESC, p.product_name"
        return db.execute(sql, params).fetchall()

    @staticmethod
    def get_product(db, product_id):
        return db.execute(PRODUCT_SELECT + " WHERE p.product_id = ?", (product_id,)).fetchone()

    @staticmethod
    def categories(db):
        rows = db.execute(
            "SELECT DISTINCT category FROM Product WHERE category IS NOT NULL AND category <> '' "
            "ORDER BY category"
        ).fetchall()
        return [r["category"] for r in rows]

    @staticmethod
    def _clean_product(db, form):
        name = (form.get("product_name") or "").strip()
        if not name:
            raise ServiceError("Product name is required")
        supplier_id = form.get("supplier_id") or None
        if supplier_id:
            supplier = db.execute(
                "SELECT 1 FROM Supplier WHERE supplier_id = ? AND is_active = 1", (supplier_id,)
            ).fetchone()
            if not supplier:
                raise ServiceError("Chosen supplier is not active")
        return {
            "product_name": name,
            "description": (form.get("description") or "").strip(),
            "category": (form.get("category") or "").strip(),
            "unit_price": round(_to_number(form.get("unit_price"), "Unit price"), 2),
            "cost_price": round(_to_number(form.get("cost_price") or 0, "Cost price"), 2),
            "reorder_level": _to_number(form.get("reorder_level") or 0, "Reorder level", int),
            "supplier_id": supplier_id,
        }

    @staticmethod
    def create_product(db, form):
        d = ProductService._clean_product(db, form)
        cur = db.execute(
            "INSERT INTO Product (product_name, description, category, unit_price, cost_price, "
            "reorder_level, supplier_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (d["product_name"], d["description"], d["category"], d["unit_price"],
             d["cost_price"], d["reorder_level"], d["supplier_id"]),
        )
        return cur.lastrowid

    @staticmethod
    def update_product(db, product_id, form):
        d = ProductService._clean_product(db, form)
        db.execute(
            "UPDATE Product SET product_name = ?, description = ?, category = ?, unit_price = ?, "
            "cost_price = ?, reorder_level = ?, supplier_id = ? WHERE product_id = ?",
            (d["product_name"], d["description"], d["category"], d["unit_price"],
             d["cost_price"], d["reorder_level"], d["supplier_id"], product_id),
        )

    @staticmethod
    def set_product_active(db, product_id, active):
        """Products are deactivated, never deleted, so past sales stay valid (NFR-08)."""
        db.execute("UPDATE Product SET is_active = ? WHERE product_id = ?",
                   (1 if active else 0, product_id))

    # ----------------------------------------------------------------- suppliers
    @staticmethod
    def list_suppliers(db, include_inactive=True):
        sql = "SELECT * FROM Supplier"
        if not include_inactive:
            sql += " WHERE is_active = 1"
        return db.execute(sql + " ORDER BY is_active DESC, supplier_name").fetchall()

    @staticmethod
    def get_supplier(db, supplier_id):
        return db.execute("SELECT * FROM Supplier WHERE supplier_id = ?", (supplier_id,)).fetchone()

    @staticmethod
    def _clean_supplier(form):
        name = (form.get("supplier_name") or "").strip()
        if not name:
            raise ServiceError("Supplier name is required")
        email = (form.get("email") or "").strip()
        if email and "@" not in email:
            raise ServiceError("Please enter a valid email address")
        return (name, (form.get("contact_person") or "").strip(), (form.get("phone") or "").strip(),
                email, (form.get("address") or "").strip())

    @staticmethod
    def create_supplier(db, form):
        cur = db.execute(
            "INSERT INTO Supplier (supplier_name, contact_person, phone, email, address) "
            "VALUES (?, ?, ?, ?, ?)", ProductService._clean_supplier(form))
        return cur.lastrowid

    @staticmethod
    def update_supplier(db, supplier_id, form):
        db.execute(
            "UPDATE Supplier SET supplier_name = ?, contact_person = ?, phone = ?, email = ?, "
            "address = ? WHERE supplier_id = ?",
            (*ProductService._clean_supplier(form), supplier_id))

    @staticmethod
    def set_supplier_active(db, supplier_id, active):
        db.execute("UPDATE Supplier SET is_active = ? WHERE supplier_id = ?",
                   (1 if active else 0, supplier_id))
