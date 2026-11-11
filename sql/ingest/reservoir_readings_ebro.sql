-- Live reservoir readings from SAIH Ebro → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer; JSON over GET, every 15 min; times are Madrid local.
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
-- ── SAIH Ebro: main reservoirs, every 15 min; JSON, Madrid local time ─────────────
ebro AS (
  SELECT unnest(DATOS) AS s
  FROM read_json('https://www.saihebro.com/api/mapa/getDatosMapa?slug=mapa-embalses-HG-toda-la-cuenca')
),
ebro_tags AS (
  SELECT s.CW_REMOTA_TXT AS code, unnest(s.TAGS) AS tag FROM ebro
),
ebro_rows AS (
  SELECT 'saih-ebro:' || code AS station_id,
         tag.ULTIMA_FECHA::TIMESTAMP AT TIME ZONE 'Europe/Madrid' AS observed_at,
         tag.LS_TIPO_SENAL AS signal,
         TRY_CAST(replace(replace(tag.VALOR, '.', ''), ',', '.') AS DOUBLE) AS value
  FROM ebro_tags
),
ebro_out AS (
  SELECT station_id, observed_at,
         max(value) FILTER (WHERE signal = 'NEMBA') AS water_level_masl,
         max(value) FILTER (WHERE signal = 'VEMBA') AS stored_volume_hm3,
         max(value) FILTER (WHERE signal = 'PORCE') AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         NULL::DOUBLE AS outflow_m3s,
         'saih-ebro' AS source
  FROM ebro_rows GROUP BY station_id, observed_at
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM ebro_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
