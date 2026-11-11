-- The queries the site runs. In the browser they run on DuckDB-WASM against the public catalog;
-- for design work they export a snapshot:
--   mkdir -p site/snapshot && lhbox duckdb --catalog embalses -- -f site/queries.sql
-- Each statement writes one JSON file named after the dataset.
LOAD spatial; SET geometry_always_xy = true; SET TimeZone = 'UTC';

-- basins: peninsula and Balearics outlines for the base map, simplified
COPY (
  SELECT basin_id, basin_name, basin_name_en,
         ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.01))::JSON AS geometry
  FROM embalses.ref.basins
  WHERE basin_id NOT LIKE 'ES12%' AND basin_id NOT IN ('ES150', 'ES160')
) TO 'site/snapshot/basins.json' (FORMAT json, ARRAY true);

-- rivers: the larger ones (Strahler order ≥ 4), line width from mean flow
COPY (
  SELECT stream_order, round(mean_flow_m3s, 1) AS mean_flow_m3s,
         ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.004))::JSON AS geometry
  FROM embalses.ref.rivers
  WHERE stream_order >= 4
) TO 'site/snapshot/rivers.json' (FORMAT json, ARRAY true);

-- rain on the H3 grid, one row per cell with each window as a column
COPY (
  SELECT h3_cell, any_value(g.basin_id) AS basin_id,
         max(rain_mm) FILTER (WHERE time_window = '1h')  AS rain_1h,
         max(rain_mm) FILTER (WHERE time_window = '6h')  AS rain_6h,
         max(rain_mm) FILTER (WHERE time_window = '12h') AS rain_12h,
         max(rain_mm) FILTER (WHERE time_window = '24h') AS rain_24h,
         max(as_of) AS as_of
  FROM embalses."now".rain_grid JOIN embalses.ref.grid_cells g USING (h3_cell)
  GROUP BY 1
  HAVING max(rain_mm) >= 0.2
) TO 'site/snapshot/rain_grid.json' (FORMAT json, ARRAY true);

-- reservoirs: where, how full, how it compares, how much rain fell upstream
COPY (
  SELECT r.reservoir_id, r.reservoir_name, r.basin_id, b.basin_name, r.province, r.region, r.river_name,
         round(ST_X(r.dam_location), 4) AS lon, round(ST_Y(r.dam_location), 4) AS lat,
         s.capacity_hm3, round(s.stored_volume_hm3, 1) AS stored_hm3, round(s.fill_pct, 1) AS fill_pct,
         s.fill_pct_same_week_last_year AS fill_last_year, s.fill_pct_10y_average AS fill_10y,
         s.change_6h_hm3, s.change_24h_hm3, s.weekly_change_hm3, s.change_since_bulletin_hm3, s.data_source, s.latest_reading_at, s.data_age_minutes,
         round(r.catchment_area_km2) AS catchment_km2, r.quality_flags,
         round(max(u.areal_rain_mm) FILTER (WHERE u.time_window = '12h'), 1)   AS upstream_rain_12h_mm,
         round(max(u.rain_volume_hm3) FILTER (WHERE u.time_window = '12h'), 1) AS upstream_rain_12h_hm3,
         round(max(u.areal_rain_mm) FILTER (WHERE u.time_window = '24h'), 1)   AS upstream_rain_24h_mm,
         round(max(u.rain_volume_hm3) FILTER (WHERE u.time_window = '24h'), 1) AS upstream_rain_24h_hm3
  FROM embalses.ref.reservoirs r
  JOIN embalses."now".reservoir_status s USING (reservoir_id)
  LEFT JOIN embalses.ref.basins b USING (basin_id)
  LEFT JOIN embalses."now".upstream_rain u USING (reservoir_id)
  GROUP BY ALL
) TO 'site/snapshot/reservoirs.json' (FORMAT json, ARRAY true);

-- basins in numbers
COPY (
  SELECT b.basin_id, b.basin_name, s.stored_volume_hm3, s.capacity_hm3, s.fill_pct,
         s.fill_pct_same_week_last_year AS fill_last_year, s.fill_pct_10y_average AS fill_10y,
         s.weekly_change_hm3, s.change_24h_hm3, s.areal_rain_24h_mm, s.reservoirs_live, s.reservoirs_total
  FROM embalses."now".basin_summary s JOIN embalses.ref.basins b USING (basin_id)
  ORDER BY s.capacity_hm3 DESC
) TO 'site/snapshot/basin_summary.json' (FORMAT json, ARRAY true);

-- the wettest gauges
COPY (
  SELECT st.station_id, s.station_name, s.network, b.basin_name,
         round(ST_X(s.location), 4) AS lon, round(ST_Y(s.location), 4) AS lat,
         st.rain_1h_mm, st.rain_6h_mm, st.rain_12h_mm, st.rain_24h_mm, st.rain_hydro_year_mm,
         st.rain_same_period_last_year_mm, st.air_temperature_c, st.latest_observation_at
  FROM embalses."now".station_status st
  JOIN embalses.ref.stations s USING (station_id)
  LEFT JOIN embalses.ref.basins b USING (basin_id)
  WHERE st.rain_12h_mm IS NOT NULL
  ORDER BY st.rain_12h_mm DESC
  LIMIT 60
) TO 'site/snapshot/wettest_stations.json' (FORMAT json, ARRAY true);

-- the national picture since 1988 (weekly bulletin)
COPY (
  SELECT w.bulletin_date, round(sum(w.stored_volume_hm3)) AS stored_hm3, round(sum(w.capacity_hm3)) AS capacity_hm3,
         round(100 * sum(w.stored_volume_hm3) / sum(w.capacity_hm3), 1) AS fill_pct
  FROM embalses.obs.reservoir_weekly w
  WHERE w.fill_pct IS NULL OR w.fill_pct <= 110
  GROUP BY 1 HAVING count(*) > 200 ORDER BY 1
) TO 'site/snapshot/national_weekly.json' (FORMAT json, ARRAY true);

-- weekly totals per basin, province and region since 2016, for the year chart of a selected area
COPY (
  WITH w AS (SELECT * FROM embalses.obs.reservoir_weekly WHERE bulletin_date >= DATE '2015-12-01' AND (fill_pct IS NULL OR fill_pct <= 110))
  SELECT 'b' AS t, b.basin_name AS k, w.bulletin_date AS d, round(sum(w.stored_volume_hm3)) AS s, round(sum(w.capacity_hm3)) AS c
  FROM w JOIN embalses.ref.reservoirs r USING (reservoir_id) JOIN embalses.ref.basins b USING (basin_id) GROUP BY ALL
  UNION ALL
  SELECT 'p', r.province, w.bulletin_date, round(sum(w.stored_volume_hm3)), round(sum(w.capacity_hm3))
  FROM w JOIN embalses.ref.reservoirs r USING (reservoir_id) WHERE r.province IS NOT NULL GROUP BY ALL
  UNION ALL
  SELECT 'c', r.region, w.bulletin_date, round(sum(w.stored_volume_hm3)), round(sum(w.capacity_hm3))
  FROM w JOIN embalses.ref.reservoirs r USING (reservoir_id) WHERE r.region IS NOT NULL GROUP BY ALL
  ORDER BY 1, 2, 3
) TO 'site/snapshot/scope_weekly.json' (FORMAT json, ARRAY true);
