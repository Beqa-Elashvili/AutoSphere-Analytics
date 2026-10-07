-- =============================================================================
-- 05_product.sql — category and product performance
-- =============================================================================

-- Category x year.
CREATE OR REPLACE VIEW analytics.v_category_performance AS
SELECT category_name, business_line, year,
       sum(revenue)                                                             AS revenue,
       sum(profit)                                                              AS profit,
       ROUND(100 * sum(profit) / NULLIF(sum(revenue), 0), 2)                    AS profit_margin_pct,
       sum(quantity)                                                            AS units,
       count(DISTINCT invoice_number)                                           AS orders,
       ROUND(100 * sum(revenue) / sum(sum(revenue)) OVER (PARTITION BY year), 2) AS revenue_share_pct,
       RANK() OVER (PARTITION BY year ORDER BY sum(revenue) DESC)               AS revenue_rank
FROM analytics.v_sales
GROUP BY category_name, business_line, year;

-- Product (all-time) with rankings and a sales-vs-margin portfolio quadrant.
-- Quadrants compare each product with the MEDIAN revenue and margin of its peer group
-- (vehicles are compared with vehicles, everything else with non-vehicle products),
-- otherwise every vehicle would look "high sales" and every part "low sales".
CREATE OR REPLACE VIEW analytics.v_product_performance AS
WITH p AS (
    SELECT product_id, product_name, brand, category_name, business_line,
           business_line = 'vehicles'                                AS is_vehicle,
           sum(revenue) AS revenue, sum(profit) AS profit, sum(quantity) AS units,
           count(DISTINCT invoice_number) AS orders,
           ROUND(100 * sum(profit) / NULLIF(sum(revenue), 0), 2)     AS profit_margin_pct
    FROM analytics.v_sales
    GROUP BY product_id, product_name, brand, category_name, business_line
), medians AS (
    SELECT is_vehicle,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY revenue)           AS median_revenue,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY profit_margin_pct) AS median_margin
    FROM p GROUP BY is_vehicle
)
SELECT p.*,
       RANK() OVER (ORDER BY p.revenue DESC)                        AS revenue_rank,
       RANK() OVER (ORDER BY p.profit DESC)                         AS profit_rank,
       RANK() OVER (ORDER BY p.profit_margin_pct DESC)              AS margin_rank,
       ROUND(100 * p.revenue / sum(p.revenue) OVER (), 2)           AS revenue_share_pct,
       CASE WHEN p.revenue >= m.median_revenue AND p.profit_margin_pct >= m.median_margin THEN 'Star: high sales, high margin'
            WHEN p.revenue >= m.median_revenue                                           THEN 'Volume driver: high sales, low margin'
            WHEN p.profit_margin_pct >= m.median_margin                                  THEN 'Niche: low sales, high margin'
            ELSE 'Underperformer: low sales, low margin' END        AS portfolio_quadrant
FROM p JOIN medians m ON m.is_vehicle = p.is_vehicle;
