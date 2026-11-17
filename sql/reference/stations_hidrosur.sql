-- ref.stations, SAIH Hidrosur (Junta de Andalucía): the reservoirs of the viewer's "Datos de última hora" table, keyed by
-- the sensor code of each row's chart link (saih-hidrosur:003E01), joined to the bulletin reservoirs. Matched by hand
-- on 2026-11-17 by name and capacity; every volume within 3 hm³ of the bulletin of 2026-11-10.
-- MITECO's register names Hidrosur stations by name (saih-hidrosur:EMBALSE DE …), which no feed uses; those rows stay.
-- The bulletin's Guadalhorce-Guadalteba (154) is the sum of two dams: the sink writes it as saih-hidrosur:029L02+030E01.
-- Andévalo and Chanza are filed under the Guadiana district in the bulletin; Hidrosur measures them.
-- Not linked: Cueva de la Mora (375L02), not a bulletin reservoir. Bulletin reservoirs Hidrosur does not list: Odiel, Sancho.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_hidrosur.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
CREATE OR REPLACE TEMP TABLE hs_links AS
SELECT * FROM (VALUES
  ('003E01', 'EMBALSE DE CHARCO REDONDO',        101),
  ('008L02', 'EMBALSE DE GUADARRANQUE',          158),
  ('269L03', 'EMBALSE DE ZAHARA - EL GASTOR',    350),
  ('270E02', 'EMBALSE DE BORNOS',                 58),
  ('271L02', 'EMBALSE ARCOS DE LA FRONTERA',      27),
  ('272L02', 'EMBALSE DE HURONES',               167),
  ('273E02', 'EMBALSE DE GUADALCACÍN',           152),
  ('275E02', 'EMBALSE DE BARBATE',                39),
  ('276L02', 'EMBALSE DE CELEMÍN',                93),
  ('277E02', 'EMBALSE DE ALMODÓVAR',              21),
  ('016E01', 'EMBALSE DE LA CONCEPCIÓN',         106),
  ('019L02', 'EMBALSE DE CASASOLA',              380),
  ('020E01', 'EMBALSE DEL LIMONERO',             184),
  ('029L02+030E01', 'EMBALSES DEL GUADALTEBA Y DEL GUADALHORCE', 154),
  ('031L02', 'EMBALSE CONDE DE GUADALHORCE',     108),
  ('037E01', 'EMBALSE DE LA VIÑUELA',            347),
  ('051L02', 'EMBALSE DE RULES',                 379),
  ('064E01', 'EMBALSE DE BEZNAR',                 68),
  ('058E01', 'EMBALSE DE BENINAR',                51),
  ('084E01', 'EMBALSE CUEVAS DEL ALMANZORA',     118),
  ('371L02', 'EMBALSE DE CHANZA',                100),
  ('373E02', 'EMBALSE DE PIEDRAS',               229),
  ('374E02', 'EMBALSE DE LOS MACHOS',            189),
  ('376L02', 'EMBALSE DE SOTIEL - OLIVARGAS',    216),
  ('377L03', 'EMBALSE DE CORUMBEL BAJO',         113),
  ('379L03', 'EMBALSE DE JARRAMA',               358),
  ('380L02', 'EMBALSE DE ANDÉVALO',              355)
) AS t(native_code, station_name, reservoir_id);

DELETE FROM embalses.ref.stations WHERE station_id IN (SELECT 'saih-hidrosur:' || native_code FROM hs_links);

INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-hidrosur:' || l.native_code, 'saih-hidrosur', 'Junta de Andalucía (Red Hidrosur)', l.native_code,
       l.station_name, 'reservoir', ['fill_pct', 'stored_volume'], r.reservoir_id, r.basin_id, r.catchment_id, NULL, 60,
       now(), NULL, r.dam_location, 'saih-hidrosur'
FROM hs_links l JOIN embalses.ref.reservoirs r USING (reservoir_id);

SELECT count(*) AS hidrosur_reservoir_stations
FROM embalses.ref.stations WHERE network = 'saih-hidrosur' AND source = 'saih-hidrosur' AND reservoir_id IS NOT NULL;
