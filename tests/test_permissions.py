"""Role-based access and POPIA - FR-02, NFR-04, NFR-05."""


def test_tc09_sales_staff_refused_user_management_and_logged(as_sales, db):
    """TC-09 (FR-02, NFR-04): Sales Staff cannot open Users; the attempt is logged."""
    assert as_sales.get("/users/").status_code == 403
    last = db.execute("SELECT event_type, event_detail FROM AccessLog "
                      "ORDER BY log_id DESC LIMIT 1").fetchone()
    assert last["event_type"] == "ACCESS_DENIED" and last["event_detail"] == "/users/"


def test_tc10_sales_staff_cannot_see_supplier_details(as_sales):
    """TC-10 (NFR-05 POPIA): no supplier page, no supplier or cost columns for Sales Staff."""
    assert as_sales.get("/suppliers").status_code == 403
    page = as_sales.get("/products").data
    assert b"PaperCo" not in page
    assert b"Cost price" not in page
    dashboard = as_sales.get("/").data
    assert b"015 307 1100" not in dashboard


def test_tc11_owner_cannot_record_sales_or_stock(as_owner):
    """TC-11 (FR-02): Business Owner is a viewing role (permissions table, 3.4)."""
    assert as_owner.get("/sales/new").status_code == 403
    assert as_owner.get("/stock/grn/new").status_code == 403
    assert as_owner.get("/stock/adjust").status_code == 403
    assert as_owner.get("/reports/sales").status_code == 200
    assert as_owner.get("/access-log").status_code == 200


def test_tc12_not_logged_in_redirects_to_login(app):
    """TC-12 (NFR-04): every page needs a login."""
    c = app.test_client()
    for page in ["/", "/products", "/sales/new", "/reports/sales", "/users/"]:
        r = c.get(page)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_tc13_menu_only_shows_allowed_items(as_sales, as_manager):
    """TC-13 (FR-02): the navigation menu changes with the role."""
    sales_page = as_sales.get("/").data
    assert b"Record Sale" in sales_page and b">Users<" not in sales_page and b">Reports<" not in sales_page
    manager_page = as_manager.get("/").data
    assert b">Users<" in manager_page and b">Reports<" in manager_page
