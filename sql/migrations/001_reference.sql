-- Reference tables: places (basins, catchments, rivers, reservoirs, stations) and the rain grid.
-- Migration for the embalses catalog. Proposed `lhbox migrate` format (tablemere PLAN 21): plain DuckDB DDL,
-- applied once in file order; `-- lhbox:` lines carry what DuckDB DDL cannot express (format version, partitioning).
-- Generated from the deployed catalog on 2026-11-11.

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.basins (
  basin_id VARCHAR,
  miteco_code VARCHAR,
  basin_name VARCHAR,
  basin_name_en VARCHAR,
  authority_name VARCHAR,
  saih_network VARCHAR,
  area_km2 DOUBLE,
  geometry GEOMETRY('EPSG:4326'),
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.basins IS 'Spain''s 25 river basin districts (demarcaciones hidrográficas), one row each. Each is managed by one authority, most with their own SAIH real-time network. Source: MITECO ArcGIS ''Demarcaciones'' (outlines simplified to ~200 m). Static; refreshed when MITECO republishes.';
COMMENT ON COLUMN embalses.ref.basins.basin_id IS 'EU water-framework district code, e.g. ES030 (Tajo). Key.';
COMMENT ON COLUMN embalses.ref.basins.miteco_code IS 'MITECO''s own district code, e.g. 31 (Tajo).';
COMMENT ON COLUMN embalses.ref.basins.basin_name IS 'Spanish name, e.g. Tajo.';
COMMENT ON COLUMN embalses.ref.basins.basin_name_en IS 'English name, e.g. Tagus.';
COMMENT ON COLUMN embalses.ref.basins.authority_name IS 'Body that manages the district and its SAIH network.';
COMMENT ON COLUMN embalses.ref.basins.saih_network IS 'Network key used in ref.stations.network for this district''s live data (e.g. saih-tajo); null where there is none.';
COMMENT ON COLUMN embalses.ref.basins.area_km2 IS 'Land area of the district in km².';
COMMENT ON COLUMN embalses.ref.basins.geometry IS 'District outline, MultiPolygon, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.basins.source IS 'Key of the source (miteco-arcgis).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.catchments (
  catchment_id BIGINT,
  downstream_catchment_id BIGINT,
  pfafstetter_code VARCHAR,
  basin_id VARCHAR,
  local_area_km2 DOUBLE,
  upstream_area_km2 DOUBLE,
  is_endorheic BOOLEAN,
  geometry GEOMETRY('EPSG:4326'),
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.catchments IS 'Small drainage units (HydroBASINS level 12, ~130 km² median) covering Spain''s river basin districts, each linked to the unit it drains into. Used to collect all land upstream of a reservoir. Source: HydroSHEDS HydroBASINS v1c (CC BY 4.0). Static.';
COMMENT ON COLUMN embalses.ref.catchments.catchment_id IS 'HydroBASINS unit id (HYBAS_ID). Key.';
COMMENT ON COLUMN embalses.ref.catchments.downstream_catchment_id IS 'Unit this one drains into; null at the sea or an inland sink.';
COMMENT ON COLUMN embalses.ref.catchments.pfafstetter_code IS 'Hierarchical Pfafstetter code: shared prefixes mean nested catchments.';
COMMENT ON COLUMN embalses.ref.catchments.basin_id IS 'River basin district (ref.basins) the unit belongs to.';
COMMENT ON COLUMN embalses.ref.catchments.local_area_km2 IS 'Area of this unit alone, km².';
COMMENT ON COLUMN embalses.ref.catchments.upstream_area_km2 IS 'Total area draining through this unit, itself included, km².';
COMMENT ON COLUMN embalses.ref.catchments.is_endorheic IS 'True for units draining to an inland sink rather than the sea; excluded from upstream areas.';
COMMENT ON COLUMN embalses.ref.catchments.geometry IS 'Unit outline, Polygon, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.catchments.source IS 'Key of the source (hydrobasins).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.rivers (
  river_segment_id BIGINT,
  downstream_segment_id BIGINT,
  river_name VARCHAR,
  stream_order INTEGER,
  length_km DOUBLE,
  upstream_area_km2 DOUBLE,
  mean_flow_m3s DOUBLE,
  catchment_id BIGINT,
  basin_id VARCHAR,
  geometry GEOMETRY,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.rivers IS 'River network for maps: one row per HydroRIVERS segment in Spain''s basin districts, with its size so line width can follow the river. Source: HydroSHEDS HydroRIVERS v1.0 (CC BY 4.0). Static.';
COMMENT ON COLUMN embalses.ref.rivers.river_segment_id IS 'HydroRIVERS segment id (HYRIV_ID). Key.';
COMMENT ON COLUMN embalses.ref.rivers.downstream_segment_id IS 'Next segment downstream; null at the mouth.';
COMMENT ON COLUMN embalses.ref.rivers.river_name IS 'Official river name where matched (not yet filled).';
COMMENT ON COLUMN embalses.ref.rivers.stream_order IS 'Strahler order: 1 for headwater streams, rising as tributaries join.';
COMMENT ON COLUMN embalses.ref.rivers.length_km IS 'Segment length, km.';
COMMENT ON COLUMN embalses.ref.rivers.upstream_area_km2 IS 'Area draining through this segment, km².';
COMMENT ON COLUMN embalses.ref.rivers.mean_flow_m3s IS 'Long-term modelled mean flow (HydroSHEDS, 1971–2000), m³/s. For scale on the map, not a measurement.';
COMMENT ON COLUMN embalses.ref.rivers.catchment_id IS 'Catchment unit (ref.catchments) the segment lies in.';
COMMENT ON COLUMN embalses.ref.rivers.basin_id IS 'River basin district (ref.basins).';
COMMENT ON COLUMN embalses.ref.rivers.geometry IS 'Segment line, LineString, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.rivers.source IS 'Key of the source (hydrorivers).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.reservoirs (
  reservoir_id INTEGER,
  reservoir_name VARCHAR,
  bulletin_area_name VARCHAR,
  basin_id VARCHAR,
  capacity_hm3 DOUBLE,
  is_hydroelectric BOOLEAN,
  energy_capacity_gwh DOUBLE,
  dam_inventory_code VARCHAR,
  dam_name VARCHAR,
  river_name VARCHAR,
  province VARCHAR,
  region VARCHAR,
  uses VARCHAR[],
  dam_type VARCHAR,
  catchment_area_km2 DOUBLE,
  inventory_catchment_area_km2 DOUBLE,
  mean_annual_inflow_hm3 DOUBLE,
  surface_area_ha DOUBLE,
  river_segment_id BIGINT,
  catchment_id BIGINT,
  gauges_upstream INTEGER,
  quality_flags VARCHAR[],
  dam_location GEOMETRY('EPSG:4326'),
  water_outline GEOMETRY('EPSG:4326'),
  link_status VARCHAR,
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.reservoirs IS 'The 375 reservoirs in MITECO''s weekly reservoir bulletin (practically all of Spain''s stored water), one row each, enriched with the national dam inventory, the reservoir''s water outline and its upstream catchment. Key reservoir_id is MITECO''s EMBALSE_ID, stable since 1988. Links to the inventory, outlines and catchments were made automatically by location, name and capacity; see quality_flags. Sources: MITECO ArcGIS (Embalses_Mapa, UP_Presas_y_embalses, Láminas_Embalses), HydroSHEDS.';
COMMENT ON COLUMN embalses.ref.reservoirs.reservoir_id IS 'MITECO bulletin EMBALSE_ID, stable since 1988. Key.';
COMMENT ON COLUMN embalses.ref.reservoirs.reservoir_name IS 'Name as in the weekly bulletin.';
COMMENT ON COLUMN embalses.ref.reservoirs.bulletin_area_name IS 'Area the bulletin groups it under (ámbito); close to, but not the same as, the basin district.';
COMMENT ON COLUMN embalses.ref.reservoirs.basin_id IS 'River basin district the dam is in (ref.basins).';
COMMENT ON COLUMN embalses.ref.reservoirs.capacity_hm3 IS 'Capacity used by the weekly bulletin, hm³.';
COMMENT ON COLUMN embalses.ref.reservoirs.is_hydroelectric IS 'True when the bulletin also reports stored energy for it.';
COMMENT ON COLUMN embalses.ref.reservoirs.energy_capacity_gwh IS 'Energy the full reservoir could generate, GWh (bulletin).';
COMMENT ON COLUMN embalses.ref.reservoirs.dam_inventory_code IS 'Code of the main dam in MITECO''s national dam inventory.';
COMMENT ON COLUMN embalses.ref.reservoirs.dam_name IS 'Dam name in the inventory; can differ from the reservoir name (Alcántara''s dam is José María de Oriol).';
COMMENT ON COLUMN embalses.ref.reservoirs.river_name IS 'River dammed, as in the inventory.';
COMMENT ON COLUMN embalses.ref.reservoirs.province IS 'Province of the dam.';
COMMENT ON COLUMN embalses.ref.reservoirs.region IS 'Autonomous community of the dam.';
COMMENT ON COLUMN embalses.ref.reservoirs.uses IS 'Uses listed in the inventory (Abastecimiento, Riego, Hidroeléctrico, Defensa frente avenidas, …).';
COMMENT ON COLUMN embalses.ref.reservoirs.dam_type IS 'Construction type, from the inventory.';
COMMENT ON COLUMN embalses.ref.reservoirs.catchment_area_km2 IS 'Area draining into the dam, km², computed from HydroRIVERS at the dam''s river segment. Median error vs the inventory is 2% for catchments over 200 km²; preferred over inventory_catchment_area_km2.';
COMMENT ON COLUMN embalses.ref.reservoirs.inventory_catchment_area_km2 IS 'Catchment area as recorded in the dam inventory, km² (filled for about half; some values are wrong).';
COMMENT ON COLUMN embalses.ref.reservoirs.mean_annual_inflow_hm3 IS 'Average yearly inflow from the dam inventory, hm³/yr. Lets a storm be expressed as a share of a normal year.';
COMMENT ON COLUMN embalses.ref.reservoirs.surface_area_ha IS 'Area of the water outline (Láminas_Embalses), hectares.';
COMMENT ON COLUMN embalses.ref.reservoirs.river_segment_id IS 'HydroRIVERS segment the dam was snapped to (ref.rivers).';
COMMENT ON COLUMN embalses.ref.reservoirs.catchment_id IS 'Catchment unit the dam sits in (ref.catchments).';
COMMENT ON COLUMN embalses.ref.reservoirs.gauges_upstream IS 'Rain gauges (AEMET + SAIH) inside the upstream catchment. 0 means upstream rain is interpolated from outside.';
COMMENT ON COLUMN embalses.ref.reservoirs.quality_flags IS 'Caveats: no_upstream_gauges, small_catchment (<50 km²), no_river_segment, inventory_catchment_area_differs (>25%), no_water_outline.';
COMMENT ON COLUMN embalses.ref.reservoirs.dam_location IS 'Dam position from the bulletin, Point, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.reservoirs.water_outline IS 'Reservoir water surface, Polygon, EPSG:4326 (null for 7).';
COMMENT ON COLUMN embalses.ref.reservoirs.link_status IS 'How inventory, outline and catchment were attached: auto or reviewed.';
COMMENT ON COLUMN embalses.ref.reservoirs.source IS 'Key of the source (miteco-arcgis).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.reservoir_catchments (
  reservoir_id INTEGER,
  catchment_id BIGINT,
  is_dam_unit BOOLEAN,
  area_km2 DOUBLE,
  area_weight DOUBLE,
  upstream_reservoir_id INTEGER
);
COMMENT ON TABLE embalses.ref.reservoir_catchments IS 'Bridge table: for each bulletin reservoir, every catchment unit upstream of its dam (traced up the HydroRIVERS network). Makes ''rain over the land that drains into this reservoir'' a plain join: obs.precipitation → ref.stations.catchment_id → this table → reservoir. Endorheic units excluded.';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.reservoir_id IS 'Reservoir (ref.reservoirs).';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.catchment_id IS 'Catchment unit upstream of the dam (ref.catchments).';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.is_dam_unit IS 'True for the unit the dam sits in.';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.area_km2 IS 'Area of the unit, km².';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.area_weight IS 'Share of the reservoir''s total upstream area (sums to 1 per reservoir), for area-weighted rain.';
COMMENT ON COLUMN embalses.ref.reservoir_catchments.upstream_reservoir_id IS 'Nearest other bulletin reservoir between this unit and the dam, if any: water from here is regulated by it before arriving.';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.stations (
  station_id VARCHAR,
  network VARCHAR,
  operator VARCHAR,
  native_code VARCHAR,
  station_name VARCHAR,
  station_type VARCHAR,
  variables VARCHAR[],
  reservoir_id INTEGER,
  basin_id VARCHAR,
  catchment_id BIGINT,
  elevation_m DOUBLE,
  update_interval_minutes INTEGER,
  first_seen_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  location GEOMETRY('EPSG:4326'),
  source VARCHAR
);
COMMENT ON TABLE embalses.ref.stations IS 'Every measuring station in one register: AEMET weather stations (official inventory) and the SAIH real-time stations of each basin authority (MITECO''s national SAIH register): reservoirs, river gauges and rain gauges. One row per physical station per network; station_id is network:native_code. SiAR agro-weather stations to be added. Sources: AEMET OpenData, MITECO ArcGIS ''SAIH''.';
COMMENT ON COLUMN embalses.ref.stations.station_id IS 'network:native_code, unique across networks, e.g. saih-tajo:E_36, aemet:5769X. Key.';
COMMENT ON COLUMN embalses.ref.stations.network IS 'Network: aemet, aca, or saih-<basin> (saih-tajo, saih-ebro, …).';
COMMENT ON COLUMN embalses.ref.stations.operator IS 'Organisation that runs the station.';
COMMENT ON COLUMN embalses.ref.stations.native_code IS 'The station''s code in its own network, as its feed uses it (for Júcar, Segura and Andalusia the register uses names).';
COMMENT ON COLUMN embalses.ref.stations.station_name IS 'Name as published (for reservoir stations without one, the reservoir''s name).';
COMMENT ON COLUMN embalses.ref.stations.station_type IS 'reservoir, river_gauge, rain_gauge or weather_station.';
COMMENT ON COLUMN embalses.ref.stations.variables IS 'What it measures: water_level, stored_volume, fill_pct, flow, precipitation, air_temperature, relative_humidity, wind.';
COMMENT ON COLUMN embalses.ref.stations.reservoir_id IS 'Reservoir it measures (ref.reservoirs); set for reservoir stations within 1.5 km of a bulletin dam.';
COMMENT ON COLUMN embalses.ref.stations.basin_id IS 'River basin district (ref.basins).';
COMMENT ON COLUMN embalses.ref.stations.catchment_id IS 'Catchment unit it sits in (ref.catchments); drives upstream-rain calculations. Null outside the Iberian peninsula.';
COMMENT ON COLUMN embalses.ref.stations.elevation_m IS 'Station altitude, m (AEMET).';
COMMENT ON COLUMN embalses.ref.stations.update_interval_minutes IS 'How often its source publishes a new value.';
COMMENT ON COLUMN embalses.ref.stations.first_seen_at IS 'When it entered this register (UTC).';
COMMENT ON COLUMN embalses.ref.stations.last_seen_at IS 'Last time a feed returned a value for it (UTC); filled by the ingestion.';
COMMENT ON COLUMN embalses.ref.stations.location IS 'Station position, Point, EPSG:4326.';
COMMENT ON COLUMN embalses.ref.stations.source IS 'Key of the source (aemet-opendata, miteco-arcgis).';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.grid_cells (
  h3_cell VARCHAR,
  basin_id VARCHAR,
  cell_area_km2 DOUBLE,
  geometry GEOMETRY
);
COMMENT ON TABLE embalses.ref.grid_cells IS 'H3 resolution-6 cells (~37 km²) covering Spain''s river basin districts: the grid rain is interpolated onto (now.rain_grid). Built by sql/reference/grid.sql.';
COMMENT ON COLUMN embalses.ref.grid_cells.h3_cell IS 'H3 cell index (resolution 6), as a hex string. Key.';
COMMENT ON COLUMN embalses.ref.grid_cells.basin_id IS 'River basin district the cell centre lies in.';
COMMENT ON COLUMN embalses.ref.grid_cells.cell_area_km2 IS 'Cell area, km².';
COMMENT ON COLUMN embalses.ref.grid_cells.geometry IS 'Cell outline, Polygon, EPSG:4326.';

-- lhbox: format-version=3
CREATE TABLE IF NOT EXISTS embalses.ref.catchment_cells (
  catchment_id BIGINT,
  h3_cell VARCHAR,
  cell_weight DOUBLE
);
COMMENT ON TABLE embalses.ref.catchment_cells IS 'Which H3 grid cells make up each catchment unit, so gridded rain can be averaged over any catchment. Built by sql/reference/grid.sql.';
COMMENT ON COLUMN embalses.ref.catchment_cells.catchment_id IS 'Catchment unit (ref.catchments).';
COMMENT ON COLUMN embalses.ref.catchment_cells.h3_cell IS 'Grid cell (ref.grid_cells).';
COMMENT ON COLUMN embalses.ref.catchment_cells.cell_weight IS 'Weight of the cell within the unit (equal weights, summing to 1 per unit).';
