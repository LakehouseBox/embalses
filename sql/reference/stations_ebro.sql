-- ref.stations, SAIH Ebro: eight reservoir stations of the viewer's zone maps that MITECO's SAIH register does not list.
-- Matched by hand on 2026-11-17 by the viewer's name (LR_NOMBRE_CORTO), then checked against the bulletin of 2026-11-10
-- (SAIH volume / bulletin volume, hm³): Lechago 10.6 / 11, Enciso 17.4 / 17, Nagore 2.2 / 2, Belsué 1.3 / 1,
-- Montearagón 23.8 / 24, Puente de Santolea 17.7 / 18, Cañón de Santolea 14.9 / 15; La Loteta publishes a level only.
-- The station sits at the dam. Not linked (not bulletin reservoirs): Albagés, Mularroya, Mairaga, Tabescán, Plandescún.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_ebro.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
CREATE OR REPLACE TEMP TABLE ebro_links AS
SELECT * FROM (VALUES
  ('E087', 'LECHAGO',         389),
  ('E089', 'ENCISO',          390),
  ('E085', 'LA LOTETA',       378),
  ('E104', 'NAGORE',          395),
  ('E042', 'BELSUÉ',          300),
  ('E077', 'MONTEARAGÓN',     391),
  ('E098', 'PUENTE SANTOLEA', 384),
  ('E108', 'CAÑON-SANTOLEA',  400)
) AS t(native_code, station_name, reservoir_id);

DELETE FROM embalses.ref.stations WHERE station_id IN (SELECT 'saih-ebro:' || native_code FROM ebro_links);

INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-ebro:' || l.native_code, 'saih-ebro', 'Confederación Hidrográfica del Ebro', l.native_code, l.station_name,
       'reservoir', ['fill_pct', 'stored_volume', 'water_level'], r.reservoir_id, r.basin_id, r.catchment_id, NULL, 15,
       now(), NULL, r.dam_location, 'saih-ebro'
FROM ebro_links l JOIN embalses.ref.reservoirs r USING (reservoir_id);

SELECT count(*) AS ebro_reservoir_stations FROM embalses.ref.stations WHERE network = 'saih-ebro' AND reservoir_id IS NOT NULL;
