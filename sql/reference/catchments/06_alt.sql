load spatial;
create or replace table snap_alt as
with c as (select b.EMBALSE_ID, r.HYRIV_ID, r.upland, r.HYBAS_L12, st_distance(b.g,r.g) d,
   (select bool_or(st_dwithin(e.g, r.g, 250)) from supe s join embp e using(ID_EMBALSE) where s.EMBALSE_ID=b.EMBALSE_ID and (s.ensim>=0.85 or s.edist<300)) touches_poly
  from b join riv r on st_dwithin(b.g,r.g,2000))
select EMBALSE_ID,
  arg_min(HYRIV_ID, d) near_id, arg_min(upland, d) near_up,
  arg_max(upland, upland) filter (d<=500) r500_up, arg_max(HYRIV_ID, upland) filter (d<=500) r500_id,
  arg_max(upland, upland) filter (touches_poly) poly_up, arg_max(HYRIV_ID, upland) filter (touches_poly) poly_id,
  count(*) filter (touches_poly) n_poly
from c group by 1;
