-- ref.municipalities: every municipality in Spain with name, province, region, population and boundary.
-- Inputs, downloaded by tools/fetch_municipalities.py into data/raw/:
--   ine/diccionario26.xlsx        INE, Relación de municipios y sus códigos (1 January 2026)
--   ine/population/t*.json        INE, Cifras oficiales de población (Revisión del Padrón), latest year
--   ign/*.geojson                 IGN municipal boundaries (NATCODE / nationalCode ends in the INE code);
--                                 new_<code>.geojson: municipalities created after the boundary file
-- Run from the repository root:  lhbox duckdb --catalog embalses -- -f sql/reference/municipalities.sql
INSTALL spatial; LOAD spatial; INSTALL excel; LOAD excel;
SET geometry_always_xy = true;

CREATE OR REPLACE TEMP TABLE ine_list AS
SELECT lpad(CPRO, 2, '0') || lpad(CMUN, 3, '0') AS municipality_code, trim(NOMBRE) AS official_name,
       lpad(CPRO, 2, '0') AS province_code, lpad(CODAUTO, 2, '0') AS region_code
FROM read_xlsx('data/raw/ine/diccionario26.xlsx', range = 'A2:E9000', header = true, all_varchar = true)
WHERE NOMBRE IS NOT NULL;

CREATE OR REPLACE TEMP TABLE population AS
WITH series AS (
  SELECT unnest(s) AS s FROM read_json('data/raw/ine/population/t*.json', format = 'unstructured', maximum_object_size = 268435456) t(s)
)
SELECT list_filter(s.MetaData, lambda m: m.T3_Variable = 'Municipios')[1].Codigo AS municipality_code,
       s.Data[-1].Valor::INTEGER AS population, s.Data[-1].Anyo::SMALLINT AS population_year
FROM series
WHERE list_filter(s.MetaData, lambda m: m.T3_Variable = 'Sexo')[1].Codigo = '0'
  AND len(list_filter(s.MetaData, lambda m: m.T3_Variable = 'Municipios')) = 1;

CREATE OR REPLACE TEMP TABLE raw_boundaries AS
WITH features AS (
  SELECT filename, unnest(fc.features) AS f
  FROM read_json('data/raw/ign/*.geojson', format = 'auto', maximum_object_size = 1073741824, union_by_name = true, filename = true) fc
)
SELECT right(coalesce(f.properties.NATCODE, f.properties.nationalCode), 5) AS municipality_code,
       filename LIKE '%/new\_%' ESCAPE '\' AS is_new,
       ST_MakeValid(ST_Union_Agg(ST_MakeValid(ST_SimplifyPreserveTopology(ST_MakeValid(ST_GeomFromGeoJSON(to_json(f.geometry))), 0.0002)))) AS boundary
FROM features GROUP BY ALL;

-- Municipalities created after the boundary file come from the live service; cut them out of the outline they were
-- taken from, so no ground belongs to two municipalities.
CREATE OR REPLACE TEMP TABLE boundaries AS
WITH new AS (SELECT * FROM raw_boundaries WHERE is_new)
SELECT o.municipality_code,
       coalesce(ST_MakeValid(ST_Difference(o.boundary, (SELECT ST_Union_Agg(n.boundary) FROM new n
                                                         WHERE ST_Intersects(n.boundary, o.boundary)))), o.boundary) AS boundary
FROM raw_boundaries o WHERE NOT o.is_new AND o.municipality_code NOT IN (SELECT municipality_code FROM new)
UNION ALL
SELECT municipality_code, boundary FROM new;

-- INE names put the article last ("Rozas de Madrid, Las"); people write it first ("Las Rozas de Madrid").
-- Bilingual names ("Donostia/San Sebastián") are turned part by part.
CREATE OR REPLACE MACRO article_first(name) AS
  array_to_string(list_transform(string_split(name, '/'), lambda p:
    CASE WHEN regexp_matches(p, ', (L'')$') THEN regexp_replace(p, '^(.*), (L'')$', '\2\1')
         WHEN regexp_matches(p, ', (El|La|Los|Las|Les|Els|A|O|As|Os|Lo|Sa|Es|Ses|Na)$') THEN regexp_replace(p, '^(.*), (\w+)$', '\2 \1')
         ELSE p END), '/');

CREATE OR REPLACE TEMP TABLE province_names(province_code VARCHAR, province_name VARCHAR);
INSERT INTO province_names VALUES
 ('01','Araba/Álava'),('02','Albacete'),('03','Alicante/Alacant'),('04','Almería'),('05','Ávila'),('06','Badajoz'),
 ('07','Illes Balears'),('08','Barcelona'),('09','Burgos'),('10','Cáceres'),('11','Cádiz'),('12','Castellón/Castelló'),
 ('13','Ciudad Real'),('14','Córdoba'),('15','A Coruña'),('16','Cuenca'),('17','Girona'),('18','Granada'),
 ('19','Guadalajara'),('20','Gipuzkoa'),('21','Huelva'),('22','Huesca'),('23','Jaén'),('24','León'),('25','Lleida'),
 ('26','La Rioja'),('27','Lugo'),('28','Madrid'),('29','Málaga'),('30','Murcia'),('31','Navarra'),('32','Ourense'),
 ('33','Asturias'),('34','Palencia'),('35','Las Palmas'),('36','Pontevedra'),('37','Salamanca'),
 ('38','Santa Cruz de Tenerife'),('39','Cantabria'),('40','Segovia'),('41','Sevilla'),('42','Soria'),('43','Tarragona'),
 ('44','Teruel'),('45','Toledo'),('46','Valencia/València'),('47','Valladolid'),('48','Bizkaia'),('49','Zamora'),
 ('50','Zaragoza'),('51','Ceuta'),('52','Melilla');

CREATE OR REPLACE TEMP TABLE region_names(region_code VARCHAR, region_name VARCHAR);
INSERT INTO region_names VALUES
 ('01','Andalucía'),('02','Aragón'),('03','Principado de Asturias'),('04','Illes Balears'),('05','Canarias'),
 ('06','Cantabria'),('07','Castilla y León'),('08','Castilla-La Mancha'),('09','Cataluña'),('10','Comunitat Valenciana'),
 ('11','Extremadura'),('12','Galicia'),('13','Comunidad de Madrid'),('14','Región de Murcia'),
 ('15','Comunidad Foral de Navarra'),('16','País Vasco'),('17','La Rioja'),('18','Ceuta'),('19','Melilla');

DELETE FROM embalses.ref.municipalities;
INSERT INTO embalses.ref.municipalities
SELECT m.municipality_code, article_first(m.official_name), m.official_name,
       m.province_code, p.province_name, m.region_code, r.region_name,
       pop.population, pop.population_year,
       round(ST_Area_Spheroid(b.boundary) / 1e6, 2),
       round(ST_X(ST_PointOnSurface(b.boundary)), 5), round(ST_Y(ST_PointOnSurface(b.boundary)), 5),
       b.boundary, 'ine-ign'
FROM ine_list m
JOIN province_names p USING (province_code)
JOIN region_names r USING (region_code)
LEFT JOIN population pop USING (municipality_code)
LEFT JOIN boundaries b USING (municipality_code);

SELECT count(*) AS municipalities, count(population) AS with_population, count(boundary) AS with_boundary,
       sum(population) AS population, min(population_year) AS year
FROM embalses.ref.municipalities;
