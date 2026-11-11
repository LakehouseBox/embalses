-- now.basin_summary: totals per river basin district (reads now.reservoir_status and now.rain_grid).
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
res AS (
  SELECT r.basin_id,
         sum(s.stored_volume_hm3) AS stored, sum(s.capacity_hm3) AS cap, sum(s.weekly_change_hm3) AS wk, sum(s.change_24h_hm3) AS ch24,
         count(*) FILTER (WHERE s.data_source <> 'miteco-weekly' AND s.data_age_minutes < 180)::INTEGER AS live,
         count(*)::INTEGER AS n
  FROM embalses.ref.reservoirs r JOIN embalses."now".reservoir_status s USING (reservoir_id)
  GROUP BY 1
),
hist AS (   -- basin fill in earlier years, from the same-week bulletins
  SELECT r.basin_id, sw.years_back, 100.0 * sum(sw.stored_volume_hm3) / sum(sw.capacity_hm3) AS fill
  FROM same_week sw JOIN embalses.ref.reservoirs r USING (reservoir_id)
  GROUP BY r.basin_id, sw.years_back
),
hist2 AS (SELECT basin_id, round(max(fill) FILTER (WHERE years_back = 1), 2) AS last_year, round(avg(fill), 2) AS avg10 FROM hist GROUP BY 1),
rain24 AS (
  SELECT c.basin_id, avg(g.rain_mm) AS mm
  FROM embalses."now".rain_grid g JOIN embalses.ref.grid_cells c USING (h3_cell)
  WHERE g.time_window = '24h' GROUP BY 1
)
SELECT b.basin_id,
       now()                                    AS as_of,
       res.stored                               AS stored_volume_hm3,
       res.cap                                  AS capacity_hm3,
       round(100.0 * res.stored / res.cap, 2)   AS fill_pct,
       res.wk                                   AS weekly_change_hm3,
       round(res.ch24, 3)                       AS change_24h_hm3,
       h.last_year                              AS fill_pct_same_week_last_year,
       h.avg10                                  AS fill_pct_10y_average,
       round(rain24.mm, 2)                      AS areal_rain_24h_mm,
       res.live                                 AS reservoirs_live,
       res.n                                    AS reservoirs_total
FROM embalses.ref.basins b
JOIN res USING (basin_id)
LEFT JOIN hist2 h USING (basin_id)
LEFT JOIN rain24 USING (basin_id)
