-- Business question: What is the repeat customer rate, and is it changing?
-- KPI: Repeat Customer Rate = customers with 2+ orders / customers with 1+ order
-- Source: analytics.v_kpi_by_year, analytics.v_kpi_summary
-- Decision: loyalty programme targets; a falling rate signals a retention problem.
-- Note: a partial year naturally shows a lower rate (less time to place a 2nd order).
SELECT year::text AS period, months_covered, customer_count, repeat_customers, repeat_customer_rate_pct
FROM analytics.v_kpi_by_year
UNION ALL
SELECT 'all time', NULL, customer_count, repeat_customers, repeat_customer_rate_pct
FROM analytics.v_kpi_summary
ORDER BY period;
