load spatial;
create or replace table b_pfaf as select b.EMBALSE_ID, p.pfafrio, p.cod_uni, p.nom_rio_1, p.Shape_Area pfaf_area from b join pfaf p on st_intersects(b.g4, p.g4);
