-- ref.supply_units, ref.municipality_supply, ref.supply_sources: where each municipality's water comes from.
-- Inputs (format: tools/supply_plans_format.md):
--   data/raw/plans/<plan>/           one folder per river-basin plan, written by tools/extract_supply_<plan>.py
--   sql/reference/curated/<network>/ bulk supply networks described by hand from their operators' documents
--                                    (units keyed by supply_unit_id; rows may link to a network with network_unit_id)
--   sql/reference/curated/reservoir_aliases.csv  names the plans use for bulletin reservoirs that do not match by rule
-- Reservoir names are matched to ref.reservoirs: same basin first, else a unique match anywhere.
-- When a curated folder describes how an urban unit is served (rows for that unit), they replace the plan's generic
-- network rows for it ("Red del CYII" -> the treatment plants that serve it).
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/water_supply.sql

-- ── inputs ────────────────────────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE TEMP TABLE meta AS
SELECT regexp_extract(filename, 'plans/([^/]+)/meta.json', 1) AS plan, basin_id, source, plan_cycle, source_document, source_url
FROM read_json('data/raw/plans/*/meta.json', filename = true,
               columns = {basin_id: 'VARCHAR', source: 'VARCHAR', plan_cycle: 'VARCHAR', source_document: 'VARCHAR', source_url: 'VARCHAR'});

CREATE OR REPLACE TEMP TABLE plan_units AS
SELECT m.basin_id || '-' || u.unit_code AS supply_unit_id, m.basin_id, u.unit_code, u.unit_name, 'urban' AS unit_type,
       m.plan_cycle, m.source_document, m.source_url, m.source
FROM read_csv('data/raw/plans/*/supply_units.csv', filename = true, all_varchar = true, header = true, union_by_name = true) u
JOIN meta m ON m.plan = regexp_extract(u.filename, 'plans/([^/]+)/', 1);

CREATE OR REPLACE TEMP TABLE curated_meta AS
SELECT regexp_extract(filename, 'curated/([^/]+)/meta.json', 1) AS network, source
FROM read_json('sql/reference/curated/*/meta.json', filename = true, columns = {source: 'VARCHAR'});

CREATE OR REPLACE TEMP TABLE curated_units AS
SELECT u.supply_unit_id, u.basin_id, u.unit_code, u.unit_name, u.unit_type, NULL AS plan_cycle,
       u.source_document, u.source_url, c.source
FROM read_csv('sql/reference/curated/*/supply_units.csv', filename = true, all_varchar = true, header = true, union_by_name = true) u
JOIN curated_meta c ON c.network = regexp_extract(u.filename, 'curated/([^/]+)/', 1);

CREATE OR REPLACE TEMP TABLE plan_sources AS
SELECT m.basin_id || '-' || s.unit_code AS supply_unit_id, nullif(s.municipality_code, '') AS municipality_code,
       s.source_rank::SMALLINT AS source_rank, s.source_type, nullif(s.source_name, '') AS source_name, s.role,
       NULL::VARCHAR AS network_unit_id, nullif(s.water_body_code, '') AS water_body_code,
       TRY_CAST(nullif(s.share_pct, '') AS DOUBLE) AS share_pct, nullif(s.notes, '') AS notes,
       m.basin_id, m.source, false AS curated
FROM read_csv('data/raw/plans/*/supply_sources.csv', filename = true, all_varchar = true, header = true, union_by_name = true) s
JOIN meta m ON m.plan = regexp_extract(s.filename, 'plans/([^/]+)/', 1);

CREATE OR REPLACE TEMP TABLE curated_sources AS
SELECT s.supply_unit_id, nullif(s.municipality_code, '') AS municipality_code, s.source_rank::SMALLINT AS source_rank,
       s.source_type, nullif(s.source_name, '') AS source_name, s.role, nullif(s.network_unit_id, '') AS network_unit_id,
       nullif(s.water_body_code, '') AS water_body_code, TRY_CAST(nullif(s.share_pct, '') AS DOUBLE) AS share_pct,
       nullif(s.notes, '') AS notes, split_part(s.supply_unit_id, '-', 1) AS basin_id, c.source, true AS curated
FROM read_csv('sql/reference/curated/*/supply_sources.csv', filename = true, all_varchar = true, header = true, union_by_name = true) s
JOIN curated_meta c ON c.network = regexp_extract(s.filename, 'curated/([^/]+)/', 1);

-- ── reservoir names → ref.reservoirs ──────────────────────────────────────────────────────────────────────
-- A comparable key: no accents, case, punctuation, leading article or trailing roman numeral ("Torcón I" = "Torcón").
CREATE OR REPLACE MACRO name_key(s) AS
  trim(regexp_replace(regexp_replace(regexp_replace(
    ' ' || regexp_replace(lower(strip_accents(s)), '[^a-z0-9]+', ' ', 'g') || ' ',
    '^ (el|la|los|las|l|lo|sa|es|o|a|embalse de|embalse del|presa de) ', ' '),
    ' (i|ii|iii|iv) $', ' '), '\s+', ' ', 'g'));

CREATE OR REPLACE TEMP TABLE reservoir_keys AS
WITH names AS (
  SELECT reservoir_id, basin_id, unnest(list_distinct(flatten([
           [reservoir_name, dam_name],
           string_split(reservoir_name, ' - '),
           regexp_extract_all(reservoir_name, '\(([^)]+)\)', 1),
           [regexp_replace(reservoir_name, '\s*\(.*\)\s*', ''),
            regexp_replace(reservoir_name, '^(.*), *(\w+)$', '\2 \1'),
            regexp_replace(dam_name, '^(.*), *(\w+)$', '\2 \1')]]))) AS name
  FROM embalses.ref.reservoirs
  UNION ALL
  SELECT a.reservoir_id, r.basin_id, a.name
  FROM read_csv('sql/reference/curated/reservoir_aliases.csv', header = true, all_varchar = true) a
  JOIN embalses.ref.reservoirs r ON r.reservoir_id = a.reservoir_id::INTEGER
)
SELECT DISTINCT reservoir_id, basin_id, name_key(name) AS k FROM names WHERE name IS NOT NULL AND name_key(name) <> '';

