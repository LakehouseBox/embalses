-- Live reservoir readings from SAIH Tajo → embalses.obs.reservoir_readings. Scheduled SQL, hourly.
-- Source: the Confederación Hidrográfica del Tajo's public viewer, saihtajo.chtajo.es. JSON over GET, no sign-in and no
-- cookie; every call carries an opaque token (x=) that the viewer takes from the previous one, so this query walks the
-- same chain: home page → get-wrapperentorno → get-menu → get-datos-tiempo-real (the station list, ~1.7 MB) → one
-- get-estacion per reservoir (54, ~70 KB each). About 58 requests a run, so hourly, like the source (hourly values).
-- robots.txt disallows /?w= but not /index.php?w=, which is what the viewer itself calls.
-- Each station answers its last 24 hourly values per signal: NE level (m), VE volume (hm³), PO % full, CSR outflow (m³/s).
-- This keeps the latest hour that has a volume. Times are Madrid local ('dd/mm/yyyy HH:MM').
-- reservoir_id is resolved from ref.stations downstream (saih-tajo:E_01 … from MITECO's SAIH register).
WITH
home AS MATERIALIZED (
  SELECT regexp_extract((http_get('https://saihtajo.chtajo.es/')).body,
                        'index\.php\?w=get-wrapperentorno&x=[^"'' ]+', 0) AS u
),
wrapper AS MATERIALIZED (
  SELECT (http_get('https://saihtajo.chtajo.es/' || u)).body::JSON -> 'response' ->> 'urlmenu' AS u FROM home
),
menu AS MATERIALIZED (
  SELECT regexp_extract((http_get('https://saihtajo.chtajo.es/' || u)).body,
                        'index\.php\?w=get-datos-tiempo-real&x=[^"\\]+', 0) AS u FROM wrapper
),
tipos AS MATERIALIZED (
  SELECT unnest(from_json((http_get('https://saihtajo.chtajo.es/' || u)).body::JSON -> 'response' -> 'cuenca' -> 'tipos',
                          '[{"id":"VARCHAR","subcuencas":[{"estaciones":[{"codigo":"VARCHAR","url":"VARCHAR"}]}]}]')) AS t
  FROM menu
),
st AS (
  SELECT DISTINCT e.codigo, e.url
  FROM (SELECT unnest(t.subcuencas) AS s FROM tipos WHERE t.id = 'E'),
       LATERAL (SELECT unnest(s.estaciones) AS e)
),
r AS MATERIALIZED (
  SELECT st.codigo,
         unnest(from_json((http_get('https://saihtajo.chtajo.es/' || st.url)).body::JSON -> 'response' -> 'senales',
                          '[{"tiposenal":"VARCHAR","valores":[{"tiempo":"VARCHAR","valor":"DOUBLE"}]}]')) AS sig
  FROM st
),
v AS (
  SELECT codigo, sig.tiposenal AS kind,
         timezone('Europe/Madrid', strptime(x.tiempo, '%d/%m/%Y %H:%M')) AS observed_at, x.valor
  FROM r, LATERAL (SELECT unnest(sig.valores) AS x)
),
hourly AS (
  SELECT codigo, observed_at,
         max(valor) FILTER (WHERE kind = 'NE')  AS water_level_masl,
         max(valor) FILTER (WHERE kind = 'VE')  AS stored_volume_hm3,
         max(valor) FILTER (WHERE kind = 'PO')  AS fill_pct,
         max(valor) FILTER (WHERE kind = 'CSR') AS outflow_m3s
  FROM v GROUP BY ALL
)
SELECT 'saih-tajo:' || codigo AS station_id, NULL::INTEGER AS reservoir_id, observed_at,
       water_level_masl, stored_volume_hm3, fill_pct, NULL::DOUBLE AS inflow_m3s, outflow_m3s,
       true AS is_provisional, 'saih-tajo' AS source
FROM hourly
WHERE stored_volume_hm3 IS NOT NULL
QUALIFY row_number() OVER (PARTITION BY codigo ORDER BY observed_at DESC) = 1
