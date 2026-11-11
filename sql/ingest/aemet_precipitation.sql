-- AEMET OpenData hourly observations → embalses.obs.precipitation. Scheduled SQL, every 30 min.
-- Two steps in one run: the keyed endpoint answers a `datos` URL that expires minutes later; follow it at once.
-- Uses http_get; the AEMET key comes from the catalog connection `aemet`
-- (prefix https://opendata.aemet.es/), which points at the organisation's aemet web integration (G7).
-- The body is decoded from its Content-Type charset (ISO-8859-15). The sink must be created by the key's owner.
-- AEMET returns a rolling ~12 h window: rows repeat between runs; readers de-duplicate on the interval key.
WITH s AS MATERIALIZED (
  SELECT (http_get('https://opendata.aemet.es/opendata/api/observacion/convencional/todas')).body::JSON ->> 'datos' AS u
),
d AS MATERIALIZED (
  SELECT (http_get(u)).body AS txt FROM s
),
o AS (
  SELECT unnest(from_json(txt, '[{"idema":"VARCHAR","fint":"VARCHAR","prec":"DOUBLE"}]'), recursive := true)
  FROM d
)
SELECT 'aemet:' || idema                                         AS station_id,
       strptime(fint, '%Y-%m-%dT%H:%M:%S%z') - INTERVAL 1 HOUR   AS period_start_at,
       strptime(fint, '%Y-%m-%dT%H:%M:%S%z')                     AS period_end_at,
       60                                                        AS period_minutes,
       prec                                                      AS precipitation_mm,
       true                                                      AS is_provisional,
       'aemet-opendata'                                          AS source
FROM o
WHERE prec IS NOT NULL
