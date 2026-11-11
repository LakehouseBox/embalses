-- Live reservoir readings from SAIH Segura → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer; form POST (prefix https://saihweb.chsegura.es/apps/iVisor/ declared on the catalog); values carry no timestamp, so the fetch time is used.
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
-- ── SAIH Segura: form POST, JSON; values carry no timestamp, so the fetch time (5-min data) is used ──
seg AS (
  SELECT unnest(from_json((http_post('https://saihweb.chsegura.es/apps/iVisor/obtener_datos.php',
                                     'action=consultar_embalses')).body,
                          '[{"NombreCortoPM":"VARCHAR","UltimoDatoNivel":"VARCHAR","UltimoDatoVolumen":"VARCHAR","PorcentajeCapacidad":"VARCHAR"}]'),
                recursive := true)
),
seg_out AS (
  -- the viewer's short names, normalised to the SAIH register's codes ('E. La Cierva' → E.LA CIERVA; accents dropped)
  SELECT 'saih-segura:' || replace(regexp_replace(upper(strip_accents(replace(NombreCortoPM, '. ', '.'))), '\s+', ' ', 'g'),
                                   'E.LA PEDRERA', 'E.PEDRERA') AS station_id,
         time_bucket(INTERVAL 5 MINUTE, now()) AS observed_at,
         TRY_CAST(replace(replace(UltimoDatoNivel, '.', ''), ',', '.') AS DOUBLE) AS water_level_masl,
         TRY_CAST(replace(replace(UltimoDatoVolumen, '.', ''), ',', '.') AS DOUBLE) AS stored_volume_hm3,
         TRY_CAST(replace(replace(PorcentajeCapacidad, '.', ''), ',', '.') AS DOUBLE) AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         NULL::DOUBLE AS outflow_m3s,
         'saih-segura' AS source
  FROM seg
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM seg_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
