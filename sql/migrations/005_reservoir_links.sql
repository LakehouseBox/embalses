-- How the reservoirs are connected: one row per direct link, water flowing from → to.
-- River links are computed from the river network (sql/reference/reservoir_links.sql); canals and transfers
-- are added from the river-basin plans, one reviewed row each.

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.reservoir_links (
  from_reservoir_id INTEGER,
  to_reservoir_id INTEGER,
  link_type VARCHAR,
  link_name VARCHAR,
  length_km DOUBLE,
  river_segments INTEGER,
  path GEOMETRY('EPSG:4326'),
  confidence VARCHAR,
  notes VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.reservoir_links IS 'How the reservoirs are connected, one row per direct link, water flowing from from_reservoir_id to to_reservoir_id. River links join each reservoir to the next one downstream on the river network, so following them upstream gives every reservoir that drains into a given one. Canal and transfer links (added from the river-basin plans) join reservoirs that no river connects. A reservoir with no row as from_reservoir_id drains to the sea or out of Spain without passing another bulletin reservoir.';
COMMENT ON COLUMN embalses.ref.reservoir_links.from_reservoir_id IS 'Reservoir the water leaves (ref.reservoirs).';
COMMENT ON COLUMN embalses.ref.reservoir_links.to_reservoir_id IS 'Reservoir the water reaches (ref.reservoirs).';
COMMENT ON COLUMN embalses.ref.reservoir_links.link_type IS 'river (the next reservoir downstream on the river network), canal or transfer (built conduits, from the river-basin plans).';
COMMENT ON COLUMN embalses.ref.reservoir_links.link_name IS 'Name of the canal or transfer; empty for river links.';
COMMENT ON COLUMN embalses.ref.reservoir_links.length_km IS 'Length of the river path between the two dams, km (HydroRIVERS); for canals, the conduit length when the source gives it.';
COMMENT ON COLUMN embalses.ref.reservoir_links.river_segments IS 'River links: HydroRIVERS segments walked from one dam to the next.';
COMMENT ON COLUMN embalses.ref.reservoir_links.path IS 'River links: the river line from the upper dam to the lower one, LineString or MultiLineString, EPSG:4326. Null for canals whose route is not published.';
COMMENT ON COLUMN embalses.ref.reservoir_links.confidence IS 'auto (computed, consistent), review (computed but doubtful: see notes) or reviewed (checked by hand).';
COMMENT ON COLUMN embalses.ref.reservoir_links.notes IS 'Why a link needs review, or what the reviewer found.';
COMMENT ON COLUMN embalses.ref.reservoir_links.source IS 'Key of the source: hydrorivers for river links; the plan and annex for canals and transfers.';
