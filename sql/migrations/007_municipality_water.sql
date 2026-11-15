-- How full the reservoirs behind each municipality's tap water are, rebuilt hourly by sql/now/municipality_water.sql.

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".municipality_water (
  municipality_code VARCHAR,
  municipality_name VARCHAR,
  province_name VARCHAR,
  population INTEGER,
  supply_unit_names VARCHAR[],
  source_types VARCHAR[],
  source_reservoir_ids INTEGER[],
  upstream_reservoir_ids INTEGER[],
  reservoirs INTEGER,
  stored_volume_hm3 DOUBLE,
  capacity_hm3 DOUBLE,
  fill_pct DOUBLE,
  fill_pct_same_week_last_year DOUBLE,
  fill_pct_10y_average DOUBLE,
  as_of TIMESTAMP WITH TIME ZONE
);
COMMENT ON TABLE embalses."now".municipality_water IS 'One row per municipality: where its tap water comes from and how full the reservoirs behind it are together. Reservoirs counted are those its supply units take water from (directly or through a network such as Canal de Isabel II or a transfer) plus every reservoir upstream of them on the river network; the level is weighted by capacity, so a large reservoir counts for more than a small one. Municipalities served only by groundwater, desalination or rivers without a bulletin reservoir have no level. Rebuilt hourly inside LakehouseBox by sql/now/municipality_water.sql from ref.municipality_supply, ref.supply_sources, ref.reservoir_links and now.reservoir_status.';
COMMENT ON COLUMN embalses."now".municipality_water.municipality_code IS 'INE municipality code (ref.municipalities).';
COMMENT ON COLUMN embalses."now".municipality_water.municipality_name IS 'Name as people write it.';
COMMENT ON COLUMN embalses."now".municipality_water.province_name IS 'Province.';
COMMENT ON COLUMN embalses."now".municipality_water.population IS 'Official population (ref.municipalities).';
COMMENT ON COLUMN embalses."now".municipality_water.supply_unit_names IS 'Supply units serving the municipality, as the river-basin plans name them; empty when no loaded plan places it.';
COMMENT ON COLUMN embalses."now".municipality_water.source_types IS 'Kinds of source its water comes from, through networks too: reservoir, river, aquifer, spring, desalination, transfer, reclaimed.';
COMMENT ON COLUMN embalses."now".municipality_water.source_reservoir_ids IS 'Bulletin reservoirs the supply takes water from (ref.reservoirs), directly or through networks and transfers.';
COMMENT ON COLUMN embalses."now".municipality_water.upstream_reservoir_ids IS 'Bulletin reservoirs upstream of those on the river network (ref.reservoir_links), whose water flows down to them.';
COMMENT ON COLUMN embalses."now".municipality_water.reservoirs IS 'Reservoirs counted in the level: source and upstream ones with a current reading.';
COMMENT ON COLUMN embalses."now".municipality_water.stored_volume_hm3 IS 'Water stored in them now, hm³ (now.reservoir_status).';
COMMENT ON COLUMN embalses."now".municipality_water.capacity_hm3 IS 'Their total capacity, hm³.';
COMMENT ON COLUMN embalses."now".municipality_water.fill_pct IS 'stored_volume_hm3 ÷ capacity_hm3, %: how full the water behind this tap is, a large reservoir weighing more than a small one.';
COMMENT ON COLUMN embalses."now".municipality_water.fill_pct_same_week_last_year IS 'The same, for the same week a year ago, capacity-weighted, %.';
COMMENT ON COLUMN embalses."now".municipality_water.fill_pct_10y_average IS 'The same week averaged over the previous 10 years, capacity-weighted, %.';
COMMENT ON COLUMN embalses."now".municipality_water.as_of IS 'When the reservoir levels were last updated (now.reservoir_status), UTC.';
