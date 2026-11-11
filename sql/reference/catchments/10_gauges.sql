load spatial;
create or replace table gauges as
select 'SAIH' src, IDPUNTO gid, st_transform(g4,'EPSG:4326','EPSG:3035',always_xy:=true) g from saih
union all select 'AEMET', idema, st_transform(g4,'EPSG:4326','EPSG:3035',always_xy:=true) from aemet where n_prec>0;
create or replace table g_unit as select g.src, g.gid, u.id unit from gauges g join l12 u on st_intersects(g.g, u.g);
-- nearest HydroRIVERS segment within the same L12 unit (approximates the segment's local catchment)
create or replace table g_seg as
select src, gid, arg_min(r.HYRIV_ID, st_distance(g.g, r.g)) seg
from gauges g join g_unit gu using(src,gid) join riv r on r.HYBAS_L12 = gu.unit
group by all;
-- counts: (a) polygon method: gauge inside river-traced L12 unit set; (b) refined: also nearest segment upstream of dam
create or replace table gcount as
select b.EMBALSE_ID,
 count(distinct gu.gid) filter (gu.src='AEMET') aemet_l12poly,
 count(distinct gu.gid) filter (gu.src='SAIH') saih_l12poly,
 count(distinct gs.gid) filter (gs.src='AEMET' and up.HYRIV_ID is not null) aemet_refined,
 count(distinct gs.gid) filter (gs.src='SAIH' and up.HYRIV_ID is not null) saih_refined
from b left join rt_units t using(EMBALSE_ID)
left join g_unit gu on gu.unit=t.id
left join g_seg gs on gs.src=gu.src and gs.gid=gu.gid
left join upriv up on up.EMBALSE_ID=b.EMBALSE_ID and up.HYRIV_ID=gs.seg
group by 1;
