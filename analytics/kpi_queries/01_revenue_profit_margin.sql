-- KPI: Revenue, Profit, Profit Margin (all time) - implemented directly on the star schema.
-- Revenue = SUM(net_amount) of recognized (completed) sales lines.
-- Profit  = SUM(net_amount - cost_amount) of the same lines.
-- Margin  = Profit / Revenue.
SELECT SUM(net_amount)                                          AS revenue,
       SUM(profit_amount)                                       AS profit,
       ROUND(100 * SUM(profit_amount) / NULLIF(SUM(net_amount), 0), 2) AS profit_margin_pct
FROM dw.fact_sales
WHERE is_revenue_recognized;
