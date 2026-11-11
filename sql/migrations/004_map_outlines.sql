-- Outlines for drawing maps, as GeoJSON text: a browser reads them with DuckDB-WASM and no spatial extension.
-- Loaded once by sql/reference/map_outlines.sql.

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses.ref.map_outlines (
  layer VARCHAR,
  outline_id VARCHAR,
  name VARCHAR,
  stream_order INTEGER,
  mean_flow_m3s DOUBLE,
  geojson VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.map_outlines IS 'Simplified outlines for drawing a map of Spain (peninsula and Balearic Islands): river basin districts, comunidades autónomas, provinces and the main rivers. The shape is GeoJSON text, so it can be read without a spatial extension (for example from a browser). For analysis use ref.basins and ref.rivers, which hold the full geometry. Static: loaded once by sql/reference/map_outlines.sql.';
COMMENT ON COLUMN embalses.ref.map_outlines.layer IS 'What the outline is: basin, region (comunidad autónoma), province or river.';
COMMENT ON COLUMN embalses.ref.map_outlines.outline_id IS 'Identifier within the layer: basin_id for basins (ref.basins), the name for regions and provinces, a running number for rivers.';
COMMENT ON COLUMN embalses.ref.map_outlines.name IS 'Name to show. For basins it equals ref.basins.basin_name; regions and provinces use the official Spanish names. Empty for rivers.';
COMMENT ON COLUMN embalses.ref.map_outlines.stream_order IS 'Rivers only: stream order (HydroRIVERS), larger for main stems.';
COMMENT ON COLUMN embalses.ref.map_outlines.mean_flow_m3s IS 'Rivers only: long-term mean discharge in m³/s (HydroRIVERS), useful for line width.';
COMMENT ON COLUMN embalses.ref.map_outlines.geojson IS 'GeoJSON geometry as text (Polygon, MultiPolygon, LineString or MultiLineString), WGS84 longitude and latitude, simplified for display.';
COMMENT ON COLUMN embalses.ref.map_outlines.source IS 'Where the outline comes from.';
