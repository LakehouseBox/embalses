-- ref.stations, SAIH Tajo: five reservoir stations that the location rule of build_reference.sql (within 1.5 km of the
-- bulletin dam) left without a reservoir. Matched by hand on 2026-11-17 by name, then checked against the bulletin of
-- 2026-11-10 (SAIH volume against bulletin volume, hm³): San Juan 74.5 / 64 (rising), Finisterre 23.6 / 24,
-- El Castro 3.1 / 3, Castrejón 39.8 / 32 (a regulated weir: 43, 41, 32 in the last bulletins), Atance 17.9 / 18.
-- Atance (E_48) is not in MITECO's SAIH register, so it is added here at the dam.
-- Canal de Isabel II's own reservoirs (Pinilla, Riosequillo, Puentes Viejas, El Villar, Pedrezuela, Navacerrada,
-- La Jarosa) are not on the SAIH Tajo viewer; they stay on the weekly bulletin.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/stations_tajo.sql
INSTALL spatial; LOAD spatial;   -- without it, reading a GEOMETRY('EPSG:4326') column fails with a CRS cast error

UPDATE embalses.ref.stations AS s
SET reservoir_id = v.reservoir_id
FROM (VALUES ('saih-tajo:E_19', 277), ('saih-tajo:E_23', 137), ('saih-tajo:E_24', 88), ('saih-tajo:E_27', 84))
     AS v(station_id, reservoir_id)
WHERE s.station_id = v.station_id;

DELETE FROM embalses.ref.stations WHERE station_id = 'saih-tajo:E_48';
INSERT INTO embalses.ref.stations
  (station_id, network, operator, native_code, station_name, station_type, variables, reservoir_id, basin_id,
   catchment_id, elevation_m, update_interval_minutes, first_seen_at, last_seen_at, location, source)
SELECT 'saih-tajo:E_48', 'saih-tajo', 'Confederación Hidrográfica del Tajo', 'E_48', 'ATANCE', 'reservoir',
       ['fill_pct', 'stored_volume', 'water_level'], r.reservoir_id, r.basin_id, r.catchment_id, NULL, 60, now(), NULL,
       r.dam_location, 'saih-tajo'
FROM embalses.ref.reservoirs r WHERE r.reservoir_id = 360;

SELECT count(*) AS tajo_reservoir_stations FROM embalses.ref.stations WHERE network = 'saih-tajo' AND reservoir_id IS NOT NULL;
