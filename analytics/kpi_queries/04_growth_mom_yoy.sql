-- KPI: MoM and YoY revenue growth for every month.
-- MoM = revenue(month) / revenue(previous month) - 1          (LAG over the ordered months)
-- YoY = revenue(month) / revenue(same month last year) - 1    (LAG of 12 over a gap-free month spine)
WITH months AS (
    SELECT DISTINCT d.year, d.month_number
    FROM dw.dim_date d
    WHERE d.full_date BETWEEN (SELECT min(sale_datetime)::date FROM dw.fact_sales)
                          AND (SELECT max(sale_datetime)::date FROM dw.fact_sales)
), revenue AS (
    SELECT d.year, d.month_number, SUM(f.net_amount) AS revenue
    FROM dw.fact_sales f JOIN dw.dim_date d ON d.date_key = f.date_key
    WHERE f.is_revenue_recognized
    GROUP BY d.year, d.month_number
), series AS (
    SELECT m.year, m.month_number, COALESCE(r.revenue, 0) AS revenue
    FROM months m LEFT JOIN revenue r USING (year, month_number)
)
SELECT year, month_number, revenue,
       ROUND(100 * (revenue / NULLIF(LAG(revenue)     OVER w, 0) - 1), 2) AS mom_growth_pct,
       ROUND(100 * (revenue / NULLIF(LAG(revenue, 12) OVER w, 0) - 1), 2) AS yoy_growth_pct
FROM series
WINDOW w AS (ORDER BY year, month_number)
ORDER BY year, month_number;
