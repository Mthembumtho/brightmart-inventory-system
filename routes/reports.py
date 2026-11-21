"""Sales and inventory reports with CSV export (FR-18, FR-19, FR-20) - Figure 4.6.7."""
from datetime import date, timedelta

from flask import Blueprint, Response, flash, render_template, request

from db import get_db
from security import permission_required
from services import ServiceError
from services.report_service import ReportService

bp = Blueprint("reports", __name__, url_prefix="/reports")


def _csv_response(text, filename):
    # "utf-8-sig" adds a marker so Excel opens the file with the right characters
    return Response(text.encode("utf-8-sig"), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@bp.route("/sales")
@permission_required("view_reports")
def sales_report():
    today = date.today()
    date_from = request.args.get("from") or (today - timedelta(days=6)).isoformat()
    date_to = request.args.get("to") or today.isoformat()
    report = None
    try:
        report = ReportService.sales_report(get_db(), date_from, date_to)
    except ServiceError as e:
        flash(str(e), "error")
    if report and request.args.get("export") == "csv":
        return _csv_response(ReportService.sales_report_csv(report),
                             f"sales_report_{date_from}_to_{date_to}.csv")
    return render_template("reports/sales.html", report=report,
                           date_from=date_from, date_to=date_to)


@bp.route("/inventory")
@permission_required("view_reports")
def inventory_report():
    report = ReportService.inventory_report(get_db())
    if request.args.get("export") == "csv":
        return _csv_response(ReportService.inventory_report_csv(report),
                             f"inventory_report_{date.today().isoformat()}.csv")
    return render_template("reports/inventory.html", report=report)
