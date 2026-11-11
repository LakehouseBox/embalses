-- Observation tables: append-only time series, partitioned by time.
-- Migration for the embalses catalog. Proposed `lhbox migrate` format (tablemere PLAN 21): plain DuckDB DDL,
-- applied once in file order; `-- lhbox:` lines carry what DuckDB DDL cannot express (format version, partitioning).
-- Generated from the deployed catalog on 2026-11-11.

-- lhbox: format-version=3 partition=day(period_end_at)
CREATE TABLE IF NOT EXISTS embalses.obs.precipitation (
  station_id VARCHAR NOT NULL,
  period_start_at TIMESTAMPTZ NOT NULL,
  period_end_at TIMESTAMPTZ NOT NULL,
  period_minutes INTEGER NOT NULL,
  precipitation_mm DOUBLE,
  is_provisional BOOLEAN,
  source VARCHAR NOT NULL,
  __ingest_ts TIMESTAMPTZ
);
COMMENT ON TABLE embalses.obs.precipitation IS 'Rain measured at each gauge, always as the amount over an explicit interval, so 10-, 15- and 60-minute networks can be added up. Append-only, partitioned by day of period_end_at. Today: AEMET hourly observations (~830 stations) since 2026-11-10 22:00 UTC; SAIH and SiAR gauges to follow. Real-time values are provisional (not validated by the publisher).';
COMMENT ON COLUMN embalses.obs.precipitation.station_id IS 'Gauge (ref.stations).';
COMMENT ON COLUMN embalses.obs.precipitation.period_start_at IS 'Start of the interval the rain fell in (UTC).';
COMMENT ON COLUMN embalses.obs.precipitation.period_end_at IS 'End of the interval (UTC). AEMET''s fint.';
COMMENT ON COLUMN embalses.obs.precipitation.period_minutes IS 'Interval length in minutes (60 for AEMET).';
COMMENT ON COLUMN embalses.obs.precipitation.precipitation_mm IS 'Rain in the interval, mm (1 mm = 1 litre per m²).';
COMMENT ON COLUMN embalses.obs.precipitation.is_provisional IS 'True for real-time values not yet validated by the publisher.';
COMMENT ON COLUMN embalses.obs.precipitation.source IS 'Key of the source (aemet-opendata, …).';
COMMENT ON COLUMN embalses.obs.precipitation.__ingest_ts IS 'when the sink received the batch (RFC 3339, the intake''s clock)';

-- lhbox: format-version=3 partition=day(observed_at)
CREATE TABLE IF NOT EXISTS embalses.obs.weather (
  station_id VARCHAR NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  air_temperature_c DOUBLE,
  air_temperature_min_c DOUBLE,
  air_temperature_max_c DOUBLE,
  relative_humidity_pct DOUBLE,
  dew_point_c DOUBLE,
  wind_speed_ms DOUBLE,
  wind_gust_ms DOUBLE,
  wind_direction_deg DOUBLE,
  pressure_hpa DOUBLE,
  is_provisional BOOLEAN,
  source VARCHAR NOT NULL,
  __ingest_ts TIMESTAMPTZ
);
COMMENT ON TABLE embalses.obs.weather IS 'Hourly temperature, humidity, wind and pressure at weather stations. Append-only, partitioned by day of observed_at. Today: AEMET hourly observations (~850 stations) since 2026-11-10 22:00 UTC. Provisional real-time values.';
COMMENT ON COLUMN embalses.obs.weather.station_id IS 'Weather station (ref.stations).';
COMMENT ON COLUMN embalses.obs.weather.observed_at IS 'End of the hour the values describe (UTC).';
COMMENT ON COLUMN embalses.obs.weather.air_temperature_c IS 'Air temperature at the observation time, °C.';
COMMENT ON COLUMN embalses.obs.weather.air_temperature_min_c IS 'Lowest temperature in the previous hour, °C.';
COMMENT ON COLUMN embalses.obs.weather.air_temperature_max_c IS 'Highest temperature in the previous hour, °C.';
COMMENT ON COLUMN embalses.obs.weather.relative_humidity_pct IS 'Relative humidity, %.';
COMMENT ON COLUMN embalses.obs.weather.dew_point_c IS 'Dew point, °C.';
COMMENT ON COLUMN embalses.obs.weather.wind_speed_ms IS 'Mean wind speed, m/s.';
COMMENT ON COLUMN embalses.obs.weather.wind_gust_ms IS 'Strongest gust in the previous hour, m/s.';
COMMENT ON COLUMN embalses.obs.weather.wind_direction_deg IS 'Direction the wind comes from, degrees (0 = north).';
COMMENT ON COLUMN embalses.obs.weather.pressure_hpa IS 'Station-level air pressure, hPa.';
COMMENT ON COLUMN embalses.obs.weather.is_provisional IS 'True for real-time values not yet validated.';
COMMENT ON COLUMN embalses.obs.weather.source IS 'Key of the source (aemet-opendata).';
COMMENT ON COLUMN embalses.obs.weather.__ingest_ts IS 'when the sink received the batch (RFC 3339, the intake''s clock)';

