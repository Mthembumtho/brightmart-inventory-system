"""
models.py - the Model classes from the class diagram (Part 1, Figure 4.5).

Model classes HOLD data and contain small helper methods. They do not talk
to the database - that is the job of the Service classes in /services.
"""
from dataclasses import dataclass
from typing import Optional

ROLE_LABELS = {"OWNER": "Business Owner", "MANAGER": "Store Manager", "SALES": "Sales Staff"}

# ---------------------------------------------------------------------------
# Permissions table - copied from Part 1, Section 3.4.
# Each action lists the roles that are allowed to do it (FR-02).
# ---------------------------------------------------------------------------
PERMISSIONS = {
    "view_dashboard":     {"OWNER", "MANAGER", "SALES"},
    "view_products":      {"OWNER", "MANAGER", "SALES"},
    "manage_products":    {"MANAGER"},
    "manage_suppliers":   {"MANAGER"},
    "view_suppliers":     {"OWNER", "MANAGER"},          # POPIA: not Sales Staff (NFR-05)
    "record_grn":         {"MANAGER"},
    "adjust_stock":       {"MANAGER"},
    "raise_po":           {"MANAGER"},
    "view_po":            {"OWNER", "MANAGER"},
    "record_sale":        {"MANAGER", "SALES"},
    "view_own_sales":     {"MANAGER", "SALES"},
    "view_all_sales":     {"OWNER", "MANAGER"},
    "view_movements":     {"OWNER", "MANAGER"},
    "view_access_log":    {"OWNER", "MANAGER"},
    "view_reports":       {"OWNER", "MANAGER"},
    "manage_users":       {"MANAGER"},
    "backup":             {"OWNER", "MANAGER"},
    "view_cost_prices":   {"OWNER", "MANAGER"},          # Sales Staff never see cost prices
}


@dataclass
class User:
    user_id: int
    username: str
    role: str
    is_active: bool = True

    def has_permission(self, action: str) -> bool:
        """True if this user's role appears in the permissions table for `action`."""
        return self.role in PERMISSIONS.get(action, set())

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


@dataclass
class Product:
    product_id: int
    product_name: str
    unit_price: float
    cost_price: float
    qty_in_stock: int
    reorder_level: int
    is_active: bool = True
    category: Optional[str] = None
    description: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        """Build a Product object from a database row."""
        keys = row.keys()
        return cls(
            product_id=row["product_id"],
            product_name=row["product_name"],
            unit_price=row["unit_price"],
            cost_price=row["cost_price"],
            qty_in_stock=row["qty_in_stock"],
            reorder_level=row["reorder_level"],
            is_active=bool(row["is_active"]),
            category=row["category"],
            description=row["description"],
            supplier_id=row["supplier_id"],
            supplier_name=row["supplier_name"] if "supplier_name" in keys else None,
        )

    def is_low_stock(self) -> bool:
        """FR-11: stock has reached or fallen below the reorder level."""
        return self.qty_in_stock <= self.reorder_level

    @property
    def stock_value(self) -> float:
        """FR-19: quantity x cost price."""
        return round(self.qty_in_stock * self.cost_price, 2)


class Sale:
    @staticmethod
    def calculate_change(total: float, amount_tendered: float) -> float:
        return round(amount_tendered - total, 2)


class StockMovement:
    TYPES = ("SALE", "GRN", "ADJUSTMENT")

    @staticmethod
    def is_adjustment(movement_type: str) -> bool:
        return movement_type == "ADJUSTMENT"
