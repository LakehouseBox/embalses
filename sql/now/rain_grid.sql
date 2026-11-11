-- now.rain_grid: rain over the last 1, 6, 12, 24 and 72 hours on the H3 grid, interpolated from every gauge within 40 km
-- (inverse-distance weighting, power 2, 1 km smoothing).
-- Runs inside LakehouseBox as a derived sink (scheduled SQL that reads the catalog), mode replace: each run swaps the table.
-- One SELECT; see lakehouse.yaml for its schedule.
WITH
rain AS (   -- hourly rain of the last 80 h; sinks deliver at least once, so de-duplicate on the interval key
  SELECT DISTINCT station_id, period_end_at, period_minutes, precipitation_mm
  FROM embalses.obs.precipitation
  WHERE period_end_at > now() - INTERVAL 80 HOUR AND precipitation_mm IS NOT NULL
),
as_of_hour AS (   -- "now" = the latest hour at least half the gauges have reported (AEMET publishes gradually)
  SELECT max(period_end_at) AS as_of
  FROM (SELECT period_end_at, count(DISTINCT station_id) AS n FROM rain GROUP BY 1)
  WHERE n >= 0.5 * (SELECT max(n) FROM (SELECT count(DISTINCT station_id) AS n FROM rain GROUP BY period_end_at))
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
st AS (SELECT station_id, ST_X(location) AS lon, ST_Y(location) AS lat FROM embalses.ref.stations),
cell AS (
  SELECT h3_cell, h3_cell_to_lat(h3_string_to_h3(h3_cell)) AS lat, h3_cell_to_lng(h3_string_to_h3(h3_cell)) AS lon
  FROM embalses.ref.grid_cells
),
pairs AS (   -- gauge–cell pairs in a bounding box, with their great-circle distance (haversine)
  SELECT c.h3_cell, s.station_id,
         2 * 6371.0088 * asin(sqrt(pow(sin(radians(s.lat - c.lat) / 2), 2)
             + cos(radians(c.lat)) * cos(radians(s.lat)) * pow(sin(radians(s.lon - c.lon) / 2), 2))) AS km
  FROM cell c JOIN st s ON abs(s.lat - c.lat) < 0.4 AND abs(s.lon - c.lon) < 0.5
)
SELECT p.h3_cell,
       sw.time_window,
       (SELECT as_of FROM as_of_hour)                                                     AS as_of,
       round(sum(sw.rain_mm / (p.km * p.km + 1)) / sum(1 / (p.km * p.km + 1)), 2)         AS rain_mm,
       count(*)::INTEGER                                                                  AS stations_used,
       round(min(p.km), 1)                                                                AS nearest_station_km
FROM pairs p JOIN station_window sw USING (station_id)
WHERE p.km <= 40
GROUP BY p.h3_cell, sw.time_window
