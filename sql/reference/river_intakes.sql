-- ref.river_intake_reservoirs: the bulletin reservoirs upstream of each river intake, for the municipalities whose supply
-- has no reservoir behind it otherwise. An ESTIMATE: the basin plans say "toma en el río Mero" and stop there.
-- Method: reservoirs on a river of the same name (ref.reservoirs.river_name) in the same basin district; follow the river
-- network down from each dam (ref.rivers.downstream_segment_id, HydroRIVERS); keep it when that water passes within 8 km
-- of the municipality's point (ref.municipalities). Known limits: a reservoir on a tributary is missed (Logroño gets the
-- Ebro's, not the Iregua's); a town fed by a pipe from a river far away is missed (Albacete, 27 km from the Júcar).
-- Leaves out the Balearic and Canary Islands: the page has no river network or search there yet.
-- Reads now.municipality_path to skip municipalities that already have a reservoir (so run it after water_supply.sql
-- and the path sink). Run from the repository root:
--   lhbox duckdb --catalog embalses -- -f sql/reference/river_intakes.sql
-- then: lhbox sink run now_municipality_path --wait && lhbox sink run now_municipality_water --wait
INSTALL spatial; LOAD spatial;
-- a river's name without the word for river or its article: "río de la Hoz Seca" → "hoz seca"
CREATE OR REPLACE MACRO river_key(s) AS trim(regexp_replace(strip_accents(lower(coalesce(s, ''))),
  '^(rio|riu|arroyo|riera|regato|rambla|barranco|rego|ribeira|garganta)\s+((de|del|de la|de los|de las|d'')\s+)?', ''));
-- every river intake of a municipality's own supply units (not of the networks it draws on: those serve many towns)
CREATE OR REPLACE TEMP TABLE intakes AS
SELECT DISTINCT ms.municipality_code, ms.supply_unit_id, s.source_name, river_key(s.source_name) AS rk, u.basin_id,
       m.longitude AS lon, m.latitude AS lat
FROM embalses.ref.municipality_supply ms
JOIN embalses.ref.supply_units u USING (supply_unit_id)
JOIN embalses.ref.supply_sources s
  ON s.supply_unit_id = ms.supply_unit_id AND (s.municipality_code IS NULL OR s.municipality_code = ms.municipality_code)
JOIN embalses.ref.municipalities m ON m.municipality_code = ms.municipality_code
WHERE s.source_type = 'river' AND s.source_name IS NOT NULL AND river_key(s.source_name) <> ''
  AND m.province_code NOT IN ('07', '35', '38');   -- the islands: no river network on the page yet
-- bulletin reservoirs on a river of the same name, in the same basin district
CREATE OR REPLACE TEMP TABLE candidates AS
SELECT DISTINCT i.rk, i.basin_id, r.reservoir_id, r.river_segment_id
FROM (SELECT DISTINCT rk, basin_id FROM intakes) i
JOIN embalses.ref.reservoirs r ON river_key(r.river_name) = i.rk AND r.basin_id = i.basin_id
WHERE r.river_segment_id IS NOT NULL;
-- from each dam down the river to the sea
CREATE OR REPLACE TEMP TABLE downstream AS
WITH RECURSIVE w(reservoir_id, seg, steps) AS (
  SELECT DISTINCT reservoir_id, river_segment_id, 0 FROM candidates
  UNION ALL
  SELECT w.reservoir_id, r.downstream_segment_id, w.steps + 1
  FROM w JOIN embalses.ref.rivers r ON r.river_segment_id = w.seg
  WHERE r.downstream_segment_id IS NOT NULL AND r.downstream_segment_id <> 0 AND w.steps < 4000)
SELECT * FROM w;
-- how close that water passes to the municipality (its point in ref.municipalities)
CREATE OR REPLACE TEMP TABLE near AS
SELECT i.municipality_code, i.supply_unit_id, i.source_name, c.reservoir_id,
       round(min(ST_Distance(ST_Transform(rv.geometry, 'EPSG:4326', 'EPSG:3035', always_xy := true),
                             ST_Transform(ST_Point(i.lon, i.lat), 'EPSG:4326', 'EPSG:3035', always_xy := true))) / 1000, 1) AS distance_km
FROM intakes i JOIN candidates c ON c.rk = i.rk AND c.basin_id = i.basin_id
JOIN downstream d ON d.reservoir_id = c.reservoir_id
JOIN embalses.ref.rivers rv ON rv.river_segment_id = d.seg
GROUP BY ALL;

DELETE FROM embalses.ref.river_intake_reservoirs;
INSERT INTO embalses.ref.river_intake_reservoirs
SELECT n.municipality_code, n.supply_unit_id, n.source_name, n.reservoir_id, n.distance_km,
       'river-name-downstream-8km', 'ph-2022-2027 + hydrorivers'
FROM near n
WHERE n.distance_km <= 8
  AND NOT EXISTS (SELECT 1 FROM embalses."now".municipality_path p JOIN embalses.ref.reservoirs r USING (reservoir_id)
                  WHERE p.municipality_code = n.municipality_code)
ORDER BY n.municipality_code, n.source_name, n.distance_km, n.reservoir_id;

SELECT count(*) AS links, count(DISTINCT municipality_code) AS municipalities, count(DISTINCT reservoir_id) AS reservoirs
FROM embalses.ref.river_intake_reservoirs;
