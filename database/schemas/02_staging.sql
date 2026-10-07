-- =============================================================================
-- 02_staging.sql — cleaned source entities (the data contract)
--
-- Staging holds data AFTER Python validation/cleaning, keyed by business keys.
-- Constraints here are a second line of defence: if a cleaning bug lets a bad
-- row through, PostgreSQL rejects the load instead of corrupting the warehouse.
--
-- Referential integrity between staging tables is validated by the DQ framework
-- (and enforced with real foreign keys in the dw schema), so staging tables can
-- be truncated and reloaded independently.
--
-- Timestamps are business-local time (Asia/Tbilisi); money is GEL, NUMERIC(12,2).
-- =============================================================================

-- ---------- Reference / master data -----------------------------------------

CREATE TABLE IF NOT EXISTS staging.branches (
    branch_id     TEXT PRIMARY KEY,                       -- e.g. BR01
    branch_name   TEXT    NOT NULL,
    city          TEXT    NOT NULL,                       -- canonical city name
    region        TEXT    NOT NULL,
    branch_type   TEXT    NOT NULL CHECK (branch_type IN ('sales_and_service', 'sales_only', 'service_only')),
    opened_date   DATE    NOT NULL,
    is_active     BOOLEAN NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.product_categories (
    category_id   TEXT PRIMARY KEY,                       -- e.g. CAT01
    category_name TEXT NOT NULL UNIQUE,
    business_line TEXT NOT NULL CHECK (business_line IN ('vehicles', 'parts', 'accessories', 'consumables')),
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.products (
    product_id    TEXT PRIMARY KEY,                       -- e.g. PRD001
    product_name  TEXT          NOT NULL,
    category_id   TEXT          NOT NULL,
    brand         TEXT          NOT NULL,                 -- fictional brands only
    unit_cost     NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),
    list_price    NUMERIC(12,2) NOT NULL CHECK (list_price > 0),
    launch_date   DATE          NOT NULL,
    is_active     BOOLEAN       NOT NULL,
    loaded_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.employees (
    employee_id   TEXT PRIMARY KEY,                       -- e.g. EMP001
    first_name    TEXT    NOT NULL,
    last_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('branch_manager', 'sales_consultant', 'service_advisor', 'technician', 'cashier')),
    department    TEXT    NOT NULL CHECK (department IN ('management', 'sales', 'service', 'finance')),
    branch_id     TEXT    NOT NULL,
    hire_date     DATE    NOT NULL,
    is_active     BOOLEAN NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id       TEXT PRIMARY KEY,                   -- e.g. CUS00001
    customer_type     TEXT NOT NULL CHECK (customer_type IN ('individual', 'corporate')),
    first_name        TEXT,
    last_name         TEXT,
    company_name      TEXT,
    email             TEXT,                               -- synthetic, example.com domain
    phone             TEXT,                               -- synthetic
    city              TEXT NOT NULL,                      -- canonical city or 'Unknown'
    registration_date DATE NOT NULL,
    loyalty_tier      TEXT NOT NULL CHECK (loyalty_tier IN ('standard', 'silver', 'gold', 'platinum')),
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (customer_type = 'corporate' OR (first_name IS NOT NULL AND last_name IS NOT NULL)),
    CHECK (customer_type = 'individual' OR company_name IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS staging.vehicles (
    vehicle_id        TEXT PRIMARY KEY,                   -- e.g. VEH00001
    vin               TEXT     NOT NULL UNIQUE CHECK (length(vin) = 17),
    make              TEXT     NOT NULL,
    model             TEXT     NOT NULL,
    model_year        SMALLINT NOT NULL CHECK (model_year BETWEEN 1980 AND 2100),
    fuel_type         TEXT     NOT NULL CHECK (fuel_type IN ('petrol', 'diesel', 'hybrid', 'electric', 'lpg')),
    transmission      TEXT     NOT NULL CHECK (transmission IN ('manual', 'automatic')),
    customer_id       TEXT     NOT NULL,                  -- current owner
    registration_date DATE     NOT NULL,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- Transactions ---------------------------------------------------------

-- Grain: one row per invoice line (an invoice = one customer order).
CREATE TABLE IF NOT EXISTS staging.sales (
    sale_line_id    TEXT PRIMARY KEY,                     -- e.g. SL0000001
    invoice_number  TEXT          NOT NULL,               -- order identifier, groups lines
    sale_datetime   TIMESTAMP     NOT NULL,
    customer_id     TEXT          NOT NULL,
    product_id      TEXT          NOT NULL,
    branch_id       TEXT          NOT NULL,
    employee_id     TEXT          NOT NULL,
    quantity        INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    unit_cost       NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),   -- cost at time of sale
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    sales_channel   TEXT          NOT NULL CHECK (sales_channel IN ('in_store', 'online', 'phone')),
    order_status    TEXT          NOT NULL CHECK (order_status IN ('completed', 'cancelled', 'returned')),
    loaded_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CHECK (discount_amount <= quantity * unit_price)
);
CREATE INDEX IF NOT EXISTS ix_stg_sales_invoice ON staging.sales (invoice_number);

-- Grain: one row per service visit (work order).
CREATE TABLE IF NOT EXISTS staging.service_orders (
    service_order_id TEXT PRIMARY KEY,                    -- e.g. SO000001
    vehicle_id       TEXT      NOT NULL,
    customer_id      TEXT      NOT NULL,
    branch_id        TEXT      NOT NULL,
    employee_id      TEXT      NOT NULL,                  -- service advisor
    service_type     TEXT      NOT NULL CHECK (service_type IN ('maintenance', 'repair', 'diagnostics', 'tire_service', 'body_work', 'warranty')),
    opened_at        TIMESTAMP NOT NULL,
    closed_at        TIMESTAMP,
    order_status     TEXT      NOT NULL CHECK (order_status IN ('completed', 'cancelled', 'in_progress')),
    odometer_km      INTEGER   CHECK (odometer_km >= 0),
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CHECK (order_status <> 'completed' OR closed_at IS NOT NULL)
);

-- Grain: one row per labour or part line on a service order.
CREATE TABLE IF NOT EXISTS staging.service_items (
    service_item_id  TEXT PRIMARY KEY,                    -- e.g. SI0000001
    service_order_id TEXT          NOT NULL,
    item_type        TEXT          NOT NULL CHECK (item_type IN ('labor', 'part')),
    product_id       TEXT,                                -- required for parts, NULL for labour
    description      TEXT          NOT NULL,
    quantity         NUMERIC(10,2) NOT NULL CHECK (quantity > 0),   -- labour hours may be fractional
    unit_price       NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    unit_cost        NUMERIC(12,2) NOT NULL CHECK (unit_cost >= 0),
    loaded_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CHECK (item_type = 'labor' OR product_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_stg_service_items_order ON staging.service_items (service_order_id);

-- Grain: one row per payment attempt against a sale invoice or service order.
CREATE TABLE IF NOT EXISTS staging.payments (
    payment_id       TEXT PRIMARY KEY,                    -- e.g. PAY0000001
    source_type      TEXT          NOT NULL CHECK (source_type IN ('sale', 'service')),
    source_reference TEXT          NOT NULL,              -- invoice_number or service_order_id
    customer_id      TEXT          NOT NULL,
    payment_datetime TIMESTAMP     NOT NULL,
    amount           NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    payment_method   TEXT          NOT NULL CHECK (payment_method IN ('cash', 'card', 'bank_transfer', 'installment')),
    payment_status   TEXT          NOT NULL CHECK (payment_status IN ('completed', 'failed', 'refunded')),
    currency         CHAR(3)       NOT NULL DEFAULT 'GEL' CHECK (currency = 'GEL'),
    loaded_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Grain: one row per feedback submission (free text in Georgian or English).
CREATE TABLE IF NOT EXISTS staging.customer_feedback (
    feedback_id      TEXT PRIMARY KEY,                    -- e.g. FB000001
    customer_id      TEXT     NOT NULL,
    branch_id        TEXT     NOT NULL,
    service_order_id TEXT,                                -- set when feedback is about a service visit
    invoice_number   TEXT,                                -- set when feedback is about a purchase
    feedback_date    DATE     NOT NULL,
    channel          TEXT     NOT NULL CHECK (channel IN ('sms_survey', 'email_survey', 'website', 'call_center')),
    rating           SMALLINT CHECK (rating BETWEEN 1 AND 5),   -- optional star rating
    feedback_text    TEXT     NOT NULL CHECK (length(trim(feedback_text)) > 0),
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
