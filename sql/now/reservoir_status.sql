-- now.reservoir_status: one row per bulletin reservoir: latest state (live SAIH reading if under 6 h old, else the weekly
-- bulletin), recent change, rain upstream (reads now.upstream_rain) and the same week in past years.
-- Runs inside LakehouseBox as a derived sink (scheduled SQL that reads the catalog), mode replace: each run swaps the table.
-- One SELECT; see lakehouse.yaml for its schedule.
WITH
weekly AS (   -- weekly bulletin, cleaned: one row per reservoir and date, impossible fills (> 110 %) dropped
  SELECT * REPLACE (coalesce(weekly_change_hm3,
                             stored_volume_hm3 - lag(stored_volume_hm3) OVER (PARTITION BY reservoir_id ORDER BY bulletin_date))
                    AS weekly_change_hm3)
  FROM (SELECT * FROM embalses.obs.reservoir_weekly
        WHERE fill_pct IS NULL OR fill_pct <= 110
        QUALIFY row_number() OVER (PARTITION BY reservoir_id, bulletin_date ORDER BY stored_volume_hm3 NULLS LAST) = 1)
),
latest AS (SELECT * FROM weekly QUALIFY row_number() OVER (PARTITION BY reservoir_id ORDER BY bulletin_date DESC) = 1),
same_week AS (   -- the same week in each of the 10 earlier years: the bulletin closest to the same date (within 4 days)
  SELECT l.reservoir_id, y.k AS years_back, w.fill_pct, w.stored_volume_hm3, w.capacity_hm3
  FROM latest l, range(1, 11) y(k), weekly w
  WHERE w.reservoir_id = l.reservoir_id
    AND abs(datediff('day', w.bulletin_date, l.bulletin_date - to_years(y.k::int))) <= 4
  QUALIFY row_number() OVER (PARTITION BY l.reservoir_id, y.k
                             ORDER BY abs(datediff('day', w.bulletin_date, l.bulletin_date - to_years(y.k::int)))) = 1
),
live AS (   -- live SAIH readings of the last 4 days, de-duplicated, with their reservoir from ref.stations
  SELECT DISTINCT r.station_id, s.reservoir_id, r.observed_at, r.stored_volume_hm3, r.inflow_m3s, r.outflow_m3s, r.source
  FROM embalses.obs.reservoir_readings r JOIN embalses.ref.stations s USING (station_id)
  WHERE r.observed_at > now() - INTERVAL 4 DAY AND s.reservoir_id IS NOT NULL AND r.stored_volume_hm3 IS NOT NULL
),
newest AS (SELECT * FROM live QUALIFY row_number() OVER (PARTITION BY reservoir_id ORDER BY observed_at DESC) = 1),
back AS (   -- the readings closest to 6, 24 and 72 h before the newest one (within 90 min)
  SELECT n.reservoir_id, h.hours, l.stored_volume_hm3
  FROM newest n, (VALUES (6), (24), (72)) h(hours), live l
  WHERE l.reservoir_id = n.reservoir_id
    AND abs(datediff('minute', l.observed_at, n.observed_at - to_hours(h.hours))) <= 90
  QUALIFY row_number() OVER (PARTITION BY n.reservoir_id, h.hours
                             ORDER BY abs(datediff('minute', l.observed_at, n.observed_at - to_hours(h.hours)))) = 1
),
live_now AS (
  SELECT n.reservoir_id, n.observed_at, n.stored_volume_hm3, n.inflow_m3s, n.outflow_m3s, n.source,
         n.stored_volume_hm3 - max(b.stored_volume_hm3) FILTER (WHERE b.hours = 6)  AS change_6h,
         n.stored_volume_hm3 - max(b.stored_volume_hm3) FILTER (WHERE b.hours = 24) AS change_24h,
         n.stored_volume_hm3 - max(b.stored_volume_hm3) FILTER (WHERE b.hours = 72) AS change_72h
  FROM newest n LEFT JOIN back b USING (reservoir_id)
  WHERE n.observed_at > now() - INTERVAL 6 HOUR
  GROUP BY n.reservoir_id, n.observed_at, n.stored_volume_hm3, n.inflow_m3s, n.outflow_m3s, n.source
),
avg10 AS (SELECT reservoir_id, round(avg(fill_pct), 1) AS fill FROM same_week GROUP BY 1)
SELECT r.reservoir_id,
       now()                                                                              AS as_of,
       coalesce(v.observed_at, l.bulletin_date::TIMESTAMPTZ)                              AS latest_reading_at,
       coalesce(v.source, 'miteco-weekly')                                                AS data_source,
       coalesce(v.stored_volume_hm3, l.stored_volume_hm3)                                 AS stored_volume_hm3,
       l.capacity_hm3                                                                     AS capacity_hm3,
       coalesce(round(100.0 * v.stored_volume_hm3 / nullif(l.capacity_hm3, 0), 2), l.fill_pct) AS fill_pct,
       round(v.change_6h, 3)                                                              AS change_6h_hm3,
       round(v.change_24h, 3)                                                             AS change_24h_hm3,
       round(v.change_72h, 3)                                                             AS change_72h_hm3,
       round(v.stored_volume_hm3 - l.stored_volume_hm3, 3)                                AS change_since_bulletin_hm3,
       l.weekly_change_hm3                                                                AS weekly_change_hm3,
       v.inflow_m3s                                                                       AS inflow_m3s,
       v.outflow_m3s                                                                      AS outflow_m3s,
       u24.areal_rain_mm                                                                  AS upstream_rain_24h_mm,
       u24.rain_volume_hm3                                                                AS upstream_rain_volume_24h_hm3,
       u72.areal_rain_mm                                                                  AS upstream_rain_72h_mm,
       ly.fill_pct                                                                        AS fill_pct_same_week_last_year,
       a.fill                                                                             AS fill_pct_10y_average,
       datediff('minute', coalesce(v.observed_at, l.bulletin_date::TIMESTAMPTZ), now())::INTEGER AS data_age_minutes
FROM embalses.ref.reservoirs r
LEFT JOIN latest l USING (reservoir_id)
LEFT JOIN live_now v USING (reservoir_id)
LEFT JOIN same_week ly ON ly.reservoir_id = r.reservoir_id AND ly.years_back = 1
LEFT JOIN avg10 a ON a.reservoir_id = r.reservoir_id
LEFT JOIN embalses."now".upstream_rain u24 ON u24.reservoir_id = r.reservoir_id AND u24.time_window = '24h'
LEFT JOIN embalses."now".upstream_rain u72 ON u72.reservoir_id = r.reservoir_id AND u72.time_window = '72h'
