-- =============================================================================
-- 04_dw.sql — analytical data warehouse (star schema)
--
-- Conventions
--   * dimensions: integer surrogate key <entity>_key + business key <entity>_id
--   * unknown members: key -1 ('Unknown'); key -2 = 'Not applicable' (labour lines)
--   * dim_customer is SCD Type 2; all other dimensions are SCD Type 1
--   * facts: one clearly defined grain each. Fact-to-dimension relationships are
--     LOGICAL foreign keys: not enforced by per-row triggers (they made the bulk load
--     ~6x slower) but verified set-based by the warehouse DQ gate (fk_* checks, CRITICAL)
--     after every build. Unknown members (-1) guarantee every key resolves.
--   * money in GEL, NUMERIC(14,2)
-- =============================================================================

-- ------------------------------------------------------------------ dimensions

CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key        INTEGER PRIMARY KEY,               -- YYYYMMDD
    full_date       DATE     NOT NULL UNIQUE,
    day_of_month    SMALLINT NOT NULL,
    day_name        TEXT     NOT NULL,
    day_of_week     SMALLINT NOT NULL,                 -- ISO: 1 = Monday
    is_weekend      BOOLEAN  NOT NULL,
    iso_week        SMALLINT NOT NULL,
    month_number    SMALLINT NOT NULL,
    month_name      TEXT     NOT NULL,
    month_short     TEXT     NOT NULL,
    year_month      TEXT     NOT NULL,                 -- '2025-03'
    quarter_number  SMALLINT NOT NULL,
    quarter_label   TEXT     NOT NULL,                 -- 'Q1'
    year            SMALLINT NOT NULL,
    year_quarter    TEXT     NOT NULL,                 -- '2025-Q1'
    is_public_holiday BOOLEAN NOT NULL,
    holiday_name    TEXT
);

