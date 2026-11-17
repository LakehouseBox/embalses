-- ref.stations, SAIH Guadiana: sixteen reservoir stations that sink saih_guadiana reads but that had no reservoir: the
-- location rule of build_reference.sql (within 1.5 km of the bulletin dam) missed them, or MITECO's register lacks them.
-- Matched by hand on 2026-11-17 by the viewer's own name (Visor/estaciones: nombre, municipio), then checked against the
-- bulletin of 2026-11-10 (SAIH volume / bulletin volume, hm³): La Serena 2,617 / 2,622, Cijara 1,157 / 1,135,
-- García de Sola 275 / 264, Torre de Abraham 133 / 132, Villalba 94 / 93, Villar del Rey 94 / 93, Peñarroya 50 / 48,
-- Búrdalo 23 / 22, La Cabezuela 22 / 22, Alcollarín 19 / 19, El Vicario 19 / 18, Hornotejero 13 / 13,
-- Vega del Jabalón 12 / 12, Montijo 12 / 11, Vallehermoso 6 / 6, El Boquerón 3 / 3.
-- Stations already in ref.stations get their reservoir_id; the others are added at the dam.
-- Not linked: Puente Navarro (E1-03), Campos del Paraíso (E1-10), Azud Lavadero (E2-10), Las Muelas (E2-31).
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_guadiana.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error
CREATE OR REPLACE TEMP TABLE gd_links AS
SELECT * FROM (VALUES
  ('E1-01', 'EMBALSE PEÑARROYA',      225),
  ('E1-02', 'EMBALSE VALLEHERMOSO',   240),
  ('E1-06', 'EMBALSE VICARIO',        338),
  ('E1-07', 'EMBALSE LA CABEZUELA',   176),
  ('E1-08', 'EMBALSE VEGA JABALÓN',   334),
  ('E1-09', 'EMBALSE TORRE ABRAHAM',  311),
  ('E2-01', 'EMBALSE CIJARA',         120),
  ('E2-03', 'EMBALSE GARCÍA SOLA',    145),
  ('E2-06', 'EMBALSE LA SERENA',      181),
  ('E2-19', 'EMBALSE DE MONTIJO',     206),
  ('E2-20', 'EMBALSE HORNOTEJERO',    165),
  ('E2-21', 'EL BOQUERÓN',             56),
  ('E2-24', 'EMBALSE VILLAR DEL REY', 345),
  ('E2-32', 'VILLALBA',               399),
  ('E2-33', 'ALCOLLARÍN',             397),
  ('E2-34', 'BÚRDALO',                398)
) AS t(native_code, station_name, reservoir_id);

UPDATE embalses.ref.stations AS s
SET reservoir_id = l.reservoir_id
FROM gd_links l
WHERE s.station_id = 'saih-guadiana:' || l.native_code;

INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-guadiana:' || l.native_code, 'saih-guadiana', 'Confederación Hidrográfica del Guadiana', l.native_code,
       l.station_name, 'reservoir', ['fill_pct', 'stored_volume', 'water_level'], r.reservoir_id, r.basin_id,
       r.catchment_id, NULL, 60, now(), NULL, r.dam_location, 'saih-guadiana'
FROM gd_links l JOIN embalses.ref.reservoirs r USING (reservoir_id)
WHERE NOT EXISTS (SELECT 1 FROM embalses.ref.stations s WHERE s.station_id = 'saih-guadiana:' || l.native_code);

SELECT count(*) AS guadiana_reservoir_stations FROM embalses.ref.stations WHERE network = 'saih-guadiana' AND reservoir_id IS NOT NULL;
