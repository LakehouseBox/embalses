-- now.upstream_rain: rain over all the land that drains into each reservoir, per window (reads now.rain_grid).
-- Runs inside LakehouseBox as a derived sink (scheduled SQL that reads the catalog), mode replace: each run swaps the table.
-- One SELECT; see lakehouse.yaml for its schedule.
WITH
rain AS (   -- hourly rain of the last 80 h; sinks deliver at least once, so de-duplicate on the interval key
  SELECT DISTINCT station_id, period_end_at, period_minutes, precipitation_mm
  FROM embalses.obs.precipitation
  WHERE period_end_at > now() - INTERVAL 80 HOUR AND precipitation_mm IS NOT NULL
),
as_of_hour AS (   -- the same "now" the rain grid used
  SELECT max(as_of) AS as_of FROM embalses."now".rain_grid
),
windows AS (SELECT * FROM (VALUES ('1h', 1), ('6h', 6), ('12h', 12), ('24h', 24), ('72h', 72)) w(time_window, hours)),
station_window AS (   -- rain per station and window; a station counts when it reported >= 75 % of the window
  SELECT w.time_window, w.hours, r.station_id,
         sum(r.precipitation_mm) AS measured_mm,
         sum(r.precipitation_mm) * (w.hours * 60.0) / sum(r.period_minutes) AS rain_mm
  FROM rain r, windows w, as_of_hour a
  WHERE r.period_end_at > a.as_of - to_hours(w.hours) AND r.period_end_at <= a.as_of
  GROUP BY w.time_window, w.hours, r.station_id
  HAVING sum(r.period_minutes) >= 0.75 * w.hours * 60
),
unit_rain AS (   -- gridded rain averaged over each catchment unit
  SELECT g.time_window, cc.catchment_id, sum(g.rain_mm * cc.cell_weight) / sum(cc.cell_weight) AS rain_mm
  FROM embalses.ref.catchment_cells cc JOIN embalses."now".rain_grid g USING (h3_cell)
  GROUP BY g.time_window, cc.catchment_id
),
tot AS (SELECT reservoir_id, sum(area_km2) AS area FROM embalses.ref.reservoir_catchments GROUP BY 1),
areal AS (
  SELECT rc.reservoir_id, u.time_window, sum(u.rain_mm * rc.area_km2) / sum(rc.area_km2) AS mm, sum(rc.area_km2) AS covered
  FROM embalses.ref.reservoir_catchments rc JOIN unit_rain u USING (catchment_id)
  GROUP BY rc.reservoir_id, u.time_window
),
gauges AS (
  SELECT rc.reservoir_id, sw.time_window, max(sw.rain_mm) AS max_mm, count(DISTINCT sw.station_id)::INTEGER AS n
  FROM embalses.ref.reservoir_catchments rc
  JOIN embalses.ref.stations s ON s.catchment_id = rc.catchment_id
  JOIN station_window sw USING (station_id)
  GROUP BY rc.reservoir_id, sw.time_window
)
SELECT a.reservoir_id,
       a.time_window,
       (SELECT as_of FROM as_of_hour)          AS as_of,
       round(a.mm, 2)                          AS areal_rain_mm,
       round(g.max_mm, 1)                      AS max_station_rain_mm,
       round(a.mm * t.area / 1000.0, 3)        AS rain_volume_hm3,      -- 1 mm over 1 km² = 0.001 hm³
       round(t.area, 1)                        AS upstream_area_km2,
       round(100.0 * a.covered / t.area, 1)    AS area_covered_pct,
       coalesce(g.n, 0)                        AS stations_reporting
FROM areal a JOIN tot t USING (reservoir_id)
LEFT JOIN gauges g USING (reservoir_id, time_window)
