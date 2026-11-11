-- now.station_status: latest weather, recent rain, and rain since 1 October against the two previous hydrological years.
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
hy AS (SELECT CASE WHEN month(as_of) >= 10 THEN year(as_of) ELSE year(as_of) - 1 END AS year, as_of FROM as_of_hour),
wx AS (
  SELECT * FROM embalses.obs.weather WHERE observed_at > now() - INTERVAL 48 HOUR
  QUALIFY row_number() OVER (PARTITION BY station_id ORDER BY observed_at DESC) = 1
),
win AS (
  SELECT station_id,
         max(measured_mm) FILTER (WHERE time_window = '1h')  AS r1,
         max(measured_mm) FILTER (WHERE time_window = '6h')  AS r6,
         max(measured_mm) FILTER (WHERE time_window = '12h') AS r12,
         max(measured_mm) FILTER (WHERE time_window = '24h') AS r24
  FROM station_window GROUP BY 1
),
daily AS (
  SELECT d.station_id,
         sum(d.precipitation_mm) FILTER (WHERE d.hydrological_year = hy.year) AS this_year,
         max(d.observation_date) FILTER (WHERE d.hydrological_year = hy.year) AS through,
         sum(d.precipitation_mm) FILTER (WHERE d.hydrological_year = hy.year - 1
                                         AND d.observation_date <= (hy.as_of - INTERVAL 1 YEAR)::DATE) AS same_last,
         sum(d.precipitation_mm) FILTER (WHERE d.hydrological_year = hy.year - 1) AS last_total,
         sum(d.precipitation_mm) FILTER (WHERE d.hydrological_year = hy.year - 2) AS two_ago_total
  FROM embalses.obs.daily_weather d, hy GROUP BY 1
),
recent AS (   -- hourly rain after the last daily value, so the year-to-date total reaches "now"
  SELECT r.station_id, sum(r.precipitation_mm) AS mm
  FROM rain r JOIN daily d USING (station_id)
  WHERE r.period_end_at > (d.through + 1)::TIMESTAMPTZ + INTERVAL 7 HOUR   -- AEMET's daily rain runs 07–07 UTC
  GROUP BY 1
)
SELECT s.station_id,
       (SELECT as_of FROM as_of_hour)                      AS as_of,
       wx.observed_at                                      AS latest_observation_at,
       wx.air_temperature_c                                AS air_temperature_c,
       wx.relative_humidity_pct                            AS relative_humidity_pct,
       win.r1                                              AS rain_1h_mm,
       win.r6                                              AS rain_6h_mm,
       win.r12                                             AS rain_12h_mm,
       win.r24                                             AS rain_24h_mm,
       round(d.this_year + coalesce(rc.mm, 0), 1)          AS rain_hydro_year_mm,
       d.through                                           AS hydro_year_daily_through,
       round(d.same_last, 1)                               AS rain_same_period_last_year_mm,
       round(d.last_total, 1)                              AS rain_last_hydro_year_total_mm,
       round(d.two_ago_total, 1)                           AS rain_two_years_ago_total_mm,
       datediff('minute', wx.observed_at, now())::INTEGER  AS data_age_minutes
FROM embalses.ref.stations s
LEFT JOIN wx USING (station_id)
LEFT JOIN win USING (station_id)
LEFT JOIN daily d USING (station_id)
LEFT JOIN recent rc USING (station_id)
WHERE wx.station_id IS NOT NULL OR win.station_id IS NOT NULL OR d.station_id IS NOT NULL
