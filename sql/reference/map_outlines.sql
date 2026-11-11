-- ref.map_outlines: display outlines as GeoJSON text. One-time load from the simplified files in sql/reference/outlines/
-- (basins from the MITECO demarcaciones, regions and provinces from MITECO's map services, rivers from HydroRIVERS).
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/map_outlines.sql
DELETE FROM embalses.ref.map_outlines;
INSERT INTO embalses.ref.map_outlines
SELECT 'basin', basin_id, basin_name, NULL, NULL, geometry::VARCHAR, 'MITECO, demarcaciones hidrográficas'
FROM read_json('sql/reference/outlines/basins.json', columns = {basin_id: 'VARCHAR', basin_name: 'VARCHAR', geometry: 'JSON'})
UNION ALL
SELECT 'region', name, name, NULL, NULL, geometry::VARCHAR, 'MITECO map services, comunidades autónomas'
FROM read_json('sql/reference/outlines/regions.json', columns = {name: 'VARCHAR', geometry: 'JSON'})
UNION ALL
SELECT 'province', name, name, NULL, NULL, geometry::VARCHAR, 'MITECO map services, provincias'
FROM read_json('sql/reference/outlines/provinces.json', columns = {name: 'VARCHAR', geometry: 'JSON'})
UNION ALL
SELECT 'river', (row_number() OVER ())::VARCHAR, NULL, stream_order, mean_flow_m3s, geometry::VARCHAR, 'HydroRIVERS (HydroSHEDS, CC BY 4.0)'
FROM read_json('sql/reference/outlines/rivers.json', columns = {stream_order: 'INTEGER', mean_flow_m3s: 'DOUBLE', geometry: 'JSON'});
SELECT layer, count(*) AS outlines, sum(length(geojson)) AS characters FROM embalses.ref.map_outlines GROUP BY 1 ORDER BY 1;
