-- Business question: Where should management investigate operational issues?
-- KPI: Median / P90 service turnaround vs the same branch a year earlier
-- Source: analytics.v_service_turnaround (percentile_cont), maintenance jobs only
-- Decision: staffing or process review where turnaround deteriorates (feeds waiting-time complaints).
WITH m AS (
    SELECT branch_name, year, quarter_number, year_quarter,
           median_turnaround_hours, p90_turnaround_hours, service_orders
    FROM analytics.v_service_turnaround
    WHERE service_type = 'maintenance'
)
SELECT cur.branch_name,
       cur.year_quarter,
       cur.service_orders,
       cur.median_turnaround_hours,
       prev.median_turnaround_hours                                                  AS median_same_quarter_last_year,
       ROUND(100 * (cur.median_turnaround_hours / NULLIF(prev.median_turnaround_hours, 0) - 1), 1) AS change_pct,
       cur.p90_turnaround_hours,
       CASE WHEN cur.median_turnaround_hours > 1.3 * prev.median_turnaround_hours THEN 'INVESTIGATE'
            ELSE 'ok' END                                                            AS flag
FROM m cur
JOIN m prev ON prev.branch_name = cur.branch_name AND prev.year = cur.year - 1
           AND prev.quarter_number = cur.quarter_number
WHERE cur.year = (SELECT current_year FROM analytics.v_data_period)
ORDER BY change_pct DESC NULLS LAST;
