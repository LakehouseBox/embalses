-- Live reservoir readings from SAIH Cantábrico → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer; WordPress admin-ajax form POST (prefix https://visor.saichcantabrico.es/wp-admin/ declared on the catalog).
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
-- ── SAIH Cantábrico: WordPress admin-ajax form POST, HTML table, decimal points ──
cb_rows AS (
  SELECT unnest(regexp_extract_all(
           (http_post('https://visor.saichcantabrico.es/wp-admin/admin-ajax.php', 'action=tabla_embalses')).body,
           '(?s)<tr title="[^"]*" data-codigo="[0-9]+">.*?</tr>', 0)) AS r
),
cb_cells AS (
  SELECT regexp_extract(r, 'data-codigo="([0-9]+)"', 1) AS code,
         list_transform(regexp_extract_all(r, '(?s)<td[^>]*>(.*?)</td>', 1),
                        lambda c: trim(regexp_replace(c, '<[^>]+>', '', 'g'))) AS c
  FROM cb_rows
),
cb_out AS (   -- cells: zona, código, río, estación, nivel, NMN, resguardo, volumen, vol. NMN, resguardo vol., %, huso max, huso min, actualización
  SELECT 'saih-cantabrico:' || code AS station_id,
         strptime(c[14], '%H:%M | %d-%m-%Y') AT TIME ZONE 'Europe/Madrid' AS observed_at,
         TRY_CAST(c[5] AS DOUBLE) AS water_level_masl,
         TRY_CAST(c[8] AS DOUBLE) AS stored_volume_hm3,
         TRY_CAST(c[11] AS DOUBLE) AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         NULL::DOUBLE AS outflow_m3s,
         'saih-cantabrico' AS source
  FROM cb_cells
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM cb_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
