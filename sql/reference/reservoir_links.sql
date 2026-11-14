-- ref.reservoir_links, river part: each reservoir joined to the next reservoir downstream on the river network.
-- Computed from the catalog itself: ref.reservoirs.river_segment_id (the HydroRIVERS segment each dam was snapped to)
-- and ref.rivers.downstream_segment_id. Canal and transfer rows are loaded separately and are left untouched.
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/reservoir_links.sql
INSTALL spatial; LOAD spatial;
SET geometry_always_xy = true;   -- longitude, latitude (as in build_reference.sql)

CREATE OR REPLACE TEMP TABLE river_links AS
WITH RECURSIVE
dams AS (   -- dams on the network, ordered along a shared segment by where the dam sits on it
  SELECT d.reservoir_id, d.river_segment_id AS seg,
         ST_LineLocatePoint(r.geometry, d.dam_location) AS frac,
         ST_Distance_Sphere(ST_ClosestPoint(r.geometry, d.dam_location), d.dam_location) / 1000 AS off_river_km
  FROM embalses.ref.reservoirs d JOIN embalses.ref.rivers r ON r.river_segment_id = d.river_segment_id
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY seg ORDER BY frac) AS k, count(*) OVER (PARTITION BY seg) AS n FROM dams
),
same_segment AS (   -- two dams on one segment: the upper one drains into the lower one
  SELECT a.reservoir_id AS from_id, b.reservoir_id AS to_id, [a.seg] AS segs, true AS shared
  FROM ranked a JOIN ranked b ON a.seg = b.seg AND b.k = a.k + 1
),
walk(start_id, seg, segs, steps) AS (   -- from the lowest dam on each segment, follow the river down
  SELECT d.reservoir_id, r.downstream_segment_id, [d.seg], 1
  FROM ranked d JOIN embalses.ref.rivers r ON r.river_segment_id = d.seg
  WHERE d.k = d.n
  UNION ALL
  SELECT w.start_id, r.downstream_segment_id, list_append(w.segs, w.seg), w.steps + 1
  FROM walk w JOIN embalses.ref.rivers r ON r.river_segment_id = w.seg
  WHERE w.seg NOT IN (SELECT seg FROM dams) AND w.steps < 5000
),
downstream AS (   -- the first segment with a dam on it; its uppermost dam is the next reservoir
  SELECT w.start_id AS from_id, t.reservoir_id AS to_id, w.segs, false AS shared
  FROM walk w JOIN ranked t ON t.seg = w.seg AND t.k = 1
),
links AS (SELECT * FROM same_segment UNION ALL SELECT * FROM downstream)
SELECT l.from_id AS from_reservoir_id, l.to_id AS to_reservoir_id,
       'river' AS link_type, NULL::VARCHAR AS link_name,
       round(sum(r.length_km), 2) AS length_km,
       len(l.segs)::INTEGER AS river_segments,
       ST_LineMerge(ST_Union_Agg(r.geometry)) AS path,
       l.shared, max(fa.off_river_km) AS from_off_km, max(ta.off_river_km) AS to_off_km
FROM links l
JOIN embalses.ref.rivers r ON list_contains(l.segs, r.river_segment_id)
JOIN dams fa ON fa.reservoir_id = l.from_id
JOIN dams ta ON ta.reservoir_id = l.to_id
GROUP BY ALL;

DELETE FROM embalses.ref.reservoir_links WHERE link_type = 'river';
INSERT INTO embalses.ref.reservoir_links
SELECT from_reservoir_id, to_reservoir_id, link_type, link_name, length_km, river_segments, path,
       CASE WHEN shared OR greatest(from_off_km, to_off_km) > 2 THEN 'review' ELSE 'auto' END,
       nullif(concat_ws('; ',
         CASE WHEN shared THEN 'both dams are on the same river segment; order taken from where each dam sits on it (pumped-storage pairs and duplicate entries land here)' END,
         CASE WHEN greatest(from_off_km, to_off_km) > 2 THEN 'a dam is ' || round(greatest(from_off_km, to_off_km), 1) || ' km from the river line it was snapped to' END), ''),
       'hydrorivers'
FROM river_links;

SELECT link_type, confidence, count(*) AS links, round(sum(length_km)) AS km FROM embalses.ref.reservoir_links GROUP BY ALL ORDER BY ALL;