-- lhbox: format-version=3 partition=year(bulletin_date)
CREATE TABLE IF NOT EXISTS embalses.obs.reservoir_weekly (
  reservoir_id INTEGER NOT NULL,
  bulletin_date DATE NOT NULL,
  bulletin_year INTEGER,
  bulletin_number INTEGER,
  stored_volume_hm3 DOUBLE,
  capacity_hm3 DOUBLE,
  fill_pct DOUBLE,
  weekly_change_hm3 DOUBLE,
  stored_energy_gwh DOUBLE,
  energy_capacity_gwh DOUBLE,
  source VARCHAR
);
COMMENT ON TABLE embalses.obs.reservoir_weekly IS 'MITECO weekly reservoir bulletin (Boletin Hidrologico), one row per reservoir and bulletin, 1988-01-05 onward. Peninsular reservoirs > 5 hm3. Source: MITECO ArcGIS FeatureServer Embalses_Total (backfill by ingest/miteco_reservoir_weekly.py). Bulletins are Tuesdays.';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.reservoir_id IS 'MITECO EMBALSE_ID, stable reservoir id (note: Pajares/Ebro appears as 353 in 2003 and 362 from 2006)';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.bulletin_date IS 'Bulletin date (a Tuesday), from fecha at 00:00 UTC';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.bulletin_year IS 'boletin_anyo, calendar year of the bulletin';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.bulletin_number IS 'boletin_num, bulletin number within the year';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.stored_volume_hm3 IS 'agua_actual: water stored on the bulletin date, hm3';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.capacity_hm3 IS 'agua_total: capacity at normal maximum level, hm3 (0 for some rows)';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.fill_pct IS 'stored/capacity*100, 2 dp; null when capacity is 0 or null. Source errors make a few rows exceed 100 (max 700)';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.weekly_change_hm3 IS 'stored_volume_hm3 minus the same reservoir''s previous bulletin; null for its first bulletin (a few gaps span more than a week)';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.stored_energy_gwh IS 'energia_actual: theoretical hydroelectric energy stored, GWh (null/0 for non-hydro reservoirs)';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.energy_capacity_gwh IS 'energia_total: hydroelectric energy at capacity, GWh';
COMMENT ON COLUMN embalses.obs.reservoir_weekly.source IS '''miteco-arcgis''';

