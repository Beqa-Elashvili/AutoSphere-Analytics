-- Unknown / not-applicable members. Facts never hold NULL dimension keys: an unresolved
-- reference points to -1 ('Unknown'); labour lines without a product point to -2.
INSERT INTO dw.dim_branch (branch_key, branch_id, branch_name, city, region, branch_type, offers_sales, offers_service, opened_date, is_active)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'Unknown branch', 'Unknown', 'Unknown', 'unknown', false, false, NULL, false)
ON CONFLICT (branch_key) DO NOTHING;

INSERT INTO dw.dim_category (category_key, category_id, category_name, business_line)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'Unknown category', 'unknown'),
       (-2, 'N/A',     'Labour',           'services')
ON CONFLICT (category_key) DO NOTHING;

INSERT INTO dw.dim_product (product_key, product_id, product_name, brand, category_name, business_line, price_band, is_active)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'Unknown product',     'Unknown', 'Unknown category', 'unknown',  'Unknown', false),
       (-2, 'N/A',     'Labour (no product)', 'N/A',     'Labour',           'services', 'N/A',     true)
ON CONFLICT (product_key) DO NOTHING;

INSERT INTO dw.dim_customer (customer_key, customer_id, customer_name, customer_type, city, region, loyalty_tier, valid_from, valid_to, is_current)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'Unknown customer', 'unknown', 'Unknown', 'Unknown', 'unknown',
        DATE '1900-01-01', DATE '9999-12-31', true)
ON CONFLICT (customer_key) DO NOTHING;

INSERT INTO dw.dim_vehicle (vehicle_key, vehicle_id, vin, make, model, make_model, age_band, fuel_type, transmission)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'UNKNOWN', 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'unknown', 'unknown')
ON CONFLICT (vehicle_key) DO NOTHING;

INSERT INTO dw.dim_employee (employee_key, employee_id, full_name, role, department, home_branch_name, is_active)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNKNOWN', 'Unknown employee', 'unknown', 'unknown', 'Unknown branch', false)
ON CONFLICT (employee_key) DO NOTHING;