CREATE OR REPLACE TEMP TABLE all_sources AS
SELECT * FROM curated_sources
UNION ALL BY NAME
SELECT p.* FROM plan_sources p
WHERE NOT (p.source_type = 'network'
           AND p.supply_unit_id IN (SELECT supply_unit_id FROM curated_sources WHERE source_type = 'network'));

CREATE OR REPLACE TEMP TABLE matched AS
WITH cand AS (
  SELECT s.rowid AS rid, k.reservoir_id, (k.basin_id = s.basin_id) AS same_basin
  FROM all_sources s JOIN reservoir_keys k ON k.k = name_key(s.source_name)
  WHERE s.source_type = 'reservoir'
),
pick AS (
  SELECT rid,
         CASE WHEN count(DISTINCT reservoir_id) FILTER (WHERE same_basin) = 1 THEN any_value(reservoir_id) FILTER (WHERE same_basin)
              WHEN count(DISTINCT reservoir_id) FILTER (WHERE same_basin) = 0 AND count(DISTINCT reservoir_id) = 1 THEN any_value(reservoir_id)
         END AS reservoir_id,
         count(DISTINCT reservoir_id) AS candidates
  FROM cand GROUP BY rid
)
SELECT s.*, p.reservoir_id AS matched_reservoir_id, coalesce(p.candidates, 0) AS candidates
FROM all_sources s LEFT JOIN pick p ON p.rid = s.rowid;

-- Plan rows naming a network (by its name) link to that network's own unit.
CREATE OR REPLACE TEMP TABLE network_names AS
SELECT supply_unit_id, name_key(unit_name) AS k FROM curated_units WHERE unit_type = 'network';

-- ── load ──────────────────────────────────────────────────────────────────────────────────────────────────
DELETE FROM embalses.ref.supply_units;
INSERT INTO embalses.ref.supply_units
SELECT supply_unit_id, basin_id, unit_code, unit_name, unit_type, plan_cycle, source_document, source_url, source
FROM (SELECT * FROM curated_units UNION ALL BY NAME SELECT * FROM plan_units);

DELETE FROM embalses.ref.municipality_supply;
INSERT INTO embalses.ref.municipality_supply
SELECT m.basin_id || '-' || s.unit_code, s.municipality_code,
       TRY_CAST(nullif(s.share_pct, '') AS DOUBLE), nullif(s.intake_description, ''),
       TRY_CAST(nullif(s.additional_intakes, '') AS SMALLINT), m.source
FROM read_csv('data/raw/plans/*/municipality_supply.csv', filename = true, all_varchar = true, header = true, union_by_name = true) s
JOIN meta m ON m.plan = regexp_extract(s.filename, 'plans/([^/]+)/', 1);

DELETE FROM embalses.ref.supply_sources;
INSERT INTO embalses.ref.supply_sources
SELECT s.supply_unit_id, s.municipality_code, s.source_rank, s.source_type, s.source_name, s.role,
       s.matched_reservoir_id,
       coalesce(s.network_unit_id, CASE WHEN s.source_type IN ('network', 'transfer') THEN (SELECT any_value(n.supply_unit_id) FROM network_names n WHERE n.k = name_key(s.source_name)) END),
       s.water_body_code, s.share_pct,
       CASE WHEN s.candidates > 1 AND s.matched_reservoir_id IS NULL THEN 'review'
            WHEN s.curated AND s.notes ILIKE '%to confirm%' THEN 'review'
            WHEN s.curated THEN 'reviewed' ELSE 'auto' END,
       CASE WHEN s.candidates > 1 AND s.matched_reservoir_id IS NULL
            THEN concat_ws('; ', s.notes, 'name matches several bulletin reservoirs') ELSE s.notes END,
       s.source
FROM matched s;

-- municipality_supply must name existing municipalities and units
SELECT 'municipality_supply rows without a municipality' AS check, count(*) AS n FROM embalses.ref.municipality_supply ms
  WHERE ms.municipality_code NOT IN (SELECT municipality_code FROM embalses.ref.municipalities)
UNION ALL SELECT 'municipality_supply rows without a unit', count(*) FROM embalses.ref.municipality_supply
  WHERE supply_unit_id NOT IN (SELECT supply_unit_id FROM embalses.ref.supply_units)
UNION ALL SELECT 'source rows without a unit', count(*) FROM embalses.ref.supply_sources
  WHERE supply_unit_id NOT IN (SELECT supply_unit_id FROM embalses.ref.supply_units)
UNION ALL SELECT 'network and transfer rows linked to a network', count(*) FROM embalses.ref.supply_sources
  WHERE network_unit_id IS NOT NULL
UNION ALL SELECT 'network rows not linked (no network description yet)', count(*) FROM embalses.ref.supply_sources
  WHERE source_type = 'network' AND network_unit_id IS NULL
UNION ALL SELECT 'reservoir rows matched to the bulletin', count(*) FROM embalses.ref.supply_sources
  WHERE source_type = 'reservoir' AND reservoir_id IS NOT NULL
UNION ALL SELECT 'reservoir rows not in the bulletin', count(*) FROM embalses.ref.supply_sources
  WHERE source_type = 'reservoir' AND reservoir_id IS NULL
UNION ALL SELECT 'municipalities with a supply unit', count(DISTINCT municipality_code) FROM embalses.ref.municipality_supply;
