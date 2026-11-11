load spatial;
create or replace table catch as select HYRIV_ID, CATCH_SKM::double catch from 'data/geo/hydrosheds/rivers_iberia.parquet';
create or replace table upriv as
with recursive w(EMBALSE_ID, HYRIV_ID) as (
  select EMBALSE_ID, HYRIV_ID from snap_best
  union
  select w.EMBALSE_ID, r.HYRIV_ID from w join riv r on r.NEXT_DOWN = w.HYRIV_ID)
select * from w;
create or replace table rt_units as select distinct u.EMBALSE_ID, r.HYBAS_L12 id from upriv u join riv r using(HYRIV_ID);
create or replace table rt_area as select t.EMBALSE_ID, sum(l.sub) filter (e.ENDO=0) area_l12_rivtrace, count(*) n_units_rt from rt_units t join l12 l using(id) join endo e using(id) group by 1;
create or replace table rt_chk as select u.EMBALSE_ID, sum(c.catch) catch_sum, count(*) nseg from upriv u join catch c using(HYRIV_ID) group by 1;
