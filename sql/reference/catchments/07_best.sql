load spatial;
create or replace table snap_best as
select a.EMBALSE_ID,
  coalesce(a.poly_id, a.r500_id, a.near_id) HYRIV_ID,
  case when a.poly_id is not null then 'reservoir_polygon' when a.r500_id is not null then 'max_upland_500m' else 'nearest_2km' end snap_rule
from snap_alt a;
create or replace table snap_best as select s.*, r.upland, r.dis, r.HYBAS_L12, round(st_distance(b.g, r.g)) rdist from snap_best s join riv r using(HYRIV_ID) join b using(EMBALSE_ID);
create or replace table starts as
select EMBALSE_ID, 'r12' m, HYBAS_L12 id from snap_best
union all select s.EMBALSE_ID, 'r10', u10.id from snap_best s join l12 u on u.id=s.HYBAS_L12 join l10 u10 on u10.pfaf::varchar = substr(u.pfaf::varchar,1,10)
union all select EMBALSE_ID, 'b12', id from snap_b12
union all select EMBALSE_ID, 'b10', id from snap_b10
union all select EMBALSE_ID, 'c12', id from in_b12;
create or replace table up12 as
with recursive w(EMBALSE_ID, m, id) as (
  select EMBALSE_ID, m, id from starts where m in ('r12','b12','c12')
  union
  select w.EMBALSE_ID, w.m, u.id from w join l12 u on u.nd = w.id)
select * from w;
create or replace table up10 as
with recursive w(EMBALSE_ID, m, id) as (
  select EMBALSE_ID, m, id from starts where m in ('r10','b10')
  union
  select w.EMBALSE_ID, w.m, u.id from w join l10 u on u.nd = w.id)
select * from w;
