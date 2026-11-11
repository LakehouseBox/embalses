load spatial;
create or replace table endo as select HYBAS_ID::bigint id, ENDO from 'lev12_iberia.parquet' union all select HYBAS_ID::bigint, ENDO from 'lev10_iberia_full.parquet';
create or replace table uparea as
select w.EMBALSE_ID, w.m, sum(u.sub) filter (e.ENDO=0) area_walk, sum(u.sub) area_walk_incl_endo, count(*) filter (e.ENDO=0) n_units from up12 w join l12 u using(id) join endo e using(id) group by all
union all
select w.EMBALSE_ID, w.m, sum(u.sub) filter (e.ENDO=0), sum(u.sub), count(*) filter (e.ENDO=0) from up10 w join l10 u using(id) join endo e using(id) group by all;
create or replace table res as
select b.EMBALSE_ID, b.nombre, b.agua_total, b.ambito_nombre,
  sr.HYRIV_ID, sr.snap_rule, sr.rdist riv_snap_dist_m, (select upland from snap_riv where EMBALSE_ID=b.EMBALSE_ID) area_hydrorivers_max2km, sr.upland area_hydrorivers, sr.dis dis_av_cms,
  sr.HYBAS_L12 unit_l12_river, s10.id unit_l10_river, sb12.id unit_l12_direct, sb10.id unit_l10_direct,
  (select area_walk from uparea where EMBALSE_ID=b.EMBALSE_ID and m='r12') area_l12,
  (select area_walk from uparea where EMBALSE_ID=b.EMBALSE_ID and m='r10') area_l10,
  (select area_walk from uparea where EMBALSE_ID=b.EMBALSE_ID and m='b12') area_l12_direct,
  (select area_walk from uparea where EMBALSE_ID=b.EMBALSE_ID and m='b10') area_l10_direct, (select area_walk from uparea where EMBALSE_ID=b.EMBALSE_ID and m='c12') area_l12_containing,
  sc.ID_INFRAES inv_dam_id, sc.dname inv_dam_name, round(sc.dist) inv_dam_dist_m, round(sc.nsim,2) inv_name_sim, sc.score inv_match_score,
  sc.sup_dam sup_cuenca_dam, se.sup_emb sup_cuenca_embalse,
  coalesce(sc.sup_dam, nullif(se.sup_emb,0)) sup_cuenca
from b left join snap_best sr using(EMBALSE_ID)
left join (select * from starts where m='r10') s10 using(EMBALSE_ID)
left join snap_b12 sb12 using(EMBALSE_ID) left join snap_b10 sb10 using(EMBALSE_ID)
left join supc sc using(EMBALSE_ID) left join supe se using(EMBALSE_ID);
create or replace table cmp as
unpivot (select EMBALSE_ID, nombre, sup_cuenca, area_l12, area_l10, area_l12_direct, area_l10_direct, area_l12_containing, area_hydrorivers_max2km, area_hydrorivers from res where sup_cuenca>0)
on area_l12, area_l10, area_l12_direct, area_l10_direct, area_l12_containing, area_hydrorivers_max2km, area_hydrorivers into name method value est;
