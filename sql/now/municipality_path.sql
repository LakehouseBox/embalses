-- now.municipality_path: for each municipality, the path of its water as rows: its supply units and their sources
-- (depth 0), then the sources of every network or transfer they draw on, and of the networks those draw on (depth 1 to 5).
-- It is what the page drew step by step in the browser (four or five queries a click, 3-4 s); here it is worked out once
-- an hour, so a click reads one province's small file. Reads ref.municipality_supply, ref.supply_units, ref.supply_sources.
-- Runs inside LakehouseBox as a derived sink (scheduled SQL that reads the catalog), mode replace.
WITH RECURSIVE
first AS (   -- the municipality's own supply units and their sources
  SELECT ms.municipality_code, u.supply_unit_id AS id, u.unit_name AS unit, u.unit_type AS type, u.source_document AS doc,
         u.source_url AS url, s.source_type, s.source_name, s.reservoir_id, s.network_unit_id, s.role
  FROM embalses.ref.municipality_supply ms
  JOIN embalses.ref.supply_units u USING (supply_unit_id)
  LEFT JOIN embalses.ref.supply_sources s
         ON s.supply_unit_id = ms.supply_unit_id AND (s.municipality_code IS NULL OR s.municipality_code = ms.municipality_code)
),
nets(municipality_code, net_id, depth, seen) AS (   -- networks reached from those units, one level per step, no loops
  SELECT DISTINCT f.municipality_code, f.network_unit_id, 1, [f.id]
  FROM first f WHERE f.network_unit_id IS NOT NULL
  UNION ALL
  SELECT n.municipality_code, s.network_unit_id, n.depth + 1, list_append(n.seen, n.net_id)
  FROM nets n JOIN embalses.ref.supply_sources s ON s.supply_unit_id = n.net_id
  WHERE s.network_unit_id IS NOT NULL AND s.municipality_code IS NULL AND n.depth < 5
    AND NOT list_contains(n.seen, s.network_unit_id) AND s.network_unit_id <> n.net_id
),
reached AS (   -- each network once per municipality, at the first depth it is reached, and not one of its own units
  SELECT n.municipality_code, n.net_id, min(n.depth) AS depth
  FROM nets n
  WHERE NOT EXISTS (SELECT 1 FROM first f WHERE f.municipality_code = n.municipality_code AND f.id = n.net_id)
  GROUP BY ALL
)
SELECT left(municipality_code, 2) AS province_code, municipality_code, 0 AS depth, id, unit, type, doc, url,
       source_type, source_name, reservoir_id, network_unit_id, role
FROM first
UNION ALL
SELECT left(r.municipality_code, 2), r.municipality_code, r.depth, u.supply_unit_id, u.unit_name, u.unit_type,
       u.source_document, u.source_url, s.source_type, s.source_name, s.reservoir_id, s.network_unit_id, s.role
FROM reached r
JOIN embalses.ref.supply_units u ON u.supply_unit_id = r.net_id
JOIN embalses.ref.supply_sources s ON s.supply_unit_id = u.supply_unit_id AND s.municipality_code IS NULL
ORDER BY province_code, municipality_code, depth, id
