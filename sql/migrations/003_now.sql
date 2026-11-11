-- Derived tables, rebuilt hourly by the derived sinks in sql/now/ (format version 2: replace mode needs it).
-- Migration for the embalses catalog. Proposed `lhbox migrate` format (tablemere PLAN 21): plain DuckDB DDL,
-- applied once in file order; `-- lhbox:` lines carry what DuckDB DDL cannot express (format version, partitioning).
-- Generated from the deployed catalog on 2026-11-11.

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".rain_grid (
  h3_cell VARCHAR,
  time_window VARCHAR,
  as_of TIMESTAMPTZ,
  rain_mm DOUBLE,
  stations_used INTEGER,
  nearest_station_km DOUBLE
);
COMMENT ON TABLE embalses."now".rain_grid IS 'Rain over the last 1, 6, 12, 24 and 72 hours on the H3 grid, interpolated from every gauge within 40 km (inverse-distance weighting, power 2, 1 km smoothing). A gauge counts in a window when it reported at least 75% of it. Rebuilt hourly inside LakehouseBox by sql/now/rain_grid.sql.';
COMMENT ON COLUMN embalses."now".rain_grid.h3_cell IS 'Grid cell (ref.grid_cells).';
COMMENT ON COLUMN embalses."now".rain_grid.time_window IS '1h, 6h, 12h, 24h or 72h, ending at as_of.';
COMMENT ON COLUMN embalses."now".rain_grid.as_of IS 'End of the window: the latest hour at least half the gauges have reported (UTC).';
COMMENT ON COLUMN embalses."now".rain_grid.rain_mm IS 'Interpolated rain depth, mm.';
COMMENT ON COLUMN embalses."now".rain_grid.stations_used IS 'Gauges within 40 km that contributed.';
COMMENT ON COLUMN embalses."now".rain_grid.nearest_station_km IS 'Distance to the nearest contributing gauge, km. Large values mean low confidence.';

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".upstream_rain (
  reservoir_id INTEGER,
  time_window VARCHAR,
  as_of TIMESTAMPTZ,
  areal_rain_mm DOUBLE,
  max_station_rain_mm DOUBLE,
  rain_volume_hm3 DOUBLE,
  upstream_area_km2 DOUBLE,
  area_covered_pct DOUBLE,
  stations_reporting INTEGER
);
COMMENT ON TABLE embalses."now".upstream_rain IS 'Rain over all the land that drains into each reservoir, per window: the gridded rain averaged over the reservoir''s upstream catchment units (ref.reservoir_catchments), also expressed as a volume so it compares with the reservoir''s change. Rebuilt hourly inside LakehouseBox by sql/now/upstream_rain.sql.';
COMMENT ON COLUMN embalses."now".upstream_rain.reservoir_id IS 'Reservoir (ref.reservoirs).';
COMMENT ON COLUMN embalses."now".upstream_rain.time_window IS '1h, 6h, 12h, 24h or 72h.';
COMMENT ON COLUMN embalses."now".upstream_rain.as_of IS 'End of the window (UTC).';
COMMENT ON COLUMN embalses."now".upstream_rain.areal_rain_mm IS 'Average rain depth over the upstream area, mm.';
COMMENT ON COLUMN embalses."now".upstream_rain.max_station_rain_mm IS 'Highest single gauge inside the upstream area, mm.';
COMMENT ON COLUMN embalses."now".upstream_rain.rain_volume_hm3 IS 'areal_rain_mm × upstream area ÷ 1000: water that fell, hm³. Not all of it reaches the reservoir.';
COMMENT ON COLUMN embalses."now".upstream_rain.upstream_area_km2 IS 'Upstream area the average is taken over, km².';
COMMENT ON COLUMN embalses."now".upstream_rain.area_covered_pct IS 'Share of the upstream area with an interpolated value (gauges within 40 km), %.';
COMMENT ON COLUMN embalses."now".upstream_rain.stations_reporting IS 'Gauges inside the upstream area that reported in the window.';

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".reservoir_status (
  reservoir_id INTEGER,
  as_of TIMESTAMPTZ,
  latest_reading_at TIMESTAMPTZ,
  data_source VARCHAR,
  stored_volume_hm3 DOUBLE,
  capacity_hm3 DOUBLE,
  fill_pct DOUBLE,
  change_6h_hm3 DOUBLE,
  change_24h_hm3 DOUBLE,
  change_72h_hm3 DOUBLE,
  change_since_bulletin_hm3 DOUBLE,
  weekly_change_hm3 DOUBLE,
  inflow_m3s DOUBLE,
  outflow_m3s DOUBLE,
  upstream_rain_24h_mm DOUBLE,
  upstream_rain_volume_24h_hm3 DOUBLE,
  upstream_rain_72h_mm DOUBLE,
  fill_pct_same_week_last_year DOUBLE,
  fill_pct_10y_average DOUBLE,
  data_age_minutes INTEGER
);
COMMENT ON TABLE embalses."now".reservoir_status IS 'One row per bulletin reservoir with its latest state, recent change, the rain upstream and how it compares with the same week last year and the 10-year average. The main table the map draws. Live SAIH fields fill in as obs.reservoir_readings is ingested; until then the source is the weekly bulletin. Rebuilt hourly inside LakehouseBox by sql/now/reservoir_status.sql.';
COMMENT ON COLUMN embalses."now".reservoir_status.reservoir_id IS 'Reservoir (ref.reservoirs).';
COMMENT ON COLUMN embalses."now".reservoir_status.as_of IS 'When this row was computed (UTC).';
COMMENT ON COLUMN embalses."now".reservoir_status.latest_reading_at IS 'Time of the newest value used (UTC).';
COMMENT ON COLUMN embalses."now".reservoir_status.data_source IS 'saih-<basin> for a live reading, or miteco-weekly for the bulletin.';
COMMENT ON COLUMN embalses."now".reservoir_status.stored_volume_hm3 IS 'Latest stored volume, hm³.';
COMMENT ON COLUMN embalses."now".reservoir_status.capacity_hm3 IS 'Capacity, hm³.';
COMMENT ON COLUMN embalses."now".reservoir_status.fill_pct IS 'Latest fill level, %.';
COMMENT ON COLUMN embalses."now".reservoir_status.change_6h_hm3 IS 'Change over 6 hours, hm³ (live stations only).';
COMMENT ON COLUMN embalses."now".reservoir_status.change_24h_hm3 IS 'Change over 24 hours, hm³ (live stations only).';
COMMENT ON COLUMN embalses."now".reservoir_status.change_72h_hm3 IS 'Change over 72 hours, hm³ (live stations only).';
COMMENT ON COLUMN embalses."now".reservoir_status.change_since_bulletin_hm3 IS 'Change since the last weekly bulletin, hm³ (live stations only).';
COMMENT ON COLUMN embalses."now".reservoir_status.weekly_change_hm3 IS 'Change in the last weekly bulletin, hm³.';
COMMENT ON COLUMN embalses."now".reservoir_status.inflow_m3s IS 'Latest inflow, m³/s, where published.';
COMMENT ON COLUMN embalses."now".reservoir_status.outflow_m3s IS 'Latest release, m³/s, where published.';
COMMENT ON COLUMN embalses."now".reservoir_status.upstream_rain_24h_mm IS 'From now.upstream_rain.';
COMMENT ON COLUMN embalses."now".reservoir_status.upstream_rain_volume_24h_hm3 IS 'From now.upstream_rain.';
COMMENT ON COLUMN embalses."now".reservoir_status.upstream_rain_72h_mm IS 'From now.upstream_rain.';
COMMENT ON COLUMN embalses."now".reservoir_status.fill_pct_same_week_last_year IS 'Fill in the bulletin closest to the same date last year, %.';
COMMENT ON COLUMN embalses."now".reservoir_status.fill_pct_10y_average IS 'Average fill in the same week over the last 10 years, %.';
COMMENT ON COLUMN embalses."now".reservoir_status.data_age_minutes IS 'Minutes since latest_reading_at.';

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".basin_summary (
  basin_id VARCHAR,
  as_of TIMESTAMPTZ,
  stored_volume_hm3 DOUBLE,
  capacity_hm3 DOUBLE,
  fill_pct DOUBLE,
  weekly_change_hm3 DOUBLE,
  change_24h_hm3 DOUBLE,
  fill_pct_same_week_last_year DOUBLE,
  fill_pct_10y_average DOUBLE,
  areal_rain_24h_mm DOUBLE,
  reservoirs_live INTEGER,
  reservoirs_total INTEGER
);
COMMENT ON TABLE embalses."now".basin_summary IS 'Totals per river basin district for headlines: stored water vs capacity, last year and the 10-year average, and rain over the district. Rebuilt hourly inside LakehouseBox by sql/now/basin_summary.sql.';
COMMENT ON COLUMN embalses."now".basin_summary.basin_id IS 'District (ref.basins).';
COMMENT ON COLUMN embalses."now".basin_summary.as_of IS 'When this row was computed (UTC).';
COMMENT ON COLUMN embalses."now".basin_summary.stored_volume_hm3 IS 'Sum over its bulletin reservoirs, hm³.';
COMMENT ON COLUMN embalses."now".basin_summary.capacity_hm3 IS 'Sum of capacities, hm³.';
COMMENT ON COLUMN embalses."now".basin_summary.fill_pct IS 'Stored ÷ capacity, %.';
COMMENT ON COLUMN embalses."now".basin_summary.weekly_change_hm3 IS 'Change in the last weekly bulletin, hm³.';
COMMENT ON COLUMN embalses."now".basin_summary.change_24h_hm3 IS 'Change over 24 hours from live stations, hm³.';
COMMENT ON COLUMN embalses."now".basin_summary.fill_pct_same_week_last_year IS 'District fill in the same week last year, %.';
COMMENT ON COLUMN embalses."now".basin_summary.fill_pct_10y_average IS 'Average district fill in the same week over 10 years, %.';
COMMENT ON COLUMN embalses."now".basin_summary.areal_rain_24h_mm IS 'Average interpolated rain over the district in 24 hours, mm.';
COMMENT ON COLUMN embalses."now".basin_summary.reservoirs_live IS 'Reservoirs with a live reading under 3 hours old.';
COMMENT ON COLUMN embalses."now".basin_summary.reservoirs_total IS 'Bulletin reservoirs in the district.';

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".station_status (
  station_id VARCHAR,
  as_of TIMESTAMPTZ,
  latest_observation_at TIMESTAMPTZ,
  air_temperature_c DOUBLE,
  relative_humidity_pct DOUBLE,
  rain_1h_mm DOUBLE,
  rain_6h_mm DOUBLE,
  rain_12h_mm DOUBLE,
  rain_24h_mm DOUBLE,
  rain_hydro_year_mm DOUBLE,
  hydro_year_daily_through DATE,
  rain_same_period_last_year_mm DOUBLE,
  rain_last_hydro_year_total_mm DOUBLE,
  rain_two_years_ago_total_mm DOUBLE,
  data_age_minutes INTEGER
);
COMMENT ON TABLE embalses."now".station_status IS 'What a station page shows: latest weather, recent rain, and rain since 1 October compared with the previous two hydrological years. Rebuilt hourly inside LakehouseBox by sql/now/station_status.sql.';
COMMENT ON COLUMN embalses."now".station_status.station_id IS 'Station (ref.stations).';
COMMENT ON COLUMN embalses."now".station_status.as_of IS 'End of the rain windows (UTC).';
COMMENT ON COLUMN embalses."now".station_status.latest_observation_at IS 'Newest weather observation (UTC).';
COMMENT ON COLUMN embalses."now".station_status.air_temperature_c IS 'Latest temperature, °C.';
COMMENT ON COLUMN embalses."now".station_status.relative_humidity_pct IS 'Latest humidity, %.';
COMMENT ON COLUMN embalses."now".station_status.rain_1h_mm IS 'Rain in the last hour, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_6h_mm IS 'Rain in the last 6 hours, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_12h_mm IS 'Rain in the last 12 hours, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_24h_mm IS 'Rain in the last 24 hours, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_hydro_year_mm IS 'Rain since 1 October (daily values, then hourly after the last daily value), mm.';
COMMENT ON COLUMN embalses."now".station_status.hydro_year_daily_through IS 'Last day covered by AEMET''s daily values (they run ~4 days behind).';
COMMENT ON COLUMN embalses."now".station_status.rain_same_period_last_year_mm IS 'Rain from 1 October to the same date last year, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_last_hydro_year_total_mm IS 'Total of the previous October–September year, mm.';
COMMENT ON COLUMN embalses."now".station_status.rain_two_years_ago_total_mm IS 'Total of the October–September year before that, mm.';
COMMENT ON COLUMN embalses."now".station_status.data_age_minutes IS 'Minutes since latest_observation_at.';
