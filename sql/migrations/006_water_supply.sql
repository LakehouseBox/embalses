-- Where each municipality's tap water comes from.
--   ref.municipalities        every municipality in Spain (INE), with population and boundary (IGN)
--   ref.supply_units          the urban supply units the river-basin plans define (unidades de demanda urbana)
--   ref.municipality_supply   which supply unit serves each municipality, with the plan's own description of the intake
--   ref.supply_sources        where each unit, or one municipality within it, takes its water: reservoirs, rivers, aquifers…
-- Loaded once per source by sql/reference/municipalities.sql and sql/reference/supply_<basin>.sql.

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.municipalities (
  municipality_code VARCHAR,
  municipality_name VARCHAR,
  official_name VARCHAR,
  province_code VARCHAR,
  province_name VARCHAR,
  region_code VARCHAR,
  region_name VARCHAR,
  population INTEGER,
  population_year SMALLINT,
  area_km2 DOUBLE,
  longitude DOUBLE,
  latitude DOUBLE,
  boundary GEOMETRY('EPSG:4326'),
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.municipalities IS 'Every municipality in Spain, one row each: INE code and name, province, autonomous community, official population and boundary. Key municipality_code is INE''s 5-digit code (2 digits province + 3 municipality). Sources: INE (Relación de municipios y sus códigos; Cifras oficiales de población, Revisión del Padrón), IGN (INSPIRE administrative units).';
COMMENT ON COLUMN embalses.ref.municipalities.municipality_code IS 'INE municipality code, 5 digits as text (keeps the leading zero: 05002). Key.';
COMMENT ON COLUMN embalses.ref.municipalities.municipality_name IS 'Name as people write it, article first: "Las Rozas de Madrid". Bilingual names keep both forms: "Donostia/San Sebastián".';
COMMENT ON COLUMN embalses.ref.municipalities.official_name IS 'Name exactly as in INE''s register, article last: "Rozas de Madrid, Las".';
COMMENT ON COLUMN embalses.ref.municipalities.province_code IS 'INE province code, 2 digits (the first two of municipality_code).';
COMMENT ON COLUMN embalses.ref.municipalities.province_name IS 'Province, INE''s official name ("Alicante/Alacant", "A Coruña", "Illes Balears").';
COMMENT ON COLUMN embalses.ref.municipalities.region_code IS 'INE code of the autonomous community or city, 2 digits.';
COMMENT ON COLUMN embalses.ref.municipalities.region_name IS 'Autonomous community or city ("Comunidad de Madrid", "Ceuta").';
COMMENT ON COLUMN embalses.ref.municipalities.population IS 'Official population on 1 January of population_year (INE, Revisión del Padrón municipal).';
COMMENT ON COLUMN embalses.ref.municipalities.population_year IS 'Year of the population figure.';
COMMENT ON COLUMN embalses.ref.municipalities.area_km2 IS 'Area of the boundary, km².';
COMMENT ON COLUMN embalses.ref.municipalities.longitude IS 'A point guaranteed inside the municipality (not always the town centre), longitude, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.municipalities.latitude IS 'Latitude of the same point.';
COMMENT ON COLUMN embalses.ref.municipalities.boundary IS 'Municipal boundary, MultiPolygon, EPSG:4326, simplified to about 20 m. Null where IGN has none.';
COMMENT ON COLUMN embalses.ref.municipalities.source IS 'Key of the sources (ine-ign).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.supply_units (
  supply_unit_id VARCHAR,
  basin_id VARCHAR,
  unit_code VARCHAR,
  unit_name VARCHAR,
  unit_type VARCHAR,
  plan_cycle VARCHAR,
  source_document VARCHAR,
  source_url VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.supply_units IS 'Urban supply units (unidades de demanda urbana, UDU) as each river-basin plan defines them: a town, or a group of towns sharing intakes and a network; plus the bulk supply networks those units draw on (unit_type network). One row per unit. Which municipalities a unit serves is in ref.municipality_supply; where it takes its water, in ref.supply_sources.';
COMMENT ON COLUMN embalses.ref.supply_units.supply_unit_id IS 'Key: basin_id and the plan''s own code, "ES030-SAT04A13"; networks: basin_id and a short name, "ES030-CYII". Unique across basins.';
COMMENT ON COLUMN embalses.ref.supply_units.basin_id IS 'River basin district whose plan defines the unit (ref.basins).';
COMMENT ON COLUMN embalses.ref.supply_units.unit_code IS 'Code the plan gives the unit (SAT04A13).';
COMMENT ON COLUMN embalses.ref.supply_units.unit_name IS 'Name the plan gives the unit ("Majadahonda (CYII)", "Mancomunidad de Aguas del Sorbe").';
COMMENT ON COLUMN embalses.ref.supply_units.unit_type IS 'urban (a supply unit a river-basin plan defines, serving the municipalities in ref.municipality_supply) or network (a bulk supplier''s system, such as Canal de Isabel II or the Mancomunidad de los Canales del Taibilla, that urban units take water from; its own sources are its rows in ref.supply_sources).';
COMMENT ON COLUMN embalses.ref.supply_units.plan_cycle IS 'Planning cycle of the plan read (2022-2027).';
COMMENT ON COLUMN embalses.ref.supply_units.source_document IS 'Document, annex and table the unit was read from.';
COMMENT ON COLUMN embalses.ref.supply_units.source_url IS 'Where that document is published.';
COMMENT ON COLUMN embalses.ref.supply_units.source IS 'Key of the source (ph-tajo-2022-2027, …).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.municipality_supply (
  municipality_code VARCHAR,
  supply_unit_id VARCHAR,
  share_pct DOUBLE,
  intake_description VARCHAR,
  additional_intakes SMALLINT,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.municipality_supply IS 'Which supply unit serves each municipality, as the river-basin plans assign them. One row per municipality and unit; a municipality split between units has one row each, with share_pct. Municipalities a loaded plan does not list have no row (yet).';
COMMENT ON COLUMN embalses.ref.municipality_supply.municipality_code IS 'INE municipality code (ref.municipalities).';
COMMENT ON COLUMN embalses.ref.municipality_supply.supply_unit_id IS 'Supply unit (ref.supply_units).';
COMMENT ON COLUMN embalses.ref.municipality_supply.share_pct IS 'Share of the municipality''s population this unit serves, 0–100, when the source gives the split; null when the unit serves all of it, or when a plan places the municipality in several units without saying how much each serves.';
COMMENT ON COLUMN embalses.ref.municipality_supply.intake_description IS 'The plan''s own description of where this municipality''s water is taken, verbatim in Spanish ("Toma en embalses de Guadiloba y Alcántara"). ref.supply_sources holds the same, structured.';
COMMENT ON COLUMN embalses.ref.municipality_supply.additional_intakes IS 'Further intakes the plan counts for this municipality besides the ordinary one, when it gives the number.';
COMMENT ON COLUMN embalses.ref.municipality_supply.source IS 'Key of the source (ph-tajo-2022-2027, …).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.supply_sources (
  supply_unit_id VARCHAR,
  municipality_code VARCHAR,
  source_rank SMALLINT,
  source_type VARCHAR,
  source_name VARCHAR,
  role VARCHAR,
  reservoir_id INTEGER,
  network_unit_id VARCHAR,
  water_body_code VARCHAR,
  share_pct DOUBLE,
  confidence VARCHAR,
  notes VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.supply_sources IS 'Where a supply unit takes its water, one row per source: a reservoir, river, aquifer, spring, desalination plant, transfer or a network that brings water from elsewhere. A row with municipality_code applies to that municipality only (some plans describe intakes town by town); a row without it applies to every municipality of the unit. Reservoirs in MITECO''s weekly bulletin carry reservoir_id, so their levels can be joined.';
COMMENT ON COLUMN embalses.ref.supply_sources.supply_unit_id IS 'Supply unit (ref.supply_units).';
COMMENT ON COLUMN embalses.ref.supply_sources.municipality_code IS 'Set when the source applies to one municipality of the unit only; null when it applies to the whole unit.';
COMMENT ON COLUMN embalses.ref.supply_sources.source_rank IS 'Order in which the plan lists the source, 1 first.';
COMMENT ON COLUMN embalses.ref.supply_sources.source_type IS 'reservoir, river (any watercourse: río, arroyo, garganta…), aquifer (groundwater), spring, desalination, transfer, or network (a supplier''s network that brings water from its own sources, such as Canal de Isabel II).';
COMMENT ON COLUMN embalses.ref.supply_sources.source_name IS 'Name as the plan gives it ("Picadas", "río Tiétar", "Talavera - Picadas II"); null when the plan does not name it.';
COMMENT ON COLUMN embalses.ref.supply_sources.role IS 'main (the ordinary source), backup (reinforcement in dry periods or emergencies) or minor (a small part of the unit only).';
COMMENT ON COLUMN embalses.ref.supply_sources.reservoir_id IS 'The reservoir in MITECO''s weekly bulletin (ref.reservoirs), when the source is one of them. Smaller reservoirs have none.';
COMMENT ON COLUMN embalses.ref.supply_sources.network_unit_id IS 'For network and transfer sources: the network''s own row in ref.supply_units (unit_type network), whose sources say where that network takes its water. Follow it to reach the reservoirs behind a network.';
COMMENT ON COLUMN embalses.ref.supply_sources.water_body_code IS 'Code of the surface or groundwater body (masa de agua) when the plan gives it.';
COMMENT ON COLUMN embalses.ref.supply_sources.share_pct IS 'Share of the unit''s water from this source, 0–100, when the plan gives it.';
COMMENT ON COLUMN embalses.ref.supply_sources.confidence IS 'auto (read from the plan by rule), review (read, but doubtful: see notes) or reviewed (written or checked by hand against the cited document).';
COMMENT ON COLUMN embalses.ref.supply_sources.notes IS 'Short remarks of ours, in English. The plan''s wording is in ref.municipality_supply.intake_description.';
COMMENT ON COLUMN embalses.ref.supply_sources.source IS 'Key of the source (ph-tajo-2022-2027, …).';
