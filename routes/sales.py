"""Record Sale (FR-13 to FR-15, Figure 4.6.4) and transaction history (FR-16).

The Record Sale screen talks to the server with JavaScript (fetch) and JSON,
so the page does not reload while the cashier is working (Part 1, 2.2).
"""
from flask import Blueprint, abort, g, jsonify, render_template, request

from db import get_db
from security import login_required, permission_required
from services import ServiceError
from services.sales_service import SalesService

bp = Blueprint("sales", __name__)


@bp.route("/sales/new")
@permission_required("record_sale")
def new_sale():
    return render_template("sales/new.html")


@bp.route("/sales/validate-line", methods=["POST"])
@permission_required("record_sale")
def validate_line():
    """Called when the cashier presses [F4] Add line (5.3.1)."""
    data = request.get_json(silent=True) or {}
    try:
        line = SalesService.add_line_to_cart(get_db(), int(data.get("product_id", 0)),
                                             int(data.get("quantity", 0)),
                                             data.get("cart_lines", []))
        return jsonify(ok=True, line=line)
    except (ServiceError, ValueError, TypeError) as e:
        message = str(e) if isinstance(e, ServiceError) else "Enter a whole number"
        return jsonify(ok=False, message=message), 400


@bp.route("/sales/complete", methods=["POST"])
@permission_required("record_sale")
def complete_sale():
    """Called when the cashier presses [F9] Complete sale (5.3.2)."""
    data = request.get_json(silent=True) or {}
    try:
        tendered = data.get("amount_tendered")
        tendered = float(tendered) if tendered not in (None, "") else None
        sale_id, receipt_no, total, change_due = SalesService.record_sale(
            get_db(), g.user.user_id, data.get("cart_lines", []),
            data.get("payment_type"), tendered)
        return jsonify(ok=True, sale_id=sale_id, receipt_no=receipt_no,
                       total=total, change_due=change_due)
    except ServiceError as e:
        return jsonify(ok=False, message=str(e)), 400
    except (ValueError, TypeError, KeyError):
        return jsonify(ok=False, message="The sale data was not valid"), 400


@bp.route("/sales")
@login_required
def list_sales():
    """Owner/Manager see all sales; Sales Staff see only their own (permissions table)."""
    if g.user.has_permission("view_all_sales"):
        user_filter = None
    elif g.user.has_permission("view_own_sales"):
        user_filter = g.user.user_id
    else:
        abort(403)
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    sales = SalesService.list_sales(get_db(), user_filter, date_from or None, date_to or None)
    return render_template("sales/list.html", sales=sales, own_only=user_filter is not None,
                           date_from=date_from, date_to=date_to)


@bp.route("/sales/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    sale, lines = SalesService.get_sale(get_db(), sale_id)
    if sale is None:
        abort(404)
    if not g.user.has_permission("view_all_sales") and sale["user_id"] != g.user.user_id:
        abort(403)
    return render_template("sales/detail.html", sale=sale, lines=lines)
