-- Live reservoir readings from SAIH Guadalquivir → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer; one HTML map page per province; times are Madrid local.
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
-- ── SAIH Guadalquivir: one map page per province; HTML, Madrid local time ─────────
gq_pages AS (
  SELECT content,
         strptime(regexp_extract(content, 'Actualizados: ([0-9]+/[0-9]+/[0-9]+ [0-9]+:[0-9]+:[0-9]+)', 1),
                  '%d/%m/%Y %H:%M:%S') AT TIME ZONE 'Europe/Madrid' AS observed_at
  FROM read_text(['https://www.chguadalquivir.es/saih/EmbalJA.aspx',
                  'https://www.chguadalquivir.es/saih/EmbalCO.aspx',
                  'https://www.chguadalquivir.es/saih/EmbalGR.aspx',
                  'https://www.chguadalquivir.es/saih/EmbalSE.aspx'])
),
gq_blocks AS (
  SELECT observed_at,
         unnest(regexp_extract_all(content, '(?s)ContentPlaceHolder1_(E[0-9]+)_divtabla">.*?</table>', 0)) AS blk
  FROM gq_pages
),
gq_out AS (
  SELECT 'saih-guadalquivir:' || regexp_extract(blk, 'ContentPlaceHolder1_(E[0-9]+)_', 1) AS station_id,
         observed_at,
         NULL::DOUBLE AS water_level_masl,
         TRY_CAST(replace(replace(regexp_extract(blk, '(?s)Volumen.*?>([0-9.,]+) hm', 1), '.', ''), ',', '.') AS DOUBLE)
           AS stored_volume_hm3,
         NULL::DOUBLE AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         TRY_CAST(replace(replace(regexp_extract(blk, '(?s)Caudal.*?>([0-9.,]+) m', 1), '.', ''), ',', '.') AS DOUBLE)
           AS outflow_m3s,
         'saih-guadalquivir' AS source
  FROM gq_blocks
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM gq_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
