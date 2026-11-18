-- ref.stations, CH Duero open data: the reservoirs of estado_embalses.json (datos.chduero.es), keyed by the CHD's own code
-- (saih-duero:E2001), joined to the bulletin reservoirs. The register's Duero stations (saih-duero:EM001 …) use other
-- codes, so these are new rows at the dam. Matched by hand on 2026-11-17 by name, then checked against the bulletin of
-- 2026-11-10: 29 within a few hm³ (or a plausible rise after 40 mm of rain upstream, e.g. Cuerda del Pozo 123 → 131).
-- Santa Teresa (E2038), Cernadilla (E2031) and Irueña (E2047) were first left out (2026-11-17), because the open data
-- (345 / 51 / 65 hm³) was far above the bulletin of 2026-11-10 (221 / 31 / 51) with little rain measured upstream. That
-- was wrong: the bulletin was a week old and these reservoirs had risen (Santa Teresa +118 hm³ that week). The open data
-- was right, so they were linked on 2026-11-18. Lesson: a gap against the weekly bulletin is not evidence the live
-- reading is wrong; compare live with live, or wait for the next bulletin.
-- Not bulletin reservoirs: Selga de Ordás, Campillo de Buitrago, El Milagro, Riolobos.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_duero.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
CREATE OR REPLACE TEMP TABLE du_links AS
SELECT * FROM (VALUES
  ('E2001', 'Embalse de Cuerda del Pozo',              116),
  ('E2002', 'Embalse de Villalcampo',                  343),
  ('E2003', 'Embalse de Castro',                        87),
  ('E2004', 'Embalse de Saucelle',                     291),
  ('E2005', 'Embalse de Aldeadávila',                   16),
  ('E2010', 'Embalse de Úzquiza',                      324),
  ('E2011', 'Embalse de Arlanzón',                      30),
  ('E2012', 'Embalse de Cervera-Ruesga',                98),
  ('E2013', 'Embalse de La Requejada',                 250),
  ('E2014', 'Embalse de Camporredondo',                 74),
  ('E2015', 'Embalse de Compuerto',                    105),
  ('E2016', 'Embalse de Aguilar de Campoo',              7),
  ('E2026', 'Embalse de Barrios de Luna',               42),
  ('E2027', 'Embalse de Villameca',                    344),
  ('E2029', 'Embalse del Esla',                        257),
  ('E2030', 'Embalse de Porma',                        232),
  ('E2032', 'Embalse de Riaño',                        254),
  ('E2033', 'Embalse de Valparaíso',                   332),
  ('E2034', 'Embalse de Nuestra Señora del Agavanzal',   2),
  ('E2036', 'Embalse de Linares del Arroyo',           185),
  ('E2037', 'Embalse de Burgomillodo',                  64),
  ('E2039', 'Embalse de Águeda',                         5),
  ('E2040', 'Embalse de Las Vencías',                  337),
  ('E2041', 'Embalse de Almendra',                      20),
  ('E2042', 'Embalse del Castro de las Cogotas',        86),
  ('E2043', 'Embalse de El Pontón Alto',               375),
  ('E2031', 'Embalse de Cernadilla',                    96),
  ('E2038', 'Embalse de Santa Teresa',                 286),
  ('E2047', 'Embalse de Irueña',                       402),
  ('E2650', 'Embalse de San José',                     276),
  ('E2652', 'Embalse de Villagonzalo',                 341),
  ('E2653', 'Embalse de Los Rábanos',                  265)
) AS t(native_code, station_name, reservoir_id);

DELETE FROM embalses.ref.stations WHERE station_id IN (SELECT 'saih-duero:' || native_code FROM du_links);

INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-duero:' || l.native_code, 'saih-duero', 'Confederación Hidrográfica del Duero', l.native_code,
       l.station_name, 'reservoir', ['fill_pct', 'flow', 'stored_volume'], r.reservoir_id, r.basin_id, r.catchment_id,
       NULL, 15, now(), NULL, r.dam_location, 'chduero-open-data'
FROM du_links l JOIN embalses.ref.reservoirs r USING (reservoir_id);

SELECT count(*) AS duero_open_data_stations FROM embalses.ref.stations WHERE source = 'chduero-open-data' AND reservoir_id IS NOT NULL;
