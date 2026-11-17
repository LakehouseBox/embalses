-- Live reservoir readings from SAIH Ebro → embalses.obs.reservoir_readings. Scheduled SQL, every 15 min.
-- Source: the basin authority's public viewer, saihebro.com; JSON over GET, every 15 min; times are Madrid local.
-- The viewer's whole-basin reservoir map (slug mapa-embalses-HG-toda-la-cuenca) shows only the 12 largest reservoirs,
-- so this reads that map and the 21 zone maps (H1 … H22, the zones of the viewer's river-gauge maps), 22 requests a run.
-- A reservoir can sit on two zone maps (and the whole-basin one): rows are de-duplicated here. Zone maps also carry
-- gauges (A… codes): only stations with a volume or level signal are kept.
-- One sink per SAIH feeds the same table, so one site changing does not stop the others.
-- reservoir_id is resolved from ref.stations downstream.
WITH
zones(slug) AS (VALUES
    ('HG-toda-la-cuenca'),
    ('H1-alto-ebro-mi'),
    ('H2-semi-alta-miranda'),
    ('H3-aragon-irati'),
    ('H4-medio-ebro-mi'),
    ('H5-gallego'),
    ('H6-bajo-cinca'),
    ('H7-segre'),
    ('H8-bajo-ebro'),
    ('H9-guadalope-martin'),
    ('H10-bajo-jalon'),
    ('H11-semi-alta-logrono'),
    ('H12-arga'),
    ('H13-nogueras'),
    ('H15-alto-ebro-md'),
    ('H16-alto-aragon'),
    ('H17-alto-cinca'),
    ('H18-esera'),
    ('H19-huerva-aguas-vivas'),
    ('H20-alto-jalon'),
    ('H21-medio-ebro-md'),
    ('H22-garona')
),
maps AS MATERIALIZED (
  SELECT (http_get('https://www.saihebro.com/api/mapa/getDatosMapa?slug=mapa-embalses-' || slug)).body AS body FROM zones
),
ebro AS (
  SELECT unnest(from_json(body::JSON -> 'DATOS',
                '[{"CW_REMOTA_TXT":"VARCHAR","TAGS":[{"LS_TIPO_SENAL":"VARCHAR","VALOR":"VARCHAR","ULTIMA_FECHA":"VARCHAR"}]}]')) AS s
  FROM maps
),
ebro_tags AS (
  SELECT s.CW_REMOTA_TXT AS code, unnest(s.TAGS) AS tag FROM ebro
),
ebro_rows AS (
  SELECT DISTINCT 'saih-ebro:' || code AS station_id,
         TRY_CAST(tag.ULTIMA_FECHA AS TIMESTAMP) AT TIME ZONE 'Europe/Madrid' AS observed_at,
         tag.LS_TIPO_SENAL AS signal,
         TRY_CAST(replace(replace(tag.VALOR, '.', ''), ',', '.') AS DOUBLE) AS value
  FROM ebro_tags
),
ebro_out AS (
  SELECT station_id, observed_at,
         max(value) FILTER (WHERE signal = 'NEMBA') AS water_level_masl,
         max(value) FILTER (WHERE signal = 'VEMBA') AS stored_volume_hm3,
         max(value) FILTER (WHERE signal = 'PORCE') AS fill_pct,
         NULL::DOUBLE AS inflow_m3s,
         NULL::DOUBLE AS outflow_m3s,
         'saih-ebro' AS source
  FROM ebro_rows GROUP BY station_id, observed_at
)
SELECT station_id, NULL::INTEGER AS reservoir_id, observed_at, water_level_masl, stored_volume_hm3, fill_pct,
       inflow_m3s, outflow_m3s, true AS is_provisional, source
FROM ebro_out
WHERE observed_at IS NOT NULL AND (stored_volume_hm3 IS NOT NULL OR water_level_masl IS NOT NULL)
