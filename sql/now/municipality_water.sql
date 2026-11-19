-- now.municipality_water: for every municipality, the bulletin reservoirs behind its tap water and how full they are
-- together. Follows ref.municipality_supply → ref.supply_sources (through networks and transfers, network_unit_id) to the
-- source reservoirs, then ref.reservoir_links upstream; levels from now.reservoir_status, weighted by capacity.
-- Runs inside LakehouseBox as a derived sink (scheduled SQL that reads the catalog), mode replace: each run swaps the table.
-- Where no plan names a reservoir behind the supply, the reservoirs upstream of its river intakes count instead
-- (ref.river_intake_reservoirs, an estimate; listed apart in river_reservoir_ids, added by migration 011).
-- One SELECT; see lakehouse.yaml for its schedule.
WITH RECURSIVE
supply AS (SELECT municipality_code, supply_unit_id FROM embalses.ref.municipality_supply),
sources(municipality_code, source_type, reservoir_id, network_unit_id, depth) AS (
  -- a unit's rows for the whole unit, or for this municipality only
  SELECT u.municipality_code, s.source_type, s.reservoir_id, s.network_unit_id, 0
  FROM supply u JOIN embalses.ref.supply_sources s
    ON s.supply_unit_id = u.supply_unit_id AND (s.municipality_code IS NULL OR s.municipality_code = u.municipality_code)
  UNION
  -- through a network or transfer to its own sources (networks can chain: Taibilla → Tajo-Segura transfer)
  SELECT p.municipality_code, s.source_type, s.reservoir_id, s.network_unit_id, p.depth + 1
  FROM sources p JOIN embalses.ref.supply_sources s ON s.supply_unit_id = p.network_unit_id
  WHERE p.depth < 5
),
source_reservoirs AS (SELECT DISTINCT municipality_code, reservoir_id FROM sources WHERE reservoir_id IS NOT NULL),
upstream_of(reservoir_id, upstream_id) AS (   -- every reservoir upstream of each reservoir, along the river links
  SELECT to_reservoir_id, from_reservoir_id FROM embalses.ref.reservoir_links WHERE link_type = 'river'
  UNION
  SELECT u.reservoir_id, l.from_reservoir_id
  FROM upstream_of u JOIN embalses.ref.reservoir_links l ON l.to_reservoir_id = u.upstream_id AND l.link_type = 'river'
),
upstream_reservoirs AS (
  SELECT DISTINCT s.municipality_code, u.upstream_id AS reservoir_id
  FROM source_reservoirs s JOIN upstream_of u USING (reservoir_id)
  ANTI JOIN source_reservoirs x ON x.municipality_code = s.municipality_code AND x.reservoir_id = u.upstream_id
),
river_reservoirs AS (   -- estimated; the loader keeps only municipalities with no source reservoir
  SELECT DISTINCT r.municipality_code, r.reservoir_id FROM embalses.ref.river_intake_reservoirs r
  ANTI JOIN source_reservoirs s USING (municipality_code)
),
counted AS (SELECT * FROM source_reservoirs UNION SELECT * FROM upstream_reservoirs UNION SELECT * FROM river_reservoirs),
levels AS (
  SELECT c.municipality_code, count(*)::INTEGER AS reservoirs,
         sum(r.stored_volume_hm3) AS stored_volume_hm3, sum(r.capacity_hm3) AS capacity_hm3,
         sum(r.fill_pct_same_week_last_year * r.capacity_hm3) / sum(r.capacity_hm3) FILTER (WHERE r.fill_pct_same_week_last_year IS NOT NULL) AS last_year,
         sum(r.fill_pct_10y_average * r.capacity_hm3) / sum(r.capacity_hm3) FILTER (WHERE r.fill_pct_10y_average IS NOT NULL) AS avg_10y
  FROM counted c JOIN embalses."now".reservoir_status r USING (reservoir_id)
  WHERE r.stored_volume_hm3 IS NOT NULL AND r.capacity_hm3 > 0
  GROUP BY 1
),
units AS (
  SELECT u.municipality_code, list(DISTINCT su.unit_name ORDER BY su.unit_name) AS names
  FROM supply u JOIN embalses.ref.supply_units su USING (supply_unit_id) GROUP BY 1
),
kinds AS (
  SELECT municipality_code, list(DISTINCT source_type ORDER BY source_type) AS types
  FROM sources WHERE source_type <> 'network' GROUP BY 1
),
lists AS (
  SELECT municipality_code,
         list(DISTINCT reservoir_id ORDER BY reservoir_id) FILTER (WHERE kind = 'source') AS source_ids,
         list(DISTINCT reservoir_id ORDER BY reservoir_id) FILTER (WHERE kind = 'upstream') AS upstream_ids,
         list(DISTINCT reservoir_id ORDER BY reservoir_id) FILTER (WHERE kind = 'river') AS river_ids
  FROM (SELECT *, 'source' AS kind FROM source_reservoirs UNION ALL SELECT *, 'upstream' FROM upstream_reservoirs
        UNION ALL SELECT *, 'river' FROM river_reservoirs)
  GROUP BY 1
)
SELECT m.municipality_code, m.municipality_name, m.province_name, m.population,
       units.names AS supply_unit_names, kinds.types AS source_types,
       lists.source_ids AS source_reservoir_ids, lists.upstream_ids AS upstream_reservoir_ids,
       coalesce(l.reservoirs, 0) AS reservoirs,
       round(l.stored_volume_hm3, 1) AS stored_volume_hm3, round(l.capacity_hm3, 1) AS capacity_hm3,
       round(100 * l.stored_volume_hm3 / l.capacity_hm3, 1) AS fill_pct,
       round(l.last_year, 1) AS fill_pct_same_week_last_year, round(l.avg_10y, 1) AS fill_pct_10y_average,
       (SELECT max(as_of) FROM embalses."now".reservoir_status) AS as_of,
       lists.river_ids AS river_reservoir_ids   -- migration 011: last, in the table's column order
FROM embalses.ref.municipalities m
LEFT JOIN units USING (municipality_code)
LEFT JOIN kinds USING (municipality_code)
LEFT JOIN lists USING (municipality_code)
LEFT JOIN levels l USING (municipality_code)
ORDER BY m.municipality_code
