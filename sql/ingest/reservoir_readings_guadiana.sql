-- Live reservoir readings from SAIH Guadiana (SIRA) → embalses.obs.reservoir_readings. Scheduled SQL, hourly.
-- Source: the Confederación Hidrográfica del Guadiana's public viewer, siraguadiana.com. The viewer signs every visitor in
-- as the anonymous user "public" and sends that session token with each request; this query does the same:
-- one sign-in, the station list, then one request per reservoir (about 45 requests per run, so it runs hourly).
-- POST prefix https://siraguadiana.com/backend/ must be declared on the catalog. Timestamps are UTC.
WITH tok AS MATERIALIZED (
  SELECT (http_post('https://siraguadiana.com/backend/security/getProfile',
                    '{"COD_USUARIO":"public","ORIGIN":"db","APP":"VISOR","CASTICKET":null}')).body::JSON ->> 'sesionId' AS t
),
st AS MATERIALIZED (
  SELECT unnest(from_json((http_get('https://siraguadiana.com/backend/Visor/estaciones', headers := MAP {'AUTHJWT': t})).body::JSON -> 'estaciones',
                          '[{"cod_estacion":"VARCHAR","tipo":"VARCHAR","disponible":"BOOLEAN"}]'), recursive := true)
  FROM tok
),
r AS MATERIALIZED (
  SELECT st.cod_estacion,
         (http_post('https://siraguadiana.com/backend/Visor/resourceByID',
                    '{"id":"' || st.cod_estacion || '","type":"ficha_zonas_embalse"}',
                    headers := MAP {'AUTHJWT': tok.t})).body::JSON -> 'ult_res' -> 'valores' -> 0 AS v
  FROM st, tok
  WHERE st.tipo = 'E' AND st.disponible
)
SELECT 'saih-guadiana:' || cod_estacion                     AS station_id,
       NULL::INTEGER                                        AS reservoir_id,
       (TRY_CAST(v ->> 'timestamp' AS TIMESTAMP) AT TIME ZONE 'UTC')  AS observed_at,
       TRY_CAST(v ->> 'NE1' AS DOUBLE)                                AS water_level_masl,
       TRY_CAST(v ->> 'VE1' AS DOUBLE)                                AS stored_volume_hm3,
       TRY_CAST(v ->> 'PV1' AS DOUBLE)                                AS fill_pct,
       NULL::DOUBLE                                         AS inflow_m3s,
       TRY_CAST(v ->> 'QSR' AS DOUBLE)                                AS outflow_m3s,
       true                                                 AS is_provisional,
       'saih-guadiana'                                      AS source
FROM r
WHERE TRY_CAST(v ->> 'VE1' AS DOUBLE) IS NOT NULL AND TRY_CAST(v ->> 'timestamp' AS TIMESTAMP) IS NOT NULL
