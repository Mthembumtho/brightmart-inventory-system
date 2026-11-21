"""
conftest.py - shared set-up for the automated tests (pytest).

Every test gets a brand-new temporary database, so tests never touch the
real shop data and never affect each other.

Run all tests with:   python -m pytest -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app                                      # noqa: E402
from db import get_db, init_db                                  # noqa: E402
from services.auth_service import AuthService                   # noqa: E402
from services.product_service import ProductService             # noqa: E402
from services.stock_service import StockService                 # noqa: E402

PASSWORDS = {"manager": "Manager@123", "owner": "Owner@1234", "lindelwe": "Sales@1234",
             "musa": "Sales@1234"}


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.db"),
        "BACKUP_FOLDER": str(tmp_path / "backups"),
    })
    with app.app_context():
        init_db()
        db = get_db()
        AuthService.create_user(db, "owner", PASSWORDS["owner"], "OWNER")
        AuthService.create_user(db, "lindelwe", PASSWORDS["lindelwe"], "SALES")
        AuthService.create_user(db, "musa", PASSWORDS["musa"], "SALES")
        paperco = ProductService.create_supplier(db, {"supplier_name": "PaperCo",
                                                      "phone": "015 307 1100"})
        notebook = ProductService.create_product(db, {
            "product_name": "A4 Notebook 80pg", "category": "Stationery", "unit_price": "12.50",
            "cost_price": "8.00", "reorder_level": "15", "supplier_id": paperco})
        pen = ProductService.create_product(db, {
            "product_name": "Blue Pen (box)", "category": "Stationery", "unit_price": "35.00",
            "cost_price": "22.00", "reorder_level": "10", "supplier_id": paperco})
        cloth = ProductService.create_product(db, {
            "product_name": "Dish Cloth", "category": "Kitchenware", "unit_price": "10.00",
            "cost_price": "6.00", "reorder_level": "10"})
        # Opening stock through a real GRN: notebook 8, pen 30, cloth 5
        StockService.receive_grn(db, 1, paperco, None, "DN-TEST-1", "2026-11-01", [
            {"product_id": notebook, "qty_received": 8, "unit_cost": 8.00},
            {"product_id": pen, "qty_received": 30, "unit_cost": 22.00},
            {"product_id": cloth, "qty_received": 5, "unit_cost": 6.00}])
    app.ids = {"paperco": paperco, "notebook": notebook, "pen": pen, "cloth": cloth}
    return app


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()


def login(client, username):
    return client.post("/login", data={"username": username, "password": PASSWORDS[username]})


@pytest.fixture
def as_manager(app):
    c = app.test_client()
    login(c, "manager")
    return c


@pytest.fixture
def as_owner(app):
    c = app.test_client()
    login(c, "owner")
    return c


@pytest.fixture
def as_sales(app):
    c = app.test_client()
    login(c, "lindelwe")
    return c
