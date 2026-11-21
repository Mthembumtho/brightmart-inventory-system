"""Dashboard (FR-11, Figure 4.6.2), access log (FR-04) and backup (NFR-03)."""
from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   send_from_directory, url_for)

from db import get_db
from security import login_required, permission_required
from services.auth_service import AuthService
from services.backup_service import BackupService
from services.report_service import ReportService
from services.stock_service import StockService

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    db = get_db()
    low_stock = StockService.get_low_stock_products(db)
    return render_template("dashboard.html",
                           today=ReportService.today_summary(db),
                           low_stock=low_stock[:5],
                           low_count=len(low_stock))


@bp.route("/access-log")
@permission_required("view_access_log")
def access_log():
    return render_template("access_log.html", entries=AuthService.access_log(get_db()))


@bp.route("/backup", methods=["GET", "POST"])
@permission_required("backup")
def backup():
    folder = current_app.config["BACKUP_FOLDER"]
    if request.method == "POST":
        name = BackupService.create_backup(get_db(), folder)
        flash(f"Backup created: {name}. Download it and copy it to a flash drive.", "success")
        return redirect(url_for("main.backup"))
    return render_template("backup.html", backups=BackupService.list_backups(folder))


@bp.route("/backup/download/<path:name>")
@permission_required("backup")
def download_backup(name):
    # send_from_directory refuses names like ..\..\secret so only backups can be downloaded
    return send_from_directory(current_app.config["BACKUP_FOLDER"], name, as_attachment=True)