CREATE TABLE IF NOT EXISTS dw.dim_branch (
    branch_key      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_id       TEXT NOT NULL UNIQUE,
    branch_name     TEXT NOT NULL,
    city            TEXT NOT NULL,
    region          TEXT NOT NULL,
    branch_type     TEXT NOT NULL,
    offers_sales    BOOLEAN NOT NULL,
    offers_service  BOOLEAN NOT NULL,
    opened_date     DATE,
    is_active       BOOLEAN NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.dim_category (
    category_key    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id     TEXT NOT NULL UNIQUE,
    category_name   TEXT NOT NULL,
    business_line   TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      TEXT NOT NULL UNIQUE,
    product_name    TEXT NOT NULL,
    brand           TEXT NOT NULL,
    category_name   TEXT NOT NULL,                     -- denormalized for drill-down tables
    business_line   TEXT NOT NULL,
    list_price      NUMERIC(14,2),
    unit_cost       NUMERIC(14,2),
    list_margin_pct NUMERIC(6,2),
    price_band      TEXT NOT NULL,
    launch_date     DATE,
    is_active       BOOLEAN NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- SCD Type 2: a new version is created when city, loyalty_tier or customer_type changes.
CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id       TEXT NOT NULL,
    customer_name     TEXT NOT NULL,
    customer_type     TEXT NOT NULL,                   -- type 2
    city              TEXT NOT NULL,                   -- type 2
    region            TEXT NOT NULL,
    loyalty_tier      TEXT NOT NULL,                   -- type 2
    email             TEXT,                            -- type 1
    phone             TEXT,                            -- type 1
    registration_date DATE,                            -- type 1
    registration_year SMALLINT,
    valid_from        DATE NOT NULL,
    valid_to          DATE NOT NULL,
    is_current        BOOLEAN NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to >= valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customer_current ON dw.dim_customer (customer_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_dim_customer_lookup ON dw.dim_customer (customer_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS dw.dim_vehicle (
    vehicle_key       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_id        TEXT NOT NULL UNIQUE,
    vin               TEXT NOT NULL,
    make              TEXT NOT NULL,
    model             TEXT NOT NULL,
    make_model        TEXT NOT NULL,
    model_year        SMALLINT,
    age_band          TEXT NOT NULL,
    fuel_type         TEXT NOT NULL,
    transmission      TEXT NOT NULL,
    owner_customer_id TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw.dim_employee (
    employee_key     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id      TEXT NOT NULL UNIQUE,
    full_name        TEXT NOT NULL,
    role             TEXT NOT NULL,
    department       TEXT NOT NULL,
    home_branch_id   TEXT,
    home_branch_name TEXT NOT NULL,
    hire_date        DATE,
    is_active        BOOLEAN NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------ facts

-- Grain: one row per invoice line.
CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sale_line_id      TEXT PRIMARY KEY,                -- degenerate key
    invoice_number    TEXT NOT NULL,                   -- degenerate dimension (order)
    date_key          INTEGER NOT NULL,
    customer_key      INTEGER NOT NULL,
    product_key       INTEGER NOT NULL,
    category_key      INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    employee_key      INTEGER NOT NULL,
    sale_datetime     TIMESTAMP NOT NULL,
    sales_channel     TEXT NOT NULL,
    order_status      TEXT NOT NULL,
    is_revenue_recognized BOOLEAN NOT NULL,            -- only completed sales count as revenue
    quantity          INTEGER NOT NULL,
    unit_price        NUMERIC(14,2) NOT NULL,
    unit_cost         NUMERIC(14,2) NOT NULL,
    gross_amount      NUMERIC(14,2) NOT NULL,          -- quantity * unit_price
    discount_amount   NUMERIC(14,2) NOT NULL,
    net_amount        NUMERIC(14,2) NOT NULL,          -- gross - discount (revenue)
    cost_amount       NUMERIC(14,2) NOT NULL,          -- quantity * unit_cost
    profit_amount     NUMERIC(14,2) NOT NULL           -- net - cost
);

-- Grain: one row per service order (work order), measures aggregated from its lines.
CREATE TABLE IF NOT EXISTS dw.fact_service_orders (
    service_order_id  TEXT PRIMARY KEY,
    opened_date_key   INTEGER NOT NULL,
    closed_date_key   INTEGER,   -- NULL while open
    customer_key      INTEGER NOT NULL,
    vehicle_key       INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    employee_key      INTEGER NOT NULL,
    service_type      TEXT NOT NULL,
    order_status      TEXT NOT NULL,
    is_completed      BOOLEAN NOT NULL,
    is_warranty       BOOLEAN NOT NULL,
    opened_at         TIMESTAMP NOT NULL,
    closed_at         TIMESTAMP,
    turnaround_hours  NUMERIC(10,2),
    odometer_km       INTEGER,
    item_count        INTEGER NOT NULL,
    labor_hours       NUMERIC(10,2) NOT NULL,
    labor_revenue     NUMERIC(14,2) NOT NULL,
    parts_revenue     NUMERIC(14,2) NOT NULL,
    total_revenue     NUMERIC(14,2) NOT NULL,
    total_cost        NUMERIC(14,2) NOT NULL,
    profit_amount     NUMERIC(14,2) NOT NULL
);

-- Grain: one row per labour or part line on a service order.
CREATE TABLE IF NOT EXISTS dw.fact_service_items (
    service_item_id   TEXT PRIMARY KEY,
    service_order_id  TEXT NOT NULL,
    date_key          INTEGER NOT NULL,   -- order opened date
    customer_key      INTEGER NOT NULL,
    vehicle_key       INTEGER NOT NULL,
    product_key       INTEGER NOT NULL,
    category_key      INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    service_type      TEXT NOT NULL,
    item_type         TEXT NOT NULL,
    order_status      TEXT NOT NULL,
    is_revenue_recognized BOOLEAN NOT NULL,
    quantity          NUMERIC(10,2) NOT NULL,
    unit_price        NUMERIC(14,2) NOT NULL,
    unit_cost         NUMERIC(14,2) NOT NULL,
    revenue_amount    NUMERIC(14,2) NOT NULL,
    cost_amount       NUMERIC(14,2) NOT NULL,
    profit_amount     NUMERIC(14,2) NOT NULL
);

-- Grain: one row per payment attempt.
CREATE TABLE IF NOT EXISTS dw.fact_payments (
    payment_id        TEXT PRIMARY KEY,
    date_key          INTEGER NOT NULL,
    customer_key      INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    source_type       TEXT NOT NULL,
    source_reference  TEXT NOT NULL,
    payment_datetime  TIMESTAMP NOT NULL,
    payment_method    TEXT NOT NULL,
    payment_status    TEXT NOT NULL,
    is_successful     BOOLEAN NOT NULL,
    amount            NUMERIC(14,2) NOT NULL,
    net_cash_amount   NUMERIC(14,2) NOT NULL           -- completed +, refunded -, failed 0
);

-- Grain: one row per feedback submission. AI columns are filled by the NLP pipeline (Phase 8).
CREATE TABLE IF NOT EXISTS dw.fact_customer_feedback (
    feedback_id       TEXT PRIMARY KEY,
    date_key          INTEGER NOT NULL,
    customer_key      INTEGER NOT NULL,
    branch_key        INTEGER NOT NULL,
    service_order_id  TEXT,
    invoice_number    TEXT,
    feedback_source   TEXT NOT NULL,                   -- service | sale | general
    channel           TEXT NOT NULL,
    rating            SMALLINT,
    feedback_text     TEXT NOT NULL,
    language          TEXT,                            -- AI: ka | en
    sentiment         TEXT,                            -- AI: positive | neutral | negative
    topic             TEXT,                            -- AI: service_quality, waiting_time, ...
    confidence        NUMERIC(4,3),                    -- AI: 0..1
    classification_method TEXT                         -- AI: e.g. gemini:<model> | rule_based
);

-- Foreign-key indexes for join performance.
CREATE INDEX IF NOT EXISTS ix_fs_date     ON dw.fact_sales (date_key);
CREATE INDEX IF NOT EXISTS ix_fs_customer ON dw.fact_sales (customer_key);
CREATE INDEX IF NOT EXISTS ix_fs_product  ON dw.fact_sales (product_key);
CREATE INDEX IF NOT EXISTS ix_fs_branch   ON dw.fact_sales (branch_key);
CREATE INDEX IF NOT EXISTS ix_fs_invoice  ON dw.fact_sales (invoice_number);
CREATE INDEX IF NOT EXISTS ix_fso_date    ON dw.fact_service_orders (opened_date_key);
CREATE INDEX IF NOT EXISTS ix_fso_branch  ON dw.fact_service_orders (branch_key);
CREATE INDEX IF NOT EXISTS ix_fsi_order   ON dw.fact_service_items (service_order_id);
CREATE INDEX IF NOT EXISTS ix_fsi_date    ON dw.fact_service_items (date_key);
CREATE INDEX IF NOT EXISTS ix_fp_date     ON dw.fact_payments (date_key);
CREATE INDEX IF NOT EXISTS ix_ff_date     ON dw.fact_customer_feedback (date_key);
CREATE INDEX IF NOT EXISTS ix_ff_branch   ON dw.fact_customer_feedback (branch_key);
