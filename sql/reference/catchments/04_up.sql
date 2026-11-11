load spatial;
-- start units per method
create or replace table starts as
select EMBALSE_ID, 'r12' m, HYBAS_L12 id from snap_riv
union all select s.EMBALSE_ID, 'r10', u10.id from snap_riv s join l12 u on u.id=s.HYBAS_L12 join l10 u10 on u10.pfaf::varchar = substr(u.pfaf::varchar,1,10)
union all select EMBALSE_ID, 'b12', id from snap_b12
union all select EMBALSE_ID, 'b10', id from snap_b10;
create or replace table up12 as
with recursive w(EMBALSE_ID, m, id) as (
  select EMBALSE_ID, m, id from starts where m in ('r12','b12')
  union
  select w.EMBALSE_ID, w.m, u.id from w join l12 u on u.nd = w.id)
select * from w;
create or replace table up10 as
with recursive w(EMBALSE_ID, m, id) as (
  select EMBALSE_ID, m, id from starts where m in ('r10','b10')
  union
  select w.EMBALSE_ID, w.m, u.id from w join l10 u on u.nd = w.id)
select * from w;
create or replace table uparea as
select w.EMBALSE_ID, w.m, sum(u.sub) area_walk, count(*) n_units from up12 w join l12 u using(id) group by all
union all
select w.EMBALSE_ID, w.m, sum(u.sub), count(*) from up10 w join l10 u using(id) group by all;
