-- Reservoir readings from the two regional water agencies → embalses.obs.reservoir_readings. Scheduled SQL, hourly.
-- One sink for both because LakehouseBox takes at most 8 sinks per table and obs.reservoir_readings has one per SAIH;
-- the cost is that one source failing fails the run for both.
--
-- 1. SAIH Hidrosur (Junta de Andalucía): the public viewer's "Datos de última hora" page,
--    redhidrosurmedioambiente.es/saih/resumen/embalses: one HTML table with the 29 reservoirs of the three Andalusian
--    districts (Tinto-Odiel-Piedras, Guadalete-Barbate and the Mediterranean basins), refreshed hourly. One GET a run.
--    Each row: number, name, % full, capacity, rain since 1 Oct, volume now (hm³), then last week's and last year's.
--    One time for all rows ("Datos actualizados a: dd-mm-yyyy HH:MM:SS", Madrid local; og:updated_time says +01:00).
--    station_id uses the sensor code of the row's chart link (…/grafica/003E01/…): saih-hidrosur:003E01.
--    MITECO's bulletin reports Guadalhorce and Guadalteba (one dam system) as one reservoir, so their sum is also
--    written, as station saih-hidrosur:029L02+030E01. Links: sql/reference/stations_hidrosur.sql.
--
-- 2. Agència Catalana de l'Aigua: Catalonia's open-data portal (Socrata), dataset vjx7-6kcp "Quantitat d'aigua als
--    embassaments de les conques internes de Catalunya (dades en temps de registre)": 5-minute level, volume and % full
--    for 9 reservoirs, published once a day (about 07:10 UTC, up to about 04:40). So these are daily, not live:
--    now.reservoir_status accepts an ACA reading for 36 h (6 h for the SAIH feeds) and the page labels it "diario".
--    Fetched only by the 08, 14 and 20 UTC runs (one GET each); keeps the hourly values (hh:00) of the last two days,
--    so rows repeat between those runs and readers de-duplicate.
--    The dataset's station codes (E01…) are not MITECO's (026E01…): the list below maps the 7 bulletin reservoirs to
--    the ACA station ids in ref.stations. Not in the bulletin: E16 Foix, E18 Siurana.
--    Times: dia + hora are NOT Madrid wall-clock (29 March has 02:xx readings; 25 October has no repeated hour), so a
--    fixed offset. The dataset does not say which; read here as UTC, as Meteocat's XEMA does (if UTC+1, 1 h late).
WITH
-- ── SAIH Hidrosur ──
hs_page AS MATERIALIZED (
  SELECT (http_get('https://www.redhidrosurmedioambiente.es/saih/resumen/embalses')).body AS c
),
hs_t AS (
  SELECT strptime(regexp_extract(c, 'Datos actualizados a: ([0-9]{2}-[0-9]{2}-[0-9]{4} [0-9:]{8})', 1), '%d-%m-%Y %H:%M:%S') AS at_local,
         unnest(regexp_extract_all(c, '(?s)<tr class="embalse-fila">(.*?)</tr>', 1)) AS r
  FROM hs_page
),
hs_cells AS (
  SELECT at_local,
         regexp_extract(r, 'grafica/([0-9A-Z]+)/', 1) AS code,
         list_transform(regexp_extract_all(r, '(?s)<td[^>]*>(.*?)</td>', 1),
                        lambda x: trim(regexp_replace(x, '<[^>]+>', '', 'g'))) AS c
  FROM hs_t
),
hs AS (
  SELECT 'saih-hidrosur:' || code                                                        AS station_id,
         timezone('Europe/Madrid', at_local)                                             AS observed_at,
         NULL::DOUBLE                                                                    AS water_level_masl,
         TRY_CAST(replace(replace(c[6], '.', ''), ',', '.') AS DOUBLE)                   AS stored_volume_hm3,
         TRY_CAST(replace(replace(replace(c[3], '%', ''), '.', ''), ',', '.') AS DOUBLE) AS fill_pct,
         'saih-hidrosur'                                                                 AS source
  FROM hs_cells
  WHERE code <> '' AND at_local IS NOT NULL
),
hs_sum AS (   -- Guadalhorce + Guadalteba, as the bulletin counts them
  SELECT 'saih-hidrosur:029L02+030E01' AS station_id, max(observed_at) AS observed_at, NULL::DOUBLE AS water_level_masl,
         sum(stored_volume_hm3) AS stored_volume_hm3, NULL::DOUBLE AS fill_pct, 'saih-hidrosur' AS source
  FROM hs WHERE station_id IN ('saih-hidrosur:029L02', 'saih-hidrosur:030E01') AND stored_volume_hm3 IS NOT NULL
  HAVING count(*) = 2
),
-- ── ACA ──
aca_codes(codi_estacio, station_id) AS (VALUES
  ('E01', 'aca:026E01'),   -- Boadella
  ('E06', 'aca:073E01'),   -- Sau
  ('E07', 'aca:075E01'),   -- Susqueda
  ('E12', 'aca:168E01'),   -- La Llosa del Cavall
  ('E13', 'aca:170E01'),   -- Sant Ponç
  ('E14', 'aca:158E01'),   -- La Baells
  ('E19', 'aca:236E01')    -- Riudecanyes
),
aca_r AS MATERIALIZED (
  SELECT unnest(from_json((http_get(
           'https://analisi.transparenciacatalunya.cat/resource/vjx7-6kcp.json?$limit=5000'
           || '&$select=dia,hora,codi_estacio,tipus_variable,valor'
           || '&$where=dia%3E=%27' || strftime(current_date - 1, '%Y-%m-%d') || '%27%20AND%20hora%20like%20%27%25:00%27'
         )).body,
         '[{"dia":"VARCHAR","hora":"VARCHAR","codi_estacio":"VARCHAR","tipus_variable":"VARCHAR","valor":"VARCHAR"}]'),
         recursive := true)
  FROM (SELECT 1) AS gate
  WHERE hour(now() AT TIME ZONE 'UTC') IN (8, 14, 20)
),
aca AS (
  SELECT c.station_id,
         strptime(left(r.dia, 10) || ' ' || r.hora, '%Y-%m-%d %H:%M') AT TIME ZONE 'UTC'               AS observed_at,
         max(TRY_CAST(r.valor AS DOUBLE)) FILTER (WHERE r.tipus_variable = 'Nivell absolut')             AS water_level_masl,
         max(TRY_CAST(r.valor AS DOUBLE)) FILTER (WHERE r.tipus_variable = 'Volum embassat')             AS stored_volume_hm3,
         max(TRY_CAST(r.valor AS DOUBLE)) FILTER (WHERE r.tipus_variable = 'Percentatge volum embassat') AS fill_pct,
         'aca' AS source
  FROM aca_r r JOIN aca_codes c USING (codi_estacio)
  GROUP BY ALL
),
rows AS (
  SELECT * FROM hs UNION ALL SELECT * FROM hs_sum UNION ALL SELECT * FROM aca
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       NULL::DOUBLE AS inflow_m3s, NULL::DOUBLE AS outflow_m3s, true AS is_provisional, source
FROM rows
WHERE observed_at IS NOT NULL AND stored_volume_hm3 IS NOT NULL
