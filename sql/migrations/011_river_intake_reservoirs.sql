-- Reservoirs upstream of a river intake: where a basin plan says a town takes its water from a river (and names no
-- reservoir), the bulletin reservoirs on that river whose water passes the town. An estimate, kept apart from what the
-- plans state, and marked as such wherever it is used (now.municipality_path, now.municipality_water, the page).
-- Loaded by sql/reference/river_intakes.sql.

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.river_intake_reservoirs (
  municipality_code VARCHAR,
  supply_unit_id VARCHAR,
  source_name VARCHAR,
  reservoir_id INTEGER,
  distance_km DOUBLE,
  method VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.river_intake_reservoirs IS 'Estimated, not stated by any plan: for a municipality whose supply takes water from a river (ref.supply_sources, source_type river) and that has no bulletin reservoir behind it otherwise, the bulletin reservoirs on a river of the same name, in the same basin district, whose water passes within 8 km of the municipality on its way down the river network (HydroSHEDS HydroRIVERS). Regulated tributaries are not included. One row per municipality, intake and reservoir. Peninsula only.';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.municipality_code IS 'INE municipality code (ref.municipalities).';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.supply_unit_id IS 'The supply unit whose river source this is (ref.supply_units).';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.source_name IS 'The river, as the plan names it (ref.supply_sources.source_name): "río Mero".';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.reservoir_id IS 'Bulletin reservoir upstream on that river (ref.reservoirs).';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.distance_km IS 'Closest distance from the river below the dam to the municipality''s point (ref.municipalities longitude, latitude), km. The point stands in for the intake, whose place the plans do not give.';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.method IS 'How the link was made: river-name-downstream-8km.';
COMMENT ON COLUMN embalses.ref.river_intake_reservoirs.source IS 'Key of the sources (ph-2022-2027 + hydrorivers).';

ALTER TABLE embalses."now".municipality_path ADD COLUMN river_reservoir_ids INTEGER[];
COMMENT ON COLUMN embalses."now".municipality_path.river_reservoir_ids IS 'For a river source: bulletin reservoirs upstream of the intake on that river (ref.river_intake_reservoirs). An estimate, not stated by the plan.';
ALTER TABLE embalses."now".municipality_water ADD COLUMN river_reservoir_ids INTEGER[];
COMMENT ON COLUMN embalses."now".municipality_water.river_reservoir_ids IS 'Estimated: bulletin reservoirs upstream of the municipality''s river intakes (ref.river_intake_reservoirs), used only where no plan names a reservoir behind its supply. They count in the levels.';
