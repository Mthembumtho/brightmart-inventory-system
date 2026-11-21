-- =====================================================================
-- BrightMart Traders - Inventory & Sales Management System
-- Database schema (SQLite)
--
-- This file creates the 11 tables from the ERD in the Part 1 report
-- (Figure 4.4). Rules that protect the data are written as CHECK
-- constraints, so the database itself refuses bad data even if the
-- Python code has a bug (NFR-08).
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Users and audit
-- ---------------------------------------------------------------------
CREATE TABLE User (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT    NOT NULL,                       -- never the real password (NFR-04)
    role           TEXT    NOT NULL CHECK (role IN ('OWNER', 'MANAGER', 'SALES')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE AccessLog (                                   -- FR-04
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES User(user_id),
    event_type      TEXT    NOT NULL,                      -- LOGIN, LOGOUT, TIMEOUT, ACCESS_DENIED
    event_detail    TEXT,                                  -- e.g. which page was refused
    event_datetime  TEXT    NOT NULL
);

-- ---------------------------------------------------------------------
-- Products and suppliers
-- ---------------------------------------------------------------------
CREATE TABLE Supplier (                                    -- FR-06
    supplier_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name   TEXT    NOT NULL,
    contact_person  TEXT,
    phone           TEXT,
    email           TEXT,
    address         TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE Product (                                     -- FR-05
    product_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id    INTEGER REFERENCES Supplier(supplier_id),   -- nullable: 0..1 supplier (FR-07)
    product_name   TEXT    NOT NULL,
    description    TEXT,
    category       TEXT,
    unit_price     REAL    NOT NULL CHECK (unit_price >= 0),
    cost_price     REAL    NOT NULL DEFAULT 0 CHECK (cost_price >= 0),
    qty_in_stock   INTEGER NOT NULL DEFAULT 0 CHECK (qty_in_stock >= 0),  -- no negative stock (FR-15, NFR-08)
    reorder_level  INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- ---------------------------------------------------------------------
-- Sales (header + detail)
-- ---------------------------------------------------------------------
CREATE TABLE Sale (                                        -- FR-13
    sale_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no       TEXT    NOT NULL UNIQUE,
    sale_datetime    TEXT    NOT NULL,
    user_id          INTEGER NOT NULL REFERENCES User(user_id),
    payment_type     TEXT    NOT NULL CHECK (payment_type IN ('CASH', 'CARD')),
    total_amount     REAL    NOT NULL CHECK (total_amount > 0),
    amount_tendered  REAL    NOT NULL,
    change_due       REAL    NOT NULL CHECK (change_due >= 0)
);

CREATE TABLE SaleLine (
    sale_line_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id       INTEGER NOT NULL REFERENCES Sale(sale_id),
    product_id    INTEGER NOT NULL REFERENCES Product(product_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    REAL    NOT NULL CHECK (unit_price >= 0),
    line_total    REAL    NOT NULL CHECK (line_total >= 0)
);

-- ---------------------------------------------------------------------
-- Purchase orders and goods received (header + detail)
-- ---------------------------------------------------------------------
CREATE TABLE PurchaseOrder (                               -- FR-10
    po_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id  INTEGER NOT NULL REFERENCES Supplier(supplier_id),
    created_by   INTEGER NOT NULL REFERENCES User(user_id),
    order_date   TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'OPEN'
                 CHECK (status IN ('OPEN', 'PARTIALLY_RECEIVED', 'CLOSED'))
);

CREATE TABLE PurchaseOrderLine (
    po_line_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id         INTEGER NOT NULL REFERENCES PurchaseOrder(po_id),
    product_id    INTEGER NOT NULL REFERENCES Product(product_id),
    qty_ordered   INTEGER NOT NULL CHECK (qty_ordered > 0),
    qty_received  INTEGER NOT NULL DEFAULT 0 CHECK (qty_received >= 0),
    CHECK (qty_received <= qty_ordered)                    -- cannot over-receive
);

CREATE TABLE GRN (                                         -- FR-08
    grn_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grn_number        TEXT    NOT NULL UNIQUE,
    supplier_id       INTEGER NOT NULL REFERENCES Supplier(supplier_id),
    po_id             INTEGER REFERENCES PurchaseOrder(po_id),   -- nullable: PO is optional
    received_by       INTEGER NOT NULL REFERENCES User(user_id),
    delivery_note_no  TEXT    NOT NULL,
    received_date     TEXT    NOT NULL
);

CREATE TABLE GRNLine (
    grn_line_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    grn_id        INTEGER NOT NULL REFERENCES GRN(grn_id),
    product_id    INTEGER NOT NULL REFERENCES Product(product_id),
    qty_received  INTEGER NOT NULL CHECK (qty_received > 0),
    unit_cost     REAL    NOT NULL CHECK (unit_cost >= 0)
);

-- ---------------------------------------------------------------------
-- Stock movement log - the central audit trail (FR-12)
-- ---------------------------------------------------------------------
CREATE TABLE StockMovement (
    movement_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id         INTEGER NOT NULL REFERENCES Product(product_id),
    user_id            INTEGER NOT NULL REFERENCES User(user_id),
    sale_id            INTEGER REFERENCES Sale(sale_id),   -- set only for SALE movements
    grn_id             INTEGER REFERENCES GRN(grn_id),     -- set only for GRN movements
    movement_type      TEXT    NOT NULL CHECK (movement_type IN ('SALE', 'GRN', 'ADJUSTMENT')),
    qty_change         INTEGER NOT NULL CHECK (qty_change <> 0),
    reason             TEXT,
    movement_datetime  TEXT    NOT NULL,
    -- an adjustment must always have a reason (FR-09)
    CHECK (movement_type <> 'ADJUSTMENT' OR (reason IS NOT NULL AND TRIM(reason) <> ''))
);

-- ---------------------------------------------------------------------
-- Indexes on fields used for searching and reports (NFR-09)
-- ---------------------------------------------------------------------
CREATE INDEX idx_product_name       ON Product(product_name);
CREATE INDEX idx_product_category   ON Product(category);
CREATE INDEX idx_sale_datetime      ON Sale(sale_datetime);
CREATE INDEX idx_sale_user          ON Sale(user_id);
CREATE INDEX idx_saleline_sale      ON SaleLine(sale_id);
CREATE INDEX idx_saleline_product   ON SaleLine(product_id);
CREATE INDEX idx_movement_product   ON StockMovement(product_id);
CREATE INDEX idx_movement_datetime  ON StockMovement(movement_datetime);
CREATE INDEX idx_accesslog_datetime ON AccessLog(event_datetime);
