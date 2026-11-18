-- The path of each municipality's water as rows, rebuilt hourly by sql/now/municipality_path.sql and written in
-- municipality order, so a reader that filters on municipality_code skips most of the file. Not partitioned: a sink
-- writes an unpartitioned table (or a format-version 3 table partitioned by time).

-- lhbox: format-version=2
CREATE TABLE IF NOT EXISTS embalses."now".municipality_path (
  province_code VARCHAR,
  municipality_code VARCHAR,
  depth INTEGER,
  id VARCHAR,
  unit VARCHAR,
  type VARCHAR,
  doc VARCHAR,
  url VARCHAR,
  source_type VARCHAR,
  source_name VARCHAR,
  reservoir_id INTEGER,
  network_unit_id VARCHAR,
  role VARCHAR
);
COMMENT ON TABLE embalses."now".municipality_path IS 'Where each municipality''s tap water comes from, step by step: its supply units and their sources (depth 0), then the sources of each network or transfer they draw on (depth 1, 2 …). One row per unit and source. Rebuilt hourly inside LakehouseBox by sql/now/municipality_path.sql from ref.municipality_supply, ref.supply_units and ref.supply_sources, in municipality order.';
COMMENT ON COLUMN embalses."now".municipality_path.province_code IS 'INE province code, the first two digits of municipality_code.';
COMMENT ON COLUMN embalses."now".municipality_path.municipality_code IS 'INE municipality code (ref.municipalities).';
COMMENT ON COLUMN embalses."now".municipality_path.depth IS '0: a supply unit of the municipality; 1 and more: a network or transfer reached through the units above it.';
COMMENT ON COLUMN embalses."now".municipality_path.id IS 'Supply unit or network (ref.supply_units.supply_unit_id).';
COMMENT ON COLUMN embalses."now".municipality_path.unit IS 'Its name, as the basin plan or the network gives it.';
COMMENT ON COLUMN embalses."now".municipality_path.type IS 'urban or network (ref.supply_units.unit_type).';
COMMENT ON COLUMN embalses."now".municipality_path.doc IS 'The document it was read from.';
COMMENT ON COLUMN embalses."now".municipality_path.url IS 'Where that document is published.';
COMMENT ON COLUMN embalses."now".municipality_path.source_type IS 'reservoir, river, aquifer, spring, desalination, transfer, reclaimed or network; null when the plan names no source.';
COMMENT ON COLUMN embalses."now".municipality_path.source_name IS 'The source, as the plan names it.';
COMMENT ON COLUMN embalses."now".municipality_path.reservoir_id IS 'Bulletin reservoir (ref.reservoirs), for a reservoir source.';
COMMENT ON COLUMN embalses."now".municipality_path.network_unit_id IS 'For a network or transfer source: the unit whose own sources follow at the next depth.';
COMMENT ON COLUMN embalses."now".municipality_path.role IS 'backup for a source used only in droughts or emergencies; otherwise null.';
