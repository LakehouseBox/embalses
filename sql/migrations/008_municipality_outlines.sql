-- Simplified municipal outlines for drawing a map, as GeoJSON text, one partition per province: a browser that opens
-- a province reads only that province's file. Loaded by sql/reference/municipality_outlines.sql.

-- lhbox: format-version=2 partition=province_code
CREATE TABLE IF NOT EXISTS embalses.ref.municipality_outlines (
  municipality_code VARCHAR,
  province_code VARCHAR,
  municipality_name VARCHAR,
  geojson VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.municipality_outlines IS 'Simplified outline of every municipality, for drawing a map (for example in a browser, without a spatial extension). GeoJSON text, WGS84, simplified to about 200 m. Partitioned by province_code, so reading one province reads one file. For analysis use ref.municipalities.boundary, the full geometry. Static: loaded by sql/reference/municipality_outlines.sql from ref.municipalities.';
COMMENT ON COLUMN embalses.ref.municipality_outlines.municipality_code IS 'INE municipality code (ref.municipalities).';
COMMENT ON COLUMN embalses.ref.municipality_outlines.province_code IS 'INE province code, the first two digits of municipality_code; the partition.';
COMMENT ON COLUMN embalses.ref.municipality_outlines.municipality_name IS 'Name as people write it (ref.municipalities.municipality_name).';
COMMENT ON COLUMN embalses.ref.municipality_outlines.geojson IS 'GeoJSON geometry as text (Polygon or MultiPolygon), WGS84 longitude and latitude, simplified for display (tolerance 0.002°, coordinates to 0.0001°). Neighbouring outlines are simplified one by one, so they may not meet exactly.';
COMMENT ON COLUMN embalses.ref.municipality_outlines.source IS 'Where the outline comes from.';
