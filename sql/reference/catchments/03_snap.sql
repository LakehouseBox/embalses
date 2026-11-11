load spatial;
create or replace macro nrm(s) as trim(regexp_replace(regexp_replace(
   case when regexp_matches(lower(strip_accents(s)), '^(.*), *(el|la|los|las|l'')$')
        then regexp_replace(lower(strip_accents(s)), '^(.*), *(el|la|los|las|l'')$', '\2 \1')
        else lower(strip_accents(s)) end,
   '\b(embalse|presa|de|del|la|el|los|las|y|i|d|l)\b|[^a-z0-9 ]', ' ', 'g'), ' +', ' ', 'g'));
-- reservoir-polygon SUP_CUENCA as a secondary inventory source
create or replace table supe as
select * from (select b.EMBALSE_ID, e.ID_EMBALSE, e.NOMBRE ename, e.SUP_CUENCA sup_emb, st_distance(b.g,e.g) edist,
   jaro_winkler_similarity(nrm(b.nombre), nrm(e.NOMBRE)) ensim,
   row_number() over (partition by b.EMBALSE_ID order by (jaro_winkler_similarity(nrm(b.nombre), nrm(e.NOMBRE))>=0.85) desc, st_distance(b.g,e.g)) rn
 from b join embp e on st_dwithin(b.g, e.g, 3000)) where rn=1;
-- river snap: largest upland within 2 km
create or replace table snap_riv as
select * from (select b.EMBALSE_ID, r.HYRIV_ID, r.upland, r.dis, r.HYBAS_L12, st_distance(b.g, r.g) rdist,
   row_number() over (partition by b.EMBALSE_ID order by r.upland desc) rn
 from b join riv r on st_dwithin(b.g, r.g, 2000)) where rn=1;
-- nearest river (diagnostic)
create or replace table near_riv as
select * from (select b.EMBALSE_ID, r.HYRIV_ID, r.upland, st_distance(b.g, r.g) rdist,
   row_number() over (partition by b.EMBALSE_ID order by st_distance(b.g, r.g)) rn
 from b join riv r on st_dwithin(b.g, r.g, 5000)) where rn=1;
-- direct basin snap: largest UP_AREA among units within 2 km
create or replace table snap_b12 as select * from (select b.EMBALSE_ID, u.id, u.up, row_number() over (partition by b.EMBALSE_ID order by u.up desc) rn from b join l12 u on st_dwithin(b.g,u.g,2000)) where rn=1;
create or replace table snap_b10 as select * from (select b.EMBALSE_ID, u.id, u.up, row_number() over (partition by b.EMBALSE_ID order by u.up desc) rn from b join l10 u on st_dwithin(b.g,u.g,2000)) where rn=1;
-- containing unit (diagnostic)
create or replace table in_b12 as select b.EMBALSE_ID, u.id, u.up from b join l12 u on st_intersects(b.g,u.g);
