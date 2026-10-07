-- dim_customer: SCD Type 2 on (customer_type, city, loyalty_tier); Type 1 on contact data.
--
--  * first load: every customer gets one version valid 1900-01-01 .. 9999-12-31
--  * later load with a changed type-2 attribute: the current version is closed
--    (valid_to = as_of - 1) and a new version starts on as_of
--  * a second change on the same day updates that day's version in place
--  * facts pick the version valid on the transaction date (point-in-time lookup)

DROP TABLE IF EXISTS tmp_customer_src;   -- allows re-running within one transaction
CREATE TEMP TABLE tmp_customer_src ON COMMIT DROP AS
SELECT customer_id,
       COALESCE(CASE WHEN customer_type = 'corporate' THEN company_name END,
                first_name || ' ' || last_name, company_name, customer_id) AS customer_name,
       customer_type, city,
       CASE city WHEN 'Tbilisi' THEN 'Tbilisi'            WHEN 'Batumi'  THEN 'Adjara'
                 WHEN 'Kutaisi' THEN 'Imereti'            WHEN 'Rustavi' THEN 'Kvemo Kartli'
                 WHEN 'Zugdidi' THEN 'Samegrelo-Zemo Svaneti' WHEN 'Poti' THEN 'Samegrelo-Zemo Svaneti'
                 WHEN 'Gori'    THEN 'Shida Kartli'       WHEN 'Telavi'  THEN 'Kakheti'
                 ELSE 'Unknown' END AS region,
       loyalty_tier, email, phone, registration_date,
       extract(year FROM registration_date)::smallint AS registration_year
FROM staging.customers;

-- 1. Type 1 attributes: overwrite on every version (corrections, not history).
UPDATE dw.dim_customer d
SET customer_name = s.customer_name, email = s.email, phone = s.phone,
    registration_date = s.registration_date, registration_year = s.registration_year, updated_at = now()
FROM tmp_customer_src s
WHERE d.customer_id = s.customer_id
  AND (d.customer_name, d.email, d.phone, d.registration_date)
      IS DISTINCT FROM (s.customer_name, s.email, s.phone, s.registration_date);

-- 2a. Changed type-2 attributes on a version created today: update in place.
UPDATE dw.dim_customer d
SET customer_type = s.customer_type, city = s.city, region = s.region, loyalty_tier = s.loyalty_tier,
    updated_at = now()
FROM tmp_customer_src s
WHERE d.customer_id = s.customer_id AND d.is_current AND d.valid_from = %(as_of)s::date
  AND (d.customer_type, d.city, d.loyalty_tier) IS DISTINCT FROM (s.customer_type, s.city, s.loyalty_tier);

-- 2b. Changed type-2 attributes on an older version: close it.
UPDATE dw.dim_customer d
SET valid_to = %(as_of)s::date - 1, is_current = false, updated_at = now()
FROM tmp_customer_src s
WHERE d.customer_id = s.customer_id AND d.is_current AND d.valid_from < %(as_of)s::date
  AND (d.customer_type, d.city, d.loyalty_tier) IS DISTINCT FROM (s.customer_type, s.city, s.loyalty_tier);

-- 3. Insert a new current version for changed customers and for brand-new customers.
INSERT INTO dw.dim_customer (customer_id, customer_name, customer_type, city, region, loyalty_tier, email,
                             phone, registration_date, registration_year, valid_from, valid_to, is_current)
SELECT s.customer_id, s.customer_name, s.customer_type, s.city, s.region, s.loyalty_tier, s.email, s.phone,
       s.registration_date, s.registration_year,
       CASE WHEN EXISTS (SELECT 1 FROM dw.dim_customer h WHERE h.customer_id = s.customer_id)
            THEN %(as_of)s::date ELSE DATE '1900-01-01' END,
       DATE '9999-12-31', true
FROM tmp_customer_src s
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.customer_id = s.customer_id AND d.is_current);

-- Refresh planner statistics on dimensions before facts join against them.
ANALYZE dw.dim_date, dw.dim_branch, dw.dim_category, dw.dim_product, dw.dim_customer, dw.dim_vehicle, dw.dim_employee;
