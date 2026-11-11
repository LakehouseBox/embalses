load spatial;
-- fallback for reservoirs with no HydroRIVERS segment within 2 km: L12 containing unit + upstream
create or replace table gcount_fb as
select w.EMBALSE_ID, count(distinct gu.gid) filter (gu.src='AEMET') a, count(distinct gu.gid) filter (gu.src='SAIH') s
from up12 w join g_unit gu on gu.unit=w.id where w.m='c12' and w.EMBALSE_ID not in (select EMBALSE_ID from snap_best) group by 1;
create or replace table final as
select r.EMBALSE_ID, r.nombre as name, r.ambito_nombre, r.agua_total as capacity_hm3,
  r.HYRIV_ID as hyriv_id, r.snap_rule, r.riv_snap_dist_m,
  r.unit_l12_river as hybas_l12_id, r.unit_l10_river as hybas_l10_id,
  r.unit_l12_direct as hybas_l12_id_direct2km, r.unit_l10_direct as hybas_l10_id_direct2km,
  (select id from in_b12 where EMBALSE_ID=r.EMBALSE_ID) as hybas_l12_id_containing,
  round(r.area_hydrorivers,1) as upstream_area_km2_hydrorivers,
  round(r.area_hydrorivers_max2km,1) as upstream_area_km2_hydrorivers_max2km,
  round(r.area_l12,1) as upstream_area_km2_hybas_l12,
  round(r.area_l10,1) as upstream_area_km2_hybas_l10,
  round(t.area_l12_rivtrace,1) as upstream_area_km2_hybas_l12_rivertraced,
  round(r.area_l12_direct,1) as upstream_area_km2_hybas_l12_direct2km,
  round(r.area_l10_direct,1) as upstream_area_km2_hybas_l10_direct2km,
  round(r.area_l12_containing,1) as upstream_area_km2_hybas_l12_containing,
  round(coalesce(r.area_hydrorivers, r.area_l12_containing),1) as upstream_area_km2_best,
  case when r.area_hydrorivers is not null then 'hydrorivers' else 'hybas_l12_containing' end as best_method,
  p.pfafrio as miteco_pfafrio, p.nom_rio_1 as miteco_pfaf_river, round(p.pfaf_area,1) as miteco_pfaf_polygon_km2,
  r.inv_dam_id, r.inv_dam_name, r.inv_dam_dist_m, r.inv_name_sim,
  r.sup_cuenca_dam as inv_sup_cuenca_presa, r.sup_cuenca_embalse as inv_sup_cuenca_embalse, r.sup_cuenca as inv_sup_cuenca,
  coalesce(g.aemet_refined, fb.a, 0) as n_aemet, coalesce(g.saih_refined, fb.s, 0) as n_saih,
  coalesce(g.aemet_refined, fb.a, 0) + coalesce(g.saih_refined, fb.s, 0) as n_gauges,
  coalesce(g.aemet_l12poly, fb.a, 0) as n_aemet_l12poly, coalesce(g.saih_l12poly, fb.s, 0) as n_saih_l12poly,
  round(r.dis_av_cms,2) as hydrorivers_dis_av_cms
from res r left join rt_area t using(EMBALSE_ID) left join b_pfaf p using(EMBALSE_ID)
left join gcount g using(EMBALSE_ID) left join gcount_fb fb using(EMBALSE_ID);
copy (select f.*, st_aswkb(b.g4) as geometry from final f join b using(EMBALSE_ID) order by EMBALSE_ID) to 'results.parquet' (format parquet);
