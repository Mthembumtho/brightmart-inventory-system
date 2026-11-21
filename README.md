# BrightMart Traders – Inventory & Sales Management System

A local web application for one shop, built with **Python (Flask)**, **SQLite** and **HTML/CSS/JavaScript**, following the design in the Part 1 Foundational Technical Report.

---

## 1. First-time setup (Windows, Command Prompt)

Open the project folder in VS Code and open a **Command Prompt** terminal (Ctrl + `). Then type:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create the database. Pick **one** of these:

```
python init_db.py           (empty database, for real use)
python init_db.py --demo    (sample shop data, for testing and screenshots)
```

## 2. Running the system

```
python app.py
```

Open **http://127.0.0.1:5000** in Chrome or Edge. Press **Ctrl + C** in the terminal to stop the server.

| Account | Username | Password | Notes |
|---|---|---|---|
| Store Manager | `manager` | `Manager@123` | Always created. Change this password after the first login |
| Business Owner | `owner` | `Owner@1234` | Demo data only |
| Sales Staff | `lindelwe`, `musa` | `Sales@1234` | Demo data only |

### Record Sale keyboard shortcuts (Figure 4.6.4)

| Key | Action |
|---|---|
| F2 | Product search (then arrow keys and Enter) |
| F3 | Quantity |
| F4 or Enter | Add line |
| F6 | Switch between Cash and Card |
| F7 | Amount tendered |
| F9 | Complete sale |
| Esc | Cancel the sale |

## 3. Testing

```
python -m pytest -v          (44 automated tests, about 1 minute)
python tools\load_test.py    (speed test: 2,000 products and 50,000 sales)
```

Each test is named after its test case, e.g. `test_tc20_cannot_add_more_than_in_stock`, and its first line says which requirement it proves.

## 4. Backup and restore (NFR-03)

* **Back up:** log in as Manager or Owner, open **Backup**, click **Back up now**, then **Download** and copy the file to a flash drive.
* **Restore:** stop the server, then run `python restore_backup.py backups\<file name>`.

---

## 5. How the code is organised

The code follows the layers from the Part 1 class diagram (Figure 4.5):

```
Browser (templates + static)          what the user sees
   │  HTTP request
   ▼
routes/      (Flask blueprints)       receives the request, checks the login/role,
   │                                  calls a service, chooses the page to show
   ▼
services/    (business logic)         the rules from the Part 1 pseudocode
   │
   ▼
db.py + schema.sql (SQLite)           stores the data; CHECK constraints are the last safety net
```

| File / folder | What it does |
|---|---|
| `app.py` | Creates the Flask app, registers all screens, starts the server |
| `db.py` | Opens and closes the SQLite connection for each request; creates the database |
| `schema.sql` | The 11 tables from the ERD (Figure 4.4), with constraints and indexes |
| `models.py` | Model classes and the **permissions table** from Section 3.4 |
| `security.py` | `@login_required`, `@permission_required`, and the 15-minute idle timeout |
| `services/auth_service.py` | Login, password hashing, access log, user management |
| `services/product_service.py` | Products, suppliers, search |
| `services/sales_service.py` | `add_line_to_cart`, `record_sale` (the transaction) |
| `services/stock_service.py` | `write_movement`, `receive_grn`, `adjust_stock`, purchase orders, low stock |
| `services/report_service.py` | Sales and inventory reports, CSV export |
| `services/backup_service.py` | One-click backup |
| `routes/*.py` | One file per area: auth, main, products, sales, stock, reports, users |
| `templates/` | HTML pages (Jinja templates); `base.html` holds the menu shared by every page |
| `static/style.css` | One stylesheet for every page |
| `static/sale.js` | The keyboard-driven Record Sale screen |
| `tests/` | Automated tests (pytest) |
| `tools/load_test.py` | Performance test for NFR-02 and NFR-09 |

### Follow one sale through the code (a good way to study it)

1. The cashier presses **F4**. `static/sale.js` → `addLine()` sends the product and quantity to `/sales/validate-line`.
2. `routes/sales.py` → `validate_line()` calls `SalesService.add_line_to_cart()`, which checks stock **including what is already in the cart**.
3. The cashier presses **F9**. `completeSale()` sends the cart to `/sales/complete`.
4. `SalesService.record_sale()` runs `BEGIN IMMEDIATE`, reads prices from the database, inserts the `Sale`, then for each line **re-checks stock**, inserts the `SaleLine`, deducts stock and calls `StockService.write_movement()`.
5. If anything fails, `ROLLBACK` cancels everything. If not, `COMMIT` saves it all at once. The receipt number goes back to the browser.

---

## 6. Requirement → where it is implemented → test

| Req | Implemented in | Test(s) |
|---|---|---|
| FR-01 Login | `auth_service.authenticate`, `routes/auth.py` | TC-01, TC-02 |
| FR-02 Role-based access | `models.PERMISSIONS`, `security.permission_required`, `base.html` menu | TC-09, TC-11, TC-13 |
| FR-03 User management | `auth_service` create/update/set_active, `routes/users.py` | TC-04, TC-08 |
| FR-04 Access log | `auth_service.log_access`, `/access-log` | TC-05, TC-06, TC-09 |
| FR-05 Products | `product_service`, `routes/products.py` | TC-14, TC-15 |
| FR-06 Suppliers | `product_service`, `/suppliers` | TC-18 |
| FR-07 Primary supplier | `Product.supplier_id` (nullable FK) | TC-14 |
| FR-08 GRN | `stock_service.receive_grn`, `/stock/grn/new` | TC-29, TC-32, TC-44 |
| FR-09 Adjustments | `stock_service.adjust_stock`, `/stock/adjust` | TC-33, TC-34, TC-35 |
| FR-10 Purchase orders / partial receipts | `stock_service.create_po`, `update_po_status` | TC-30, TC-31 |
| FR-11 Low-stock alerts | `stock_service.get_low_stock_products`, dashboard | TC-16, TC-36 |
| FR-12 Movement log | `stock_service.write_movement`, `/stock/movements` | TC-19, TC-29, TC-37 |
| FR-13 Record sales | `sales_service.record_sale`, `sale.js` | TC-19, TC-23, TC-25, TC-28 |
| FR-14 Automatic stock update | `sales_service.record_sale` | TC-19 |
| FR-15 Stock validation | `add_line_to_cart`, re-check in `record_sale`, `CHECK` constraint | TC-20, TC-21, TC-22 |
| FR-16 Transaction history | `sales_service.list_sales`, `/sales` | TC-26 |
| FR-17 Search and filter | `product_service.search_products` | TC-16 |
| FR-18 Sales report | `report_service.sales_report` | TC-38, TC-39 |
| FR-19 Inventory report | `report_service.inventory_report` | TC-40 |
| FR-20 CSV export | `report_service.export_csv` | TC-41 |
| NFR-02 Performance | indexes in `schema.sql` | `tools/load_test.py` |
| NFR-03 Backup | `backup_service`, `restore_backup.py` | TC-42 |
| NFR-04 Security | PBKDF2 hashing, 8-character minimum, idle timeout, role checks | TC-03, TC-06, TC-07, TC-08, TC-12 |
| NFR-05 POPIA | supplier pages and columns hidden from Sales Staff | TC-10 |
| NFR-08 Data integrity | transactions, `CHECK` constraints, deactivate instead of delete | TC-17, TC-22, TC-27, TC-35, TC-37 |
| NFR-09 Scalability | indexes in `schema.sql` | `tools/load_test.py` |

## 7. Security measures

* Passwords are hashed with PBKDF2-SHA256 (never stored as plain text), with a minimum length of 8 characters.
* Login errors give the same message for a wrong username and a wrong password.
* Sessions are signed with a secret key kept in `instance/secret_key.txt`. The cookie is `HttpOnly` and `SameSite=Lax`.
* Every route checks the user's role on the **server**. Hiding menu items is only for convenience.
* All SQL uses `?` placeholders (parameterised queries), which prevents SQL injection.
* Sale prices are always read from the database, never trusted from the browser.
* Refused access attempts are written to the access log.
