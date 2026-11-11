-- Build the ref.* tables of the embalses catalog as GeoParquet in data/build/.
-- Run from the project root:  duckdb < sql/reference/build_reference.sql
-- Inputs (official sources only):
--   data/raw/arcgis/*.geojson          MITECO ArcGIS services (tools/fetch_arcgis.py)
--   data/raw/aemet/stations.json       AEMET station inventory (tools/fetch_aemet_stations.py)
--   data/geo/hydrosheds/*              HydroRIVERS / HydroBASINS (HydroSHEDS, CC-BY 4.0)
--   data/derived/reservoir_hydrology.parquet, reservoir_upstream_units.parquet
--       dam snapping + upstream tracing (sql/reference/catchments/*.sql)
load spatial;
set geometry_always_xy = true;

-- ───────────────────────────── basins ─────────────────────────────
create or replace table basin_meta(miteco_code varchar, basin_id varchar, basin_name varchar, basin_name_en varchar,
                                   authority_name varchar, saih_network varchar);
insert into basin_meta values
 ('11','ES010','Miño-Sil','Minho-Sil','Confederación Hidrográfica del Miño-Sil','saih-minosil'),
 ('14','ES014','Galicia-Costa','Galician Coast','Augas de Galicia',null),
 ('17','ES017','Cantábrico Oriental','Eastern Cantabrian','Confederación Hidrográfica del Cantábrico; Agencia Vasca del Agua (URA)','saih-cantabrico'),
 ('18','ES018','Cantábrico Occidental','Western Cantabrian','Confederación Hidrográfica del Cantábrico','saih-cantabrico'),
 ('21','ES020','Duero','Douro','Confederación Hidrográfica del Duero','saih-duero'),
 ('31','ES030','Tajo','Tagus','Confederación Hidrográfica del Tajo','saih-tajo'),
 ('40','ES040','Guadiana','Guadiana','Confederación Hidrográfica del Guadiana','saih-guadiana'),
 ('51','ES050','Guadalquivir','Guadalquivir','Confederación Hidrográfica del Guadalquivir','saih-guadalquivir'),
 ('61','ES060','Cuencas Mediterráneas Andaluzas','Andalusian Mediterranean Basins','Junta de Andalucía','saih-hidrosur'),
 ('63','ES063','Guadalete y Barbate','Guadalete and Barbate','Junta de Andalucía','saih-hidrosur'),
 ('64','ES064','Tinto, Odiel y Piedras','Tinto, Odiel and Piedras','Junta de Andalucía','saih-hidrosur'),
 ('71','ES070','Segura','Segura','Confederación Hidrográfica del Segura','saih-segura'),
 ('81','ES080','Júcar','Júcar','Confederación Hidrográfica del Júcar','saih-jucar'),
 ('91','ES091','Ebro','Ebro','Confederación Hidrográfica del Ebro','saih-ebro'),
 ('101','ES100','Cuencas Internas de Cataluña','Internal Basins of Catalonia','Agència Catalana de l''Aigua','aca'),
 ('111','ES110','Islas Baleares','Balearic Islands','Govern de les Illes Balears',null),
 ('121','ES120','Gran Canaria','Gran Canaria','Consejo Insular de Aguas de Gran Canaria',null),
 ('122','ES122','Fuerteventura','Fuerteventura','Consejo Insular de Aguas de Fuerteventura',null),
 ('123','ES123','Lanzarote','Lanzarote','Consejo Insular de Aguas de Lanzarote',null),
 ('124','ES124','Tenerife','Tenerife','Consejo Insular de Aguas de Tenerife',null),
 ('125','ES125','La Palma','La Palma','Consejo Insular de Aguas de La Palma',null),
 ('126','ES126','La Gomera','La Gomera','Consejo Insular de Aguas de La Gomera',null),
 ('127','ES127','El Hierro','El Hierro','Consejo Insular de Aguas de El Hierro',null),
 ('150','ES150','Ceuta','Ceuta','Confederación Hidrográfica del Guadalquivir',null),
 ('160','ES160','Melilla','Melilla','Confederación Hidrográfica del Guadalquivir',null);

create or replace table basins as
select m.basin_id, m.miteco_code, m.basin_name, m.basin_name_en, m.authority_name, m.saih_network,
       round(st_area_spheroid(d.geom) / 1e6, 1) as area_km2,
       st_buffer(d.geom, 0) as geometry,   -- the server-simplified outlines self-intersect; buffer(0) repairs them
       'miteco-arcgis' as source
from st_read('data/raw/arcgis/basin_districts.geojson') d
join basin_meta m on m.miteco_code = d.COD_DEMAR;

-- ───────────────────────────── catchments (HydroBASINS L12) ─────────────────────────────
create or replace table catchments as
with c as (
  select HYBAS_ID::bigint catchment_id, nullif(NEXT_DOWN, 0)::bigint downstream_catchment_id, PFAF_ID::varchar pfafstetter_code,
         SUB_AREA::double local_area_km2, UP_AREA::double upstream_area_km2, ENDO > 0 as is_endorheic, geom as geometry
  from st_read('data/geo/hydrosheds/hybas/hybas_eu_lev12_v1c.shp')
  where st_intersects(geom, st_makeenvelope(-9.6, 35.8, 4.6, 43.9))
)
select c.catchment_id, c.downstream_catchment_id, c.pfafstetter_code, b.basin_id,
       c.local_area_km2, c.upstream_area_km2, c.is_endorheic, c.geometry, 'hydrobasins' as source
from c
join basins b on st_intersects(b.geometry, st_pointonsurface(c.geometry));   -- Spanish districts only

-- ───────────────────────────── rivers (HydroRIVERS) ─────────────────────────────
create or replace table rivers_named as   -- names from MITECO's main rivers where a segment runs along one
select null::int as river_segment_id, null::varchar as river_name where false;
create or replace table rivers as
select r.HYRIV_ID::bigint river_segment_id, nullif(r.NEXT_DOWN, 0)::bigint downstream_segment_id,
       null::varchar river_name, r.ORD_STRA::int stream_order, r.LENGTH_KM::double length_km,
       r.UPLAND_SKM::double upstream_area_km2, r.DIS_AV_CMS::double mean_flow_m3s,
       r.HYBAS_L12::bigint catchment_id, c.basin_id, r.geometry, 'hydrorivers' as source
from 'data/geo/hydrosheds/rivers_iberia.parquet' r
join catchments c on c.catchment_id = r.HYBAS_L12;

-- ───────────────────────────── reservoirs ─────────────────────────────
create or replace table bulletin as
select EMBALSE_ID::int reservoir_id, embalse_nombre reservoir_name, ambito_nombre bulletin_area_name,
       agua_total::double capacity_hm3, (electrico_flag::int = 1) is_hydroelectric,
       nullif(energia_total, 0)::double energy_capacity_gwh, geom dam_location
from st_read('data/raw/arcgis/bulletin_reservoirs.geojson');

create or replace table dams as select * from st_read('data/raw/arcgis/dam_inventory.geojson');
create or replace table hydro as select * from 'data/derived/reservoir_hydrology.parquet';

-- water outlines: the outline under or nearest the dam point, preferring a matching name
create or replace table outline_pick as
with o as (select ETIQUETA lbl, geom from st_read('data/raw/arcgis/reservoir_outlines.geojson')),
c as (
  select b.reservoir_id, o.lbl, o.geom,
         st_distance_sphere(b.dam_location, st_closestpoint(o.geom, b.dam_location)) d,
         jaro_winkler_similarity(lower(strip_accents(b.reservoir_name)), lower(strip_accents(coalesce(o.lbl, '')))) sim
  from bulletin b join o on st_dwithin(b.dam_location, o.geom, 0.02))
select * from c where d < 1000
qualify row_number() over (partition by reservoir_id order by (sim > 0.75) desc, d, sim desc) = 1;

create or replace table reservoirs as
select b.reservoir_id, b.reservoir_name, b.bulletin_area_name, bs.basin_id, b.capacity_hm3, b.is_hydroelectric,
       b.energy_capacity_gwh,
       d.CODIGO dam_inventory_code, d.NOMBRE dam_name, d.CAUCE river_name, d.PROVINCIA province, d.CCAA region,
       list_filter(string_split(replace(d.USO, chr(13), ''), chr(10)), lambda x: trim(x) <> '') uses,
       d.TIPO dam_type,
       h.upstream_area_km2_best catchment_area_km2,
       h.inv_sup_cuenca inventory_catchment_area_km2,
       nullif(try_cast(trim(d.AP_M_ANUAL::varchar) as double), 0) mean_annual_inflow_hm3,
       case when op.geom is not null then round(st_area_spheroid(op.geom) / 1e4, 1) end surface_area_ha,
       h.hyriv_id::bigint river_segment_id,
       h.hybas_l12_id::bigint catchment_id,
       coalesce(h.n_gauges, 0)::int gauges_upstream,
       list_filter([
         case when coalesce(h.n_gauges, 0) = 0 then 'no_upstream_gauges' end,
         case when h.upstream_area_km2_best < 50 then 'small_catchment' end,
         case when h.hyriv_id is null then 'no_river_segment' end,
         case when h.inv_sup_cuenca > 0 and abs(h.upstream_area_km2_best - h.inv_sup_cuenca) / h.inv_sup_cuenca > 0.25
              then 'inventory_catchment_area_differs' end,
         case when op.geom is null then 'no_water_outline' end
       ], lambda x: x is not null) quality_flags,
       b.dam_location,
       op.geom water_outline,
       'auto' link_status,
       'miteco-arcgis' as source
from bulletin b
left join hydro h on h.EMBALSE_ID = b.reservoir_id
left join dams d on d.ID_INFRAES = h.inv_dam_id
left join outline_pick op using (reservoir_id)
-- the basin the dam lies in; a dam on the border can fall just outside the simplified outline: take the nearest
left join (select b2.reservoir_id, bs2.basin_id from bulletin b2, basins bs2
           qualify row_number() over (partition by b2.reservoir_id order by st_distance(bs2.geometry, b2.dam_location)) = 1
          ) bs on bs.reservoir_id = b.reservoir_id;

-- ───────────────────────────── reservoir_catchments ─────────────────────────────
create or replace table up as
select u.reservoir_id, u.catchment_id, u.area_km2
from 'data/derived/reservoir_upstream_units.parquet' u where u.ENDO = 0;
create or replace table reservoir_catchments as
with tot as (select reservoir_id, sum(area_km2) total from up group by 1),
-- another bulletin reservoir between this unit and the dam: its own upstream set contains the unit,
-- and its dam unit lies inside this reservoir's set. Take the nearest (smallest) one.
inner_res as (
  select a.reservoir_id, a.catchment_id, r2.reservoir_id upstream_reservoir_id, t2.total
  from up a
  join up b on b.catchment_id = a.catchment_id and b.reservoir_id <> a.reservoir_id
  join reservoirs r2 on r2.reservoir_id = b.reservoir_id
  join up c on c.reservoir_id = a.reservoir_id and c.catchment_id = r2.catchment_id
  join tot t2 on t2.reservoir_id = b.reservoir_id
  join tot t1 on t1.reservoir_id = a.reservoir_id
  where t2.total < t1.total
  qualify row_number() over (partition by a.reservoir_id, a.catchment_id order by t2.total) = 1)
select a.reservoir_id, a.catchment_id, (a.catchment_id = r.catchment_id) is_dam_unit, a.area_km2,
       round(a.area_km2 / t.total, 6) area_weight, i.upstream_reservoir_id
from up a join tot t using (reservoir_id)
join reservoirs r using (reservoir_id)
left join inner_res i on i.reservoir_id = a.reservoir_id and i.catchment_id = a.catchment_id;

-- ───────────────────────────── stations ─────────────────────────────
create or replace table saih_net(idsaih varchar, network varchar, operator varchar, update_interval_minutes int);
insert into saih_net values
 ('TAJO','saih-tajo','Confederación Hidrográfica del Tajo',60), ('EBRO','saih-ebro','Confederación Hidrográfica del Ebro',15),
 ('DUERO','saih-duero','Confederación Hidrográfica del Duero',60), ('GUADIANA','saih-guadiana','Confederación Hidrográfica del Guadiana',5),
 ('GUADALQUIVIR','saih-guadalquivir','Confederación Hidrográfica del Guadalquivir',60), ('SEGURA','saih-segura','Confederación Hidrográfica del Segura',5),
 ('JUCAR','saih-jucar','Confederación Hidrográfica del Júcar',5), ('CANTABRICO','saih-cantabrico','Confederación Hidrográfica del Cantábrico',15),
 ('NORTEI','saih-minosil','Confederación Hidrográfica del Miño-Sil',30), ('AGENCIAANDALUZAAGUA','saih-hidrosur','Junta de Andalucía',60),
 ('ACA','aca','Agència Catalana de l''Aigua',1440);

create or replace table saih_pts as
select 'reservoir' kind, IDSAIH, trim(IDPUNTO) idpunto, null descr, TIPO, geom from st_read('data/raw/arcgis/saih_reservoir_points.geojson')
union all select 'river_gauge', IDSAIH, trim(IDPUNTO), null, TIPO, geom from st_read('data/raw/arcgis/saih_river_gauges.geojson')
union all select 'rain_gauge', IDSAIH, trim(IDPUNTO), DESCRIPCIO, TIPO, geom from st_read('data/raw/arcgis/saih_rain_gauges.geojson');

create or replace table saih_norm as
select p.*, n.network, n.operator, n.update_interval_minutes,
  case
    when p.IDSAIH in ('EBRO','NORTEI','CANTABRICO') then regexp_extract(p.idpunto, '^([A-Z]?[0-9]{3,4})', 1)
    when p.IDSAIH = 'ACA' then left(p.idpunto, 6)
    when p.IDSAIH = 'TAJO' then regexp_extract(p.idpunto, '^(\S+)', 1)            -- 'E_01 ENTREPENAS' -> E_01
    when p.IDSAIH = 'GUADALQUIVIR' then regexp_extract(p.idpunto, '^([^ _]+)', 1)  -- 'E01_TRANCO_BEAS' -> E01
    when p.IDSAIH = 'DUERO' then regexp_extract(p.idpunto, '^([A-Z]*[0-9]+)', 1)
    when p.IDSAIH = 'GUADIANA' then p.idpunto
    else regexp_replace(upper(p.idpunto), '\s+', ' ', 'g')
  end native_code,
  case
    when p.IDSAIH = 'TAJO' then nullif(trim(regexp_replace(p.idpunto, '^\S+\s*', '')), '')
    when p.IDSAIH = 'GUADALQUIVIR' then nullif(trim(replace(regexp_replace(p.idpunto, '^[^ _]+[ _]', ''), '_', ' ')), p.idpunto)
    when p.IDSAIH in ('JUCAR','SEGURA','AGENCIAANDALUZAAGUA') then regexp_replace(p.idpunto, '\s+', ' ', 'g')
    when p.descr is not null and p.descr <> p.idpunto then p.descr
  end station_name,
  case
    when p.TIPO ilike 'Nivel embalse%' or p.TIPO ilike 'Nivel r%' then 'water_level'
    when p.TIPO ilike 'Volumen%' then 'stored_volume'
    when p.TIPO ilike 'Capacidad%' then 'fill_pct'
    when p.TIPO ilike 'Caudal%' then 'flow'
    when p.TIPO ilike 'Pluviom%' then 'precipitation'
  end as variable
from saih_pts p join saih_net n on n.idsaih = p.IDSAIH;

create or replace table saih_st as
select network || ':' || native_code station_id, network, operator, native_code,
       any_value(station_name) filter (where station_name is not null) station_name,
       case when bool_or(kind = 'reservoir') then 'reservoir' when bool_or(kind = 'river_gauge') then 'river_gauge' else 'rain_gauge' end station_type,
       list_sort(list_distinct(list(variable) filter (where variable is not null))) variables,
       any_value(update_interval_minutes) update_interval_minutes,
       st_centroid(st_collect(list(geom))) as location
from saih_norm where native_code is not null and native_code <> ''
group by all;

create or replace table aemet_st as
select 'aemet:' || native_code station_id, 'aemet' network, 'AEMET' as operator, native_code, station_name,
       'weather_station' station_type,
       ['air_temperature','precipitation','relative_humidity','wind'] variables,
       60 update_interval_minutes, elevation_m, st_point(lon, lat) as location
from read_json('data/raw/aemet/stations.json');

create or replace table stations_all as
select station_id, network, operator, native_code, station_name, station_type, variables,
       update_interval_minutes, null::double elevation_m, location from saih_st
union all
select station_id, network, operator, native_code, station_name, station_type, variables,
       update_interval_minutes, elevation_m, location from aemet_st;

create or replace table station_reservoir as
select s.station_id, r.reservoir_id
from stations_all s join reservoirs r on st_dwithin(s.location, r.dam_location, 0.03)
where s.station_type = 'reservoir'
  and st_distance_sphere(s.location, r.dam_location) < 1500
qualify row_number() over (partition by s.station_id order by st_distance_sphere(s.location, r.dam_location)) = 1;

create or replace table stations as
select s.station_id, s.network, s.operator, s.native_code, coalesce(s.station_name, rr.reservoir_name) station_name, s.station_type, s.variables,
       sr.reservoir_id, b.basin_id, c.catchment_id, s.elevation_m, s.update_interval_minutes,
       now()::timestamptz first_seen_at, null::timestamptz last_seen_at,
       s.location, case when s.network = 'aemet' then 'aemet-opendata' else 'miteco-arcgis' end as source
from stations_all s
left join station_reservoir sr using (station_id)
left join reservoirs rr on rr.reservoir_id = sr.reservoir_id
left join basins b on st_intersects(b.geometry, s.location)
left join catchments c on st_intersects(c.geometry, s.location);

-- ───────────────────────────── write ─────────────────────────────
copy (select * from basins order by basin_id) to 'data/build/ref_basins.parquet' (format parquet);
copy (select * from catchments order by catchment_id) to 'data/build/ref_catchments.parquet' (format parquet);
copy (select * from rivers order by river_segment_id) to 'data/build/ref_rivers.parquet' (format parquet);
copy (select * from reservoirs order by reservoir_id) to 'data/build/ref_reservoirs.parquet' (format parquet);
copy (select * from reservoir_catchments order by reservoir_id, catchment_id) to 'data/build/ref_reservoir_catchments.parquet' (format parquet);
copy (select * from stations order by station_id) to 'data/build/ref_stations.parquet' (format parquet);

select 'basins' t, count(*) n from basins union all select 'catchments', count(*) from catchments
union all select 'rivers', count(*) from rivers union all select 'reservoirs', count(*) from reservoirs
union all select 'reservoir_catchments', count(*) from reservoir_catchments union all select 'stations', count(*) from stations;
