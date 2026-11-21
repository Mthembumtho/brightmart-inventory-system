"""Products and suppliers (FR-05, FR-06, FR-07, FR-17) - Figure 4.6.3."""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from db import get_db
from models import Product
from security import login_required, permission_required
from services import ServiceError
from services.product_service import ProductService

bp = Blueprint("products", __name__)


# ----------------------------------------------------------------------- products
@bp.route("/products")
@permission_required("view_products")
def list_products():
    db = get_db()
    text = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    low_only = request.args.get("low") == "1"
    show_inactive = request.args.get("inactive") == "1" and g.user.has_permission("manage_products")
    rows = ProductService.search_products(db, text, category, low_only, show_inactive)
    return render_template("products/list.html",
                           products=[Product.from_row(r) for r in rows],
                           categories=ProductService.categories(db),
                           q=text, category=category, low_only=low_only,
                           show_inactive=show_inactive)


@bp.route("/products/new", methods=["GET", "POST"])
@permission_required("manage_products")
def new_product():
    db = get_db()
    if request.method == "POST":
        try:
            ProductService.create_product(db, request.form)
            flash("Product added. Stock starts at 0 - record a GRN to add stock.", "success")
            return redirect(url_for("products.list_products"))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("products/form.html", product=request.form, is_new=True,
                           suppliers=ProductService.list_suppliers(db, include_inactive=False),
                           categories=ProductService.categories(db))


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@permission_required("manage_products")
def edit_product(product_id):
    db = get_db()
    product = ProductService.get_product(db, product_id)
    if product is None:
        abort(404)
    if request.method == "POST":
        try:
            ProductService.update_product(db, product_id, request.form)
            flash("Product updated.", "success")
            return redirect(url_for("products.list_products"))
        except ServiceError as e:
            flash(str(e), "error")
            product = request.form
    return render_template("products/form.html", product=product, is_new=False,
                           product_id=product_id,
                           suppliers=ProductService.list_suppliers(db, include_inactive=False),
                           categories=ProductService.categories(db))


@bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@permission_required("manage_products")
def toggle_product(product_id):
    db = get_db()
    product = ProductService.get_product(db, product_id)
    if product is None:
        abort(404)
    ProductService.set_product_active(db, product_id, not product["is_active"])
    flash(f"{product['product_name']} {'deactivated' if product['is_active'] else 're-activated'}.",
          "success")
    return redirect(request.referrer or url_for("products.list_products"))


@bp.route("/api/products")
@login_required
def api_products():
    """Product search used by the Record Sale and GRN screens (returns JSON)."""
    rows = ProductService.search_products(get_db(), request.args.get("q", ""))[:15]
    return jsonify([{"product_id": r["product_id"], "product_name": r["product_name"],
                     "unit_price": r["unit_price"], "qty_in_stock": r["qty_in_stock"],
                     "cost_price": r["cost_price"] if g.user.has_permission("view_cost_prices") else None}
                    for r in rows])


# ---------------------------------------------------------------------- suppliers
@bp.route("/suppliers")
@permission_required("view_suppliers")
def list_suppliers():
    return render_template("suppliers/list.html", suppliers=ProductService.list_suppliers(get_db()))


@bp.route("/suppliers/new", methods=["GET", "POST"])
@permission_required("manage_suppliers")
def new_supplier():
    if request.method == "POST":
        try:
            ProductService.create_supplier(get_db(), request.form)
            flash("Supplier added.", "success")
            return redirect(url_for("products.list_suppliers"))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("suppliers/form.html", supplier=request.form, is_new=True)


@bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@permission_required("manage_suppliers")
def edit_supplier(supplier_id):
    db = get_db()
    supplier = ProductService.get_supplier(db, supplier_id)
    if supplier is None:
        abort(404)
    if request.method == "POST":
        try:
            ProductService.update_supplier(db, supplier_id, request.form)
            flash("Supplier updated.", "success")
            return redirect(url_for("products.list_suppliers"))
        except ServiceError as e:
            flash(str(e), "error")
            supplier = request.form
    return render_template("suppliers/form.html", supplier=supplier, is_new=False,
                           supplier_id=supplier_id)


@bp.route("/suppliers/<int:supplier_id>/toggle", methods=["POST"])
@permission_required("manage_suppliers")
def toggle_supplier(supplier_id):
    db = get_db()
    supplier = ProductService.get_supplier(db, supplier_id)
    if supplier is None:
        abort(404)
    ProductService.set_supplier_active(db, supplier_id, not supplier["is_active"])
    flash(f"{supplier['supplier_name']} "
          f"{'deactivated' if supplier['is_active'] else 're-activated'}.", "success")
    return redirect(url_for("products.list_suppliers"))