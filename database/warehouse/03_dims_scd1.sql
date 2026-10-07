-- SCD Type 1 dimensions: upsert on the business key. Changed attributes are overwritten;
-- surrogate keys stay stable across runs. Rows are never deleted (history of facts
-- may still reference them).

INSERT INTO dw.dim_branch (branch_id, branch_name, city, region, branch_type, offers_sales, offers_service, opened_date, is_active)
SELECT branch_id, branch_name, city, region, branch_type,
       branch_type IN ('sales_and_service', 'sales_only'),
       branch_type IN ('sales_and_service', 'service_only'),
       opened_date, is_active
FROM staging.branches
ON CONFLICT (branch_id) DO UPDATE SET
    branch_name = EXCLUDED.branch_name, city = EXCLUDED.city, region = EXCLUDED.region,
    branch_type = EXCLUDED.branch_type, offers_sales = EXCLUDED.offers_sales,
    offers_service = EXCLUDED.offers_service, opened_date = EXCLUDED.opened_date,
    is_active = EXCLUDED.is_active, updated_at = now();

INSERT INTO dw.dim_category (category_id, category_name, business_line)
SELECT category_id, category_name, business_line FROM staging.product_categories
ON CONFLICT (category_id) DO UPDATE SET
    category_name = EXCLUDED.category_name, business_line = EXCLUDED.business_line, updated_at = now();

INSERT INTO dw.dim_product (product_id, product_name, brand, category_name, business_line, list_price,
                            unit_cost, list_margin_pct, price_band, launch_date, is_active)
SELECT p.product_id, p.product_name, p.brand,
       COALESCE(c.category_name, 'Unknown category'),
       COALESCE(c.business_line, 'unknown'),
       p.list_price, p.unit_cost,
       ROUND(100 * (p.list_price - p.unit_cost) / NULLIF(p.list_price, 0), 2),
       CASE WHEN p.list_price IS NULL   THEN 'Unknown'
            WHEN p.list_price < 50      THEN '1. Under 50 GEL'
            WHEN p.list_price < 200     THEN '2. 50-199 GEL'
            WHEN p.list_price < 1000    THEN '3. 200-999 GEL'
            WHEN p.list_price < 20000   THEN '4. 1,000-19,999 GEL'
            ELSE '5. Vehicles 20,000+ GEL' END,
       p.launch_date, p.is_active
FROM staging.products p
LEFT JOIN staging.product_categories c ON c.category_id = p.category_id
ON CONFLICT (product_id) DO UPDATE SET
    product_name = EXCLUDED.product_name, brand = EXCLUDED.brand, category_name = EXCLUDED.category_name,
    business_line = EXCLUDED.business_line, list_price = EXCLUDED.list_price, unit_cost = EXCLUDED.unit_cost,
    list_margin_pct = EXCLUDED.list_margin_pct, price_band = EXCLUDED.price_band,
    launch_date = EXCLUDED.launch_date, is_active = EXCLUDED.is_active, updated_at = now();

INSERT INTO dw.dim_vehicle (vehicle_id, vin, make, model, make_model, model_year, age_band, fuel_type,
                            transmission, owner_customer_id)
SELECT vehicle_id, vin, make, model, make || ' ' || model, model_year,
       CASE WHEN model_year IS NULL                                   THEN 'Unknown'
            WHEN extract(year FROM %(as_of)s::date) - model_year <= 3 THEN '0-3 years'
            WHEN extract(year FROM %(as_of)s::date) - model_year <= 7 THEN '4-7 years'
            WHEN extract(year FROM %(as_of)s::date) - model_year <= 12 THEN '8-12 years'
            ELSE '13+ years' END,
       fuel_type, transmission, customer_id
FROM staging.vehicles
ON CONFLICT (vehicle_id) DO UPDATE SET
    vin = EXCLUDED.vin, make = EXCLUDED.make, model = EXCLUDED.model, make_model = EXCLUDED.make_model,
    model_year = EXCLUDED.model_year, age_band = EXCLUDED.age_band, fuel_type = EXCLUDED.fuel_type,
    transmission = EXCLUDED.transmission, owner_customer_id = EXCLUDED.owner_customer_id, updated_at = now();

INSERT INTO dw.dim_employee (employee_id, full_name, role, department, home_branch_id, home_branch_name,
                             hire_date, is_active)
SELECT e.employee_id, e.first_name || ' ' || e.last_name, e.role, e.department, e.branch_id,
       COALESCE(b.branch_name, 'Unknown branch'), e.hire_date, e.is_active
FROM staging.employees e
LEFT JOIN staging.branches b ON b.branch_id = e.branch_id
ON CONFLICT (employee_id) DO UPDATE SET
    full_name = EXCLUDED.full_name, role = EXCLUDED.role, department = EXCLUDED.department,
    home_branch_id = EXCLUDED.home_branch_id, home_branch_name = EXCLUDED.home_branch_name,
    hire_date = EXCLUDED.hire_date, is_active = EXCLUDED.is_active, updated_at = now();
