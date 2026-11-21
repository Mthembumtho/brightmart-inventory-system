"""
ReportService - sales and inventory reports and CSV export (FR-18, FR-19, FR-20).
All reports only READ data; they never change anything.
"""
import csv
import io
from datetime import date

from services import ServiceError


class ReportService:

    @staticmethod
    def _check_range(date_from, date_to):
        if not date_from or not date_to:
            raise ServiceError("Choose a start and end date")
        if date_from > date_to:
            raise ServiceError("Start date must be before the end date")

    @staticmethod
    def sales_report(db, date_from, date_to):
        """FR-18: total sales, number of transactions and best-selling products."""
        ReportService._check_range(date_from, date_to)
        start, end = date_from + " 00:00:00", date_to + " 23:59:59"

        summary = db.execute("""
            SELECT COUNT(*)                        AS transactions,
                   COALESCE(SUM(total_amount), 0)  AS total_sales,
                   COALESCE(AVG(total_amount), 0)  AS average_sale,
                   COALESCE(SUM(CASE WHEN payment_type = 'CASH' THEN total_amount END), 0) AS cash_total,
                   COALESCE(SUM(CASE WHEN payment_type = 'CARD' THEN total_amount END), 0) AS card_total
            FROM Sale WHERE sale_datetime BETWEEN ? AND ?""", (start, end)).fetchone()

        items_sold = db.execute("""
            SELECT COALESCE(SUM(l.quantity), 0) FROM SaleLine l
            JOIN Sale s ON s.sale_id = l.sale_id
            WHERE s.sale_datetime BETWEEN ? AND ?""", (start, end)).fetchone()[0]

        best_sellers = db.execute("""
            SELECT p.product_name, p.category,
                   SUM(l.quantity)   AS qty_sold,
                   SUM(l.line_total) AS revenue
            FROM SaleLine l
            JOIN Sale s    ON s.sale_id = l.sale_id
            JOIN Product p ON p.product_id = l.product_id
            WHERE s.sale_datetime BETWEEN ? AND ?
            GROUP BY l.product_id
            ORDER BY qty_sold DESC, revenue DESC
            LIMIT 10""", (start, end)).fetchall()

        daily = db.execute("""
            SELECT substr(sale_datetime, 1, 10) AS day,
                   COUNT(*) AS transactions,
                   SUM(total_amount) AS total_sales
            FROM Sale WHERE sale_datetime BETWEEN ? AND ?
            GROUP BY day ORDER BY day""", (start, end)).fetchall()

        return {"summary": summary, "items_sold": items_sold,
                "best_sellers": best_sellers, "daily": daily,
                "date_from": date_from, "date_to": date_to}

    @staticmethod
    def inventory_report(db):
        """FR-19: stock levels, reorder levels, low-stock flag and stock value."""
        rows = db.execute("""
            SELECT p.product_name, p.category, p.qty_in_stock, p.reorder_level,
                   p.cost_price, p.unit_price,
                   ROUND(p.qty_in_stock * p.cost_price, 2) AS stock_value,
                   CASE WHEN p.qty_in_stock <= p.reorder_level THEN 1 ELSE 0 END AS is_low,
                   s.supplier_name
            FROM Product p
            LEFT JOIN Supplier s ON s.supplier_id = p.supplier_id
            WHERE p.is_active = 1
            ORDER BY p.category, p.product_name""").fetchall()
        total_value = round(sum(r["stock_value"] for r in rows), 2)
        low_count = sum(r["is_low"] for r in rows)
        return {"rows": rows, "total_value": total_value, "low_count": low_count,
                "product_count": len(rows)}

    @staticmethod
    def today_summary(db):
        """Figures for the dashboard (Figure 4.6.2)."""
        today = date.today().isoformat()
        start, end = today + " 00:00:00", today + " 23:59:59"
        row = db.execute("""SELECT COUNT(*) AS transactions,
                                   COALESCE(SUM(total_amount), 0) AS total_sales
                            FROM Sale WHERE sale_datetime BETWEEN ? AND ?""",
                         (start, end)).fetchone()
        items = db.execute("""SELECT COALESCE(SUM(l.quantity), 0) FROM SaleLine l
                              JOIN Sale s ON s.sale_id = l.sale_id
                              WHERE s.sale_datetime BETWEEN ? AND ?""", (start, end)).fetchone()[0]
        return {"transactions": row["transactions"], "total_sales": row["total_sales"],
                "items_sold": items}

    # ------------------------------------------------------------------
    # FR-20 Export to CSV
    # ------------------------------------------------------------------
    @staticmethod
    def export_csv(headers, rows):
        """Turn a list of rows into CSV text that Excel can open."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        return buffer.getvalue()

    @staticmethod
    def sales_report_csv(report):
        rows = [["Summary", ""],
                ["Period", f"{report['date_from']} to {report['date_to']}"],
                ["Total sales (R)", f"{report['summary']['total_sales']:.2f}"],
                ["Transactions", report["summary"]["transactions"]],
                ["Items sold", report["items_sold"]],
                ["Cash (R)", f"{report['summary']['cash_total']:.2f}"],
                ["Card (R)", f"{report['summary']['card_total']:.2f}"],
                [],
                ["Best-selling products", "Category", "Qty sold", "Revenue (R)"]]
        rows += [[r["product_name"], r["category"] or "", r["qty_sold"], f"{r['revenue']:.2f}"]
                 for r in report["best_sellers"]]
        rows += [[], ["Day", "Transactions", "Total sales (R)"]]
        rows += [[d["day"], d["transactions"], f"{d['total_sales']:.2f}"] for d in report["daily"]]
        return ReportService.export_csv(["BrightMart Traders - Sales Report"], rows)

    @staticmethod
    def inventory_report_csv(report):
        headers = ["Product", "Category", "Qty in stock", "Reorder level", "Cost price (R)",
                   "Unit price (R)", "Stock value (R)", "Low stock", "Supplier"]
        rows = [[r["product_name"], r["category"] or "", r["qty_in_stock"], r["reorder_level"],
                 f"{r['cost_price']:.2f}", f"{r['unit_price']:.2f}", f"{r['stock_value']:.2f}",
                 "YES" if r["is_low"] else "", r["supplier_name"] or ""] for r in report["rows"]]
        rows.append(["TOTAL", "", "", "", "", "", f"{report['total_value']:.2f}", "", ""])
        return ReportService.export_csv(headers, rows)
