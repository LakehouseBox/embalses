-- Reservoir readings from the Agència Catalana de l'Aigua → embalses.obs.reservoir_readings. Scheduled SQL, every 6 h.
-- Source: Catalonia's open-data portal (Socrata), dataset vjx7-6kcp "Quantitat d'aigua als embassaments de les conques
-- internes de Catalunya (dades en temps de registre)": 5-minute level, volume and % full for 9 reservoirs, published once
-- a day (about 07:10 UTC, up to about 04:40 local time). So these are daily, not live: now.reservoir_status accepts an
-- ACA reading for 36 h (6 h for the SAIH feeds) and the page labels it "diario".
-- Keeps the hourly values (hh:00) of the last two days; rows repeat between runs and readers de-duplicate.
-- The dataset's station codes (E01…) are not MITECO's (026E01…): the list below maps the 7 bulletin reservoirs to the
-- ACA station ids in ref.stations. Not in the bulletin: E16 Foix, E18 Siurana. Times are Madrid local.
WITH
codes(codi_estacio, station_id) AS (VALUES
  ('E01', 'aca:026E01'),   -- Boadella
  ('E06', 'aca:073E01'),   -- Sau
  ('E07', 'aca:075E01'),   -- Susqueda
  ('E12', 'aca:168E01'),   -- La Llosa del Cavall
  ('E13', 'aca:170E01'),   -- Sant Ponç
  ('E14', 'aca:158E01'),   -- La Baells
  ('E19', 'aca:236E01')    -- Riudecanyes
),
r AS MATERIALIZED (
  SELECT unnest(from_json((http_get(
           'https://analisi.transparenciacatalunya.cat/resource/vjx7-6kcp.json?$limit=5000'
           || '&$select=dia,hora,codi_estacio,tipus_variable,valor'
           || '&$where=dia%3E=%27' || strftime(current_date - 1, '%Y-%m-%d') || '%27%20AND%20hora%20like%20%27%25:00%27'
         )).body,
         '[{"dia":"VARCHAR","hora":"VARCHAR","codi_estacio":"VARCHAR","tipus_variable":"VARCHAR","valor":"VARCHAR"}]'),
         recursive := true)
),
hourly AS (
  SELECT codi_estacio,
         timezone('Europe/Madrid', strptime(left(dia, 10) || ' ' || hora, '%Y-%m-%d %H:%M')) AS observed_at,
         max(TRY_CAST(valor AS DOUBLE)) FILTER (WHERE tipus_variable = 'Nivell absolut')             AS water_level_masl,
         max(TRY_CAST(valor AS DOUBLE)) FILTER (WHERE tipus_variable = 'Volum embassat')             AS stored_volume_hm3,
         max(TRY_CAST(valor AS DOUBLE)) FILTER (WHERE tipus_variable = 'Percentatge volum embassat') AS fill_pct
  FROM r GROUP BY ALL
)
SELECT c.station_id, NULL::INTEGER AS reservoir_id, h.observed_at, h.water_level_masl, h.stored_volume_hm3, h.fill_pct,
       NULL::DOUBLE AS inflow_m3s, NULL::DOUBLE AS outflow_m3s, true AS is_provisional, 'aca' AS source
FROM hourly h JOIN codes c USING (codi_estacio)
WHERE h.stored_volume_hm3 IS NOT NULL AND h.observed_at IS NOT NULL
