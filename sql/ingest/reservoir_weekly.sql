-- MITECO weekly reservoir bulletin → embalses.obs.reservoir_weekly. Scheduled SQL, daily at 06:00 UTC.
-- The bulletin is dated Tuesday, but MITECO's map service sometimes shows it a day or more later. So every run keeps the
-- bulletin on show if it is under 8 days old, and the sink's key (reservoir_id, bulletin_date) replaces the rows it sent
-- before: a late bulletin still lands, and once. (Until 2026-11-18 only the bulletin dated yesterday was kept, so a bulletin
-- that appeared after Wednesday 06:00 UTC would have been missed for good.)
-- weekly_change_hm3 is left NULL here and computed from the previous bulletin in sql/now/refresh.sql.
-- History since 1988 was loaded once by tools/miteco_reservoir_weekly.py (same source, layer Embalses_Total).
WITH f AS (
  SELECT unnest(features) AS f
  FROM read_json('https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/Embalses_Mapa/FeatureServer/0/query?where=1%3D1&outFields=EMBALSE_ID,agua_actual,agua_total,energia_actual,energia_total,fecha,boletin_anyo,boletin_num&returnGeometry=false&f=json')
)
SELECT f.attributes.EMBALSE_ID::INTEGER                                   AS reservoir_id,
       (make_timestamp(f.attributes.fecha::BIGINT * 1000) AT TIME ZONE 'UTC')::DATE AS bulletin_date,
       f.attributes.boletin_anyo::INTEGER                                 AS bulletin_year,
       f.attributes.boletin_num::INTEGER                                  AS bulletin_number,
       f.attributes.agua_actual::DOUBLE                                   AS stored_volume_hm3,
       f.attributes.agua_total::DOUBLE                                    AS capacity_hm3,
       round(100.0 * f.attributes.agua_actual / nullif(f.attributes.agua_total, 0), 2) AS fill_pct,
       NULL::DOUBLE                                                       AS weekly_change_hm3,
       f.attributes.energia_actual::DOUBLE                                AS stored_energy_gwh,
       nullif(f.attributes.energia_total, 0)::DOUBLE                      AS energy_capacity_gwh,
       'miteco-arcgis'                                                    AS source
FROM f
WHERE (make_timestamp(f.attributes.fecha::BIGINT * 1000) AT TIME ZONE 'UTC')::DATE >= current_date - 8
