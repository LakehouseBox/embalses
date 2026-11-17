-- ref.stations, ACA: Siurana, which the ACA's open data (dataset vjx7-6kcp, station E18) measures and MITECO's bulletin
-- lists as Ciurana (Ebro district, reservoir 102). Not in MITECO's SAIH register under the ACA, so added here at the dam,
-- keyed by the dataset's code (aca:E18). Checked 2026-11-17: ACA 8.6 hm³, bulletin of 2026-11-10 9 hm³ (capacity 12).
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_aca.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
DELETE FROM embalses.ref.stations WHERE station_id = 'aca:E18';
INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'aca:E18', 'aca', 'Agència Catalana de l''Aigua', 'E18', 'Siurana', 'reservoir',
       ['fill_pct', 'stored_volume', 'water_level'], r.reservoir_id, r.basin_id, r.catchment_id, NULL, 1440, now(), NULL,
       r.dam_location, 'aca'
FROM embalses.ref.reservoirs r WHERE r.reservoir_id = 102;
SELECT station_id, reservoir_id FROM embalses.ref.stations WHERE station_id = 'aca:E18';
