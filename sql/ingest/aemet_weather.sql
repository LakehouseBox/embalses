-- AEMET OpenData hourly observations → embalses.obs.weather. Scheduled SQL, every 30 min.
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
  SELECT unnest(from_json(txt, '[{"idema":"VARCHAR","fint":"VARCHAR","ta":"DOUBLE","tamin":"DOUBLE","tamax":"DOUBLE",
                                  "hr":"DOUBLE","tpr":"DOUBLE","vv":"DOUBLE","vmax":"DOUBLE","dv":"DOUBLE","pres":"DOUBLE"}]'),
                recursive := true)
  FROM d
)
SELECT 'aemet:' || idema                       AS station_id,
       strptime(fint, '%Y-%m-%dT%H:%M:%S%z')   AS observed_at,
       ta    AS air_temperature_c,
       tamin AS air_temperature_min_c,
       tamax AS air_temperature_max_c,
       hr    AS relative_humidity_pct,
       tpr   AS dew_point_c,
       vv    AS wind_speed_ms,
       vmax  AS wind_gust_ms,
       dv    AS wind_direction_deg,
       pres  AS pressure_hpa,
       true  AS is_provisional,
       'aemet-opendata' AS source
FROM o
