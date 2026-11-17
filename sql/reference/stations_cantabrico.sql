-- ref.stations, SAIH Cantábrico reservoirs: the codes of the basin authority's viewer joined to the bulletin reservoirs.
-- MITECO's SAIH registry (data/raw/arcgis/saih_reservoir_points.geojson, used by build_reference.sql) lists no
-- Cantábrico reservoir, so the codes that sink saih_cantabrico writes (saih-cantabrico:<data-codigo>) never joined
-- ref.stations and the live readings did not reach now.reservoir_status. Matched by hand on 2026-11-17 by name and
-- capacity (viewer "Vol. NMN" against the bulletin's capacity; all within 1 hm³). The station sits at the dam.
-- Not linked: viewer 1070, 1071 (Leurtza), 1079 (Arriarán), 1254, 1255 (Palombera, La Lastra), 1272 (Cordiñanes),
-- 1337, 1340, 1346 (El Furacón, Priañes, Valdemurio), 1355 (La Florida), 1362, 1364 (del Valle): not bulletin reservoirs.
-- Bulletin reservoirs the viewer does not carry: Ibai-Eder (168), Urkulu (322), both Gipuzkoa's, not the CHC's.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_cantabrico.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
CREATE OR REPLACE TEMP TABLE cb_links AS
SELECT * FROM (VALUES
  ('1406', 'Embalse de Salime',            270),
  ('1408', 'Embalse de Doiras',            121),
  ('1409', 'Embalse de Arbón',              26),
  ('1356', 'Embalse de La Barca',           40),
  ('1333', 'Embalse de Tanes',             305),
  ('1334', 'Embalse de Rioseco',           385),
  ('1345', 'Embalse de Alfilorios',         17),
  ('1253', 'Embalse de La Cohilla',        103),
  ('1231', 'Embalse Alsa-Mediajo',         310),
  ('1177', 'Embalse de Ordunte',           217),
  ('1078', 'Embalse de Ibiur',             377),
  ('1108', 'Embalse de Añarbe',             34),
  ('1847', 'Embalse de Endara-San Antón',  272)
) AS t(native_code, station_name, reservoir_id);

DELETE FROM embalses.ref.stations
WHERE station_id IN (SELECT 'saih-cantabrico:' || native_code FROM cb_links);

INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-cantabrico:' || l.native_code, 'saih-cantabrico', 'Confederación Hidrográfica del Cantábrico',
       l.native_code, l.station_name, 'reservoir', ['fill_pct', 'stored_volume', 'water_level'],
       r.reservoir_id, r.basin_id, r.catchment_id, NULL, 15, now(), NULL, r.dam_location, 'saih-cantabrico'
FROM cb_links l JOIN embalses.ref.reservoirs r USING (reservoir_id);

SELECT count(*) AS cantabrico_reservoir_stations
FROM embalses.ref.stations WHERE network = 'saih-cantabrico' AND reservoir_id IS NOT NULL;
