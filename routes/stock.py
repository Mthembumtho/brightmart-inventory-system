"""Stock screens: low stock (FR-11), GRN (FR-08, Figure 4.6.5), adjustments
(FR-09, Figure 4.6.6), purchase orders (FR-10) and the movement log (FR-12)."""
from datetime import date

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from db import get_db
from security import permission_required
from services import ServiceError
from services.product_service import ProductService
from services.stock_service import StockService

bp = Blueprint("stock", __name__, url_prefix="/stock")


def _read_lines(form, qty_field, with_cost=False):
    """The GRN and PO forms send lists: product_id[], qty[], cost[] - one entry per row."""
    product_ids = form.getlist("product_id")
    quantities = form.getlist(qty_field)
    costs = form.getlist("unit_cost")
    lines = []
    for i, pid in enumerate(product_ids):
        if not pid:
            continue
        try:
            line = {"product_id": int(pid), qty_field: int(quantities[i])}
            if with_cost:
                line["unit_cost"] = round(float(costs[i] or 0), 2)
        except (ValueError, IndexError):
            raise ServiceError("Quantities and costs must be numbers")
        lines.append(line)
    return lines


@bp.route("/low")
@permission_required("view_dashboard")
def low_stock():
    return render_template("stock/low.html", items=StockService.get_low_stock_products(get_db()))


# --------------------------------------------------------------------------- GRN
@bp.route("/grn")
@permission_required("record_grn")
def list_grns():
    return render_template("stock/grn_list.html", grns=StockService.list_grns(get_db()))


@bp.route("/grn/new", methods=["GET", "POST"])
@permission_required("record_grn")
def new_grn():
    db = get_db()
    posted_lines = []          # what the user typed, sent back to the form if saving fails
    if request.method == "POST":
        posted_lines = [{"product_id": pid, "qty_received": qty, "unit_cost": cost}
                        for pid, qty, cost in zip(request.form.getlist("product_id"),
                                                  request.form.getlist("qty_received"),
                                                  request.form.getlist("unit_cost"))]
        try:
            lines = _read_lines(request.form, "qty_received", with_cost=True)
            grn_number = StockService.receive_grn(
                db, g.user.user_id, request.form.get("supplier_id"), request.form.get("po_id"),
                request.form.get("delivery_note_no", ""), request.form.get("received_date", ""),
                lines)
            flash(f"{grn_number} saved. Stock levels have been increased.", "success")
            return redirect(url_for("stock.list_grns"))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("stock/grn_form.html",
                           suppliers=ProductService.list_suppliers(db, include_inactive=False),
                           products=ProductService.search_products(db),
                           open_pos=StockService.list_pos(db, open_only=True),
                           today=date.today().isoformat(),
                           selected_po=request.form.get("po_id") or request.args.get("po_id", ""),
                           posted_lines=posted_lines)


@bp.route("/grn/<int:grn_id>")
@permission_required("record_grn")
def grn_detail(grn_id):
    grn, lines = StockService.get_grn(get_db(), grn_id)
    if grn is None:
        abort(404)
    return render_template("stock/grn_detail.html", grn=grn, lines=lines)


# ------------------------------------------------------------------- adjustments
@bp.route("/adjust", methods=["GET", "POST"])
@permission_required("adjust_stock")
def adjust():
    db = get_db()
    if request.method == "POST":
        try:
            try:
                quantity = int(request.form.get("quantity", 0))
                product_id = int(request.form.get("product_id", 0))
            except ValueError:
                raise ServiceError("Choose a product and enter a whole-number quantity")
            StockService.adjust_stock(db, g.user.user_id, product_id,
                                      request.form.get("direction"), quantity,
                                      request.form.get("reason", ""))
            flash("Stock adjustment saved and logged.", "success")
            return redirect(url_for("stock.movements", type="ADJUSTMENT"))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("stock/adjust.html", products=ProductService.search_products(db),
                           form=request.form, selected=request.args.get("product_id", ""))


# ---------------------------------------------------------------- movement log
@bp.route("/movements")
@permission_required("view_movements")
def movements():
    db = get_db()
    product_id = request.args.get("product_id", "")
    movement_type = request.args.get("type", "")
    return render_template("stock/movements.html",
                           movements=StockService.list_movements(db, product_id or None,
                                                                 movement_type or None),
                           products=ProductService.search_products(db, include_inactive=True),
                           product_id=product_id, movement_type=movement_type)


# ------------------------------------------------------------- purchase orders
@bp.route("/po")
@permission_required("view_po")
def list_pos():
    return render_template("po/list.html", pos=StockService.list_pos(get_db()))


@bp.route("/po/new", methods=["GET", "POST"])
@permission_required("raise_po")
def new_po():
    db = get_db()
    if request.method == "POST":
        try:
            lines = _read_lines(request.form, "qty_ordered")
            po_id = StockService.create_po(db, g.user.user_id, request.form.get("supplier_id"),
                                           lines)
            flash(f"Purchase order PO-{po_id:05d} raised.", "success")
            return redirect(url_for("stock.po_detail", po_id=po_id))
        except ServiceError as e:
            flash(str(e), "error")
    return render_template("po/form.html",
                           suppliers=ProductService.list_suppliers(db, include_inactive=False),
                           products=ProductService.search_products(db))


@bp.route("/po/<int:po_id>")
@permission_required("view_po")
def po_detail(po_id):
    po, lines = StockService.get_po(get_db(), po_id)
    if po is None:
        abort(404)
    return render_template("po/detail.html", po=po, lines=lines)


@bp.route("/api/po/<int:po_id>")
@permission_required("record_grn")
def api_po(po_id):
    """Used by the GRN screen to fill in the outstanding lines of a chosen PO."""
    po, lines = StockService.get_po(get_db(), po_id)
    if po is None:
        return jsonify(ok=False), 404
    return jsonify(ok=True, supplier_id=po["supplier_id"],
                   lines=[{"product_id": l["product_id"], "product_name": l["product_name"],
                           "outstanding": l["qty_ordered"] - l["qty_received"]}
                          for l in lines if l["qty_ordered"] > l["qty_received"]])
