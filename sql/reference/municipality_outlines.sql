-- ref.municipality_outlines: simplified municipal outlines for drawing, from ref.municipalities (INE codes, IGN boundaries).
-- Run from the repository root after sql/reference/municipalities.sql, into an empty table (see the note in water_supply.sql):
--   lhbox duckdb --catalog embalses -- -f sql/reference/municipality_outlines.sql
INSTALL spatial; LOAD spatial;
SET geometry_always_xy = true;
INSERT INTO embalses.ref.municipality_outlines
SELECT municipality_code, province_code, municipality_name,
       ST_AsGeoJSON(ST_ReducePrecision(ST_SimplifyPreserveTopology(boundary, 0.002), 0.0001))::VARCHAR,
       'IGN municipal boundaries (via ref.municipalities), simplified'
FROM embalses.ref.municipalities
WHERE boundary IS NOT NULL
ORDER BY province_code, municipality_code;
SELECT count(*) AS outlines, count(DISTINCT province_code) AS provinces, round(sum(length(geojson)) / 1e6, 2) AS mb
FROM embalses.ref.municipality_outlines;
