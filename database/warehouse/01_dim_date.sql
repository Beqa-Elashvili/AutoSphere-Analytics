-- dim_date: one row per calendar day 2016-01-01 .. 2027-12-31 (static, insert-only).
-- Covers customer registration history and leaves headroom for future loads.
-- Public holidays: fixed-date Georgian holidays (moveable Orthodox Easter not modelled).
INSERT INTO dw.dim_date (
    date_key, full_date, day_of_month, day_name, day_of_week, is_weekend, iso_week,
    month_number, month_name, month_short, year_month, quarter_number, quarter_label,
    year, year_quarter, is_public_holiday, holiday_name)
SELECT to_char(d, 'YYYYMMDD')::int,
       d::date,
       extract(day FROM d)::smallint,
       to_char(d, 'FMDay'),
       extract(isodow FROM d)::smallint,
       extract(isodow FROM d) IN (6, 7),
       extract(week FROM d)::smallint,
       extract(month FROM d)::smallint,
       to_char(d, 'FMMonth'),
       to_char(d, 'Mon'),
       to_char(d, 'YYYY-MM'),
       extract(quarter FROM d)::smallint,
       'Q' || extract(quarter FROM d),
       extract(year FROM d)::smallint,
       extract(year FROM d) || '-Q' || extract(quarter FROM d),
       h.holiday_name IS NOT NULL,
       h.holiday_name
FROM generate_series(DATE '2016-01-01', DATE '2027-12-31', INTERVAL '1 day') AS d
LEFT JOIN (VALUES
    (1, 1, 'New Year'), (1, 2, 'New Year Holiday'), (1, 7, 'Orthodox Christmas'),
    (1, 19, 'Epiphany'), (3, 3, 'Mother''s Day'), (3, 8, 'International Women''s Day'),
    (4, 9, 'National Unity Day'), (5, 9, 'Victory Day'), (5, 12, 'St. Andrew''s Day'),
    (5, 26, 'Independence Day'), (8, 28, 'Mariamoba'), (10, 14, 'Svetitskhovloba'),
    (11, 23, 'Giorgoba')
) AS h (m, dd, holiday_name)
  ON h.m = extract(month FROM d) AND h.dd = extract(day FROM d)
ON CONFLICT (date_key) DO NOTHING;
