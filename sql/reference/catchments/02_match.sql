load spatial;
create or replace macro nrm(s) as trim(regexp_replace(regexp_replace(
   case when regexp_matches(lower(strip_accents(s)), '^(.*), *(el|la|los|las|l'')$')
        then regexp_replace(lower(strip_accents(s)), '^(.*), *(el|la|los|las|l'')$', '\2 \1')
        else lower(strip_accents(s)) end,
   '\b(embalse|presa|de|del|la|el|los|las|y|i|d|l)\b|[^a-z0-9 ]', ' ', 'g'), ' +', ' ', 'g'));
create or replace table cand as
select b.EMBALSE_ID, b.nombre, b.agua_total, d.ID_INFRAES, d.NOMBRE dname, d.CAUCE, d.SUP_CUENCA, d.NMN_CAPAC, d.AP_M_ANUAL,
  st_distance(b.g, d.g) dist,
  greatest(jaro_winkler_similarity(nrm(b.nombre), nrm(d.NOMBRE)),
           case when contains(nrm(d.NOMBRE), nrm(b.nombre)) or contains(nrm(b.nombre), nrm(d.NOMBRE)) then 0.95 else 0 end) nsim,
  case when b.agua_total>0 and d.NMN_CAPAC>0 then abs(ln(d.NMN_CAPAC/b.agua_total)) end capdiff
from b join dams d on st_dwithin(b.g, d.g, 10000);
-- score: strong name match, capacity close, distance
create or replace table cand_s as select *,
  (case when nsim>=0.9 then 2 when nsim>=0.8 then 1 else 0 end)
  + (case when capdiff is null then 0 when capdiff<0.15 then 1.5 when capdiff<0.5 then 0.75 else 0 end)
  + (case when dist<500 then 1 when dist<2000 then 0.5 when dist < 5000 then 0 else -1 end) score
from cand;
create or replace table match as
select * from (select *, row_number() over (partition by EMBALSE_ID order by score desc, dist) rn from cand_s) where rn=1;
-- SUP_CUENCA: from matched dam; if null/0, take max SUP_CUENCA among same-name dams within 3 km (duplicated records), then reservoir polygon
create or replace table supc as
select m.EMBALSE_ID, m.ID_INFRAES, m.dname, m.dist, m.nsim, m.capdiff, m.score, m.NMN_CAPAC,
 coalesce(nullif(m.SUP_CUENCA,0),
   (select max(c.SUP_CUENCA) from cand_s c where c.EMBALSE_ID=m.EMBALSE_ID and nrm(c.dname)=nrm(m.dname) and c.dist<3000 and c.SUP_CUENCA>0)) sup_dam,
 m.AP_M_ANUAL
from match m;