-- lhbox: format-version=3 partition=year(observation_date)
CREATE TABLE IF NOT EXISTS embalses.obs.daily_weather (
  station_id VARCHAR NOT NULL,
  observation_date DATE NOT NULL,
  precipitation_mm DOUBLE,
  air_temperature_mean_c DOUBLE,
  air_temperature_min_c DOUBLE,
  air_temperature_max_c DOUBLE,
  relative_humidity_mean_pct DOUBLE,
  hydrological_year INTEGER,
  is_complete BOOLEAN,
  source VARCHAR
);
COMMENT ON TABLE embalses.obs.daily_weather IS 'AEMET daily climatological values, one row per station and day, all stations, 2023-10-01 onward (AEMET publishes ~4 days late). Source: AEMET OpenData valores/climatologicos/diarios (backfill by ingest/aemet_daily.py).';
COMMENT ON COLUMN embalses.obs.daily_weather.station_id IS '''aemet:'' || AEMET indicativo (same ids as obs.weather / obs.precipitation)';
COMMENT ON COLUMN embalses.obs.daily_weather.observation_date IS 'AEMET fecha (climatological day)';
COMMENT ON COLUMN embalses.obs.daily_weather.precipitation_mm IS 'prec: precipitation 07 to 07 UTC, mm. ''Ip'' (<0.1 mm) -> 0.0; ''Acum'' or missing -> null';
COMMENT ON COLUMN embalses.obs.daily_weather.air_temperature_mean_c IS 'tmed, daily mean air temperature, degC';
COMMENT ON COLUMN embalses.obs.daily_weather.air_temperature_min_c IS 'tmin, daily minimum air temperature, degC';
COMMENT ON COLUMN embalses.obs.daily_weather.air_temperature_max_c IS 'tmax, daily maximum air temperature, degC';
COMMENT ON COLUMN embalses.obs.daily_weather.relative_humidity_mean_pct IS 'hrMedia, daily mean relative humidity, %';
COMMENT ON COLUMN embalses.obs.daily_weather.hydrological_year IS 'Year of the 1 October the date falls on or after (2025-10-01..2026-09-30 -> 2025)';
COMMENT ON COLUMN embalses.obs.daily_weather.is_complete IS 'false when prec is missing, ''Acum'' or non-numeric';
COMMENT ON COLUMN embalses.obs.daily_weather.source IS '''aemet-climatological''';

-- lhbox: format-version=3 partition=day(observed_at)
CREATE TABLE IF NOT EXISTS embalses.obs.reservoir_readings (
  station_id VARCHAR NOT NULL,
  reservoir_id INTEGER,
  observed_at TIMESTAMPTZ NOT NULL,
  water_level_masl DOUBLE,
  stored_volume_hm3 DOUBLE,
  fill_pct DOUBLE,
  inflow_m3s DOUBLE,
  outflow_m3s DOUBLE,
  is_provisional BOOLEAN,
  source VARCHAR NOT NULL
);
COMMENT ON TABLE embalses.obs.reservoir_readings IS 'Live reservoir level and storage from each basin''s SAIH network, plus inflow and outflow where published. Append-only, partitioned by day of observed_at. One row per station and observation time; sinks deliver at least once, so de-duplicate on (station_id, observed_at). Provisional real-time values.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.station_id IS 'Reservoir station (ref.stations).';
COMMENT ON COLUMN embalses.obs.reservoir_readings.reservoir_id IS 'Reservoir (ref.reservoirs), copied from ref.stations for easy filtering.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.observed_at IS 'Time of the reading (UTC).';
COMMENT ON COLUMN embalses.obs.reservoir_readings.water_level_masl IS 'Water surface height, metres above sea level.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.stored_volume_hm3 IS 'Water stored, hm³.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.fill_pct IS 'Stored volume as a share of capacity, %, as published by the source.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.inflow_m3s IS 'Water entering, m³/s, where published.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.outflow_m3s IS 'Water released through the dam, m³/s, where published.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.is_provisional IS 'True for real-time values not yet validated.';
COMMENT ON COLUMN embalses.obs.reservoir_readings.source IS 'Key of the source (saih-ebro, saih-guadalquivir, …).';

-- lhbox: format-version=3 partition=day(observed_at)
CREATE TABLE IF NOT EXISTS embalses.obs.river_flow (
  station_id VARCHAR NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  flow_m3s DOUBLE,
  water_level_m DOUBLE,
  is_provisional BOOLEAN,
  source VARCHAR NOT NULL
);
COMMENT ON TABLE embalses.obs.river_flow IS 'Flow and water depth at SAIH river gauges. A storm shows here as rising flow hours before reservoir levels move. Append-only, partitioned by day of observed_at; de-duplicate on (station_id, observed_at). Provisional real-time values.';
COMMENT ON COLUMN embalses.obs.river_flow.station_id IS 'River gauge (ref.stations).';
COMMENT ON COLUMN embalses.obs.river_flow.observed_at IS 'Time of the reading (UTC).';
COMMENT ON COLUMN embalses.obs.river_flow.flow_m3s IS 'Water flowing past the gauge, m³/s.';
COMMENT ON COLUMN embalses.obs.river_flow.water_level_m IS 'Water depth at the gauge, m.';
COMMENT ON COLUMN embalses.obs.river_flow.is_provisional IS 'True for real-time values not yet validated.';
COMMENT ON COLUMN embalses.obs.river_flow.source IS 'Key of the source (saih-ebro, …).';
