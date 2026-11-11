-- Live reservoir readings from SAIH Miño-Sil → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer; HTML table, one GET with the site's language cookie; Latin-1.
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
-- ── SAIH Miño-Sil: HTML table, one GET; the site serves data only with its language cookie ──
ms_rows AS (
  SELECT unnest(regexp_extract_all(
           (http_get('https://saih.chminosil.es/index.php?url=/datos/situacionEmbalses',
                     headers := MAP {'Cookie': 'lang=es'}, encoding := 'iso-8859-1')).body,   -- its pages are Latin-1 whatever they claim
           '(?s)<tr>\s*<td class="celdal">.*?</tr>', 0)) AS r
),
ms_out AS (
  SELECT 'saih-minosil:' || regexp_extract(r, 'estacion:(E[0-9]+)', 1) AS station_id,
         strptime(regexp_extract(r, '([0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2})', 1), '%d/%m/%Y %H:%M')
           AT TIME ZONE 'Europe/Madrid' AS observed_at,
         NULL::DOUBLE AS water_level_masl,
         TRY_CAST(replace(replace(regexp_extract(r, 'VEMBA[^>]*>([0-9.,]+)<', 1), '.', ''), ',', '.') AS DOUBLE) AS stored_volume_hm3,
         TRY_CAST(replace(replace(regexp_extract(r, 'PORCE[^>]*>([0-9.,]+)<', 1), '.', ''), ',', '.') AS DOUBLE) AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         NULL::DOUBLE AS outflow_m3s,
         'saih-minosil' AS source
  FROM ms_rows
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM ms_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
