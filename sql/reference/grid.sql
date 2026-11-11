-- H3 grid for interpolated rain (resolution 6, ~37 km² per cell) and the cells of each catchment unit.
-- Run once (or when ref.basins / ref.catchments change):
--   lhbox duckdb --catalog embalses -- -f sql/reference/grid.sql
-- then import data/build/ref_grid_cells.parquet and ref_catchment_cells.parquet with `lhbox table import`.
INSTALL h3 FROM community; LOAD h3; LOAD spatial;
SET geometry_always_xy = true;

-- every cell whose centre lies in a river basin district
CREATE OR REPLACE TEMP TABLE cells AS
SELECT DISTINCT unnest(h3_polygon_wkt_to_cells(ST_AsText(part), 6)) AS cell, basin_id
FROM (SELECT basin_id, unnest(ST_Dump(geometry)).geom AS part FROM embalses.ref.basins);   -- h3 fills Polygons only

COPY (
  SELECT h3_h3_to_string(cell) AS h3_cell,
         basin_id,
         round(h3_cell_area(cell, 'km^2'), 2) AS cell_area_km2,
         ST_GeomFromText(h3_cell_to_boundary_wkt(cell)) AS geometry
  FROM cells
  QUALIFY row_number() OVER (PARTITION BY cell ORDER BY basin_id) = 1
  ORDER BY h3_cell
) TO 'data/build/ref_grid_cells.parquet' (FORMAT parquet);

-- the cells of each catchment unit; a unit too small to contain a cell centre gets the cell under its centre
CREATE OR REPLACE TEMP TABLE unit_cells AS
WITH filled AS (
  SELECT catchment_id, unnest(h3_polygon_wkt_to_cells(ST_AsText(part), 6)) AS cell
  FROM (SELECT catchment_id, unnest(ST_Dump(geometry)).geom AS part FROM embalses.ref.catchments)),
missing AS (
  SELECT c.catchment_id,
         h3_latlng_to_cell(ST_Y(ST_PointOnSurface(c.geometry)), ST_X(ST_PointOnSurface(c.geometry)), 6) AS cell
  FROM embalses.ref.catchments c
  WHERE c.catchment_id NOT IN (SELECT catchment_id FROM filled))
SELECT * FROM filled UNION ALL SELECT * FROM missing;

COPY (
  SELECT catchment_id, h3_h3_to_string(cell) AS h3_cell,
         round(1.0 / count(*) OVER (PARTITION BY catchment_id), 6) AS cell_weight
  FROM unit_cells
  ORDER BY catchment_id, h3_cell
) TO 'data/build/ref_catchment_cells.parquet' (FORMAT parquet);
