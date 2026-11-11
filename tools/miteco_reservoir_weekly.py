"""MITECO weekly reservoir bulletin (Boletín Hidrológico semanal, 1988-) -> embalses.obs.reservoir_weekly.

Source: MITECO's public ArcGIS FeatureServer "Embalses_Total" (no key):
  https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/Embalses_Total/FeatureServer/0
One row per reservoir and bulletin. Volumes (agua_*) are hm3, energy (energia_*) GWh,
`fecha` is the bulletin's Tuesday as epoch ms at 00:00 UTC.

Steps
  fetch      page through the layer (resultOffset/resultRecordCount = the layer's
             maxRecordCount, ordered by its object-id field, f=json, 0.3 s apart) and
             save the raw attributes as NDJSON.
  transform  DuckDB (CLI, 1.5.5+) turns the NDJSON into Parquet with the data-model
             columns, drops the layer's rows without EMBALSE_ID/fecha and any
             (reservoir_id, bulletin_date) duplicate (keeping the newest object id),
             computes fill_pct and weekly_change_hm3.

Usage: python3 tools/miteco_reservoir_weekly.py OUT_DIR [--skip-fetch]
  writes OUT_DIR/raw/reservoir_weekly.ndjson and OUT_DIR/reservoir_weekly.parquet.

Loading: `lhbox table import ... --mode append` (lhbox 0.6.128 + DuckDB 1.5.5) fails on these
year()-partitioned tables ("target-file-size-bytes is currently not supported for partitioned
tables"), so load with one INSERT in `lhbox duckdb`:
  SET TimeZone='UTC'; SET preserve_insertion_order=true;
  SET ignore_target_file_size_for_partitioned_tables=true;
  INSERT INTO embalses.obs.reservoir_weekly (<columns>) SELECT <columns> FROM read_parquet('OUT_DIR/reservoir_weekly.parquet') ORDER BY bulletin_date, reservoir_id;
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

LAYER = ("https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/"
         "Embalses_Total/FeatureServer/0")
FIELDS = ["EMBALSE_ID", "embalse_nombre", "ambito_nombre", "agua_total", "agua_actual",
          "energia_total", "energia_actual", "fecha", "Fecha_str", "boletin_anyo", "boletin_num",
          "Variacion_Reserva", "Porcentaje_Reserva", "ID_Unico"]
PAUSE_S = 0.3
SOURCE = "miteco-arcgis"


def get_json(url, params, tries=5):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(full, timeout=120) as r:
                d = json.loads(r.read().decode("utf-8"))
            if "error" in d:
                raise RuntimeError(d["error"])
            return d
        except Exception as e:  # network blips and ArcGIS 'error' bodies: retry with back-off
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"  retry in {wait}s after: {e}", file=sys.stderr)
            time.sleep(wait)


def fetch(path):
    meta = get_json(LAYER, {"f": "json"})
    page = int(meta["maxRecordCount"])
    oid = meta["objectIdField"]  # the layer's real OID; its plain 'OBJECTID' column is mostly null
    total = get_json(LAYER + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    print(f"layer: {total} rows, maxRecordCount {page}, ordered by {oid}", file=sys.stderr)
    n = 0
    tmp = path + ".part"
    with open(tmp, "w") as out:
        offset = 0
        while True:
            d = get_json(LAYER + "/query", {
                "where": "1=1", "outFields": ",".join(FIELDS + [oid]), "orderByFields": oid,
                "resultOffset": offset, "resultRecordCount": page,
                "returnGeometry": "false", "f": "json"})
            feats = d.get("features", [])
            for f in feats:
                a = f["attributes"]
                a["oid"] = a.pop(oid)
                out.write(json.dumps(a, ensure_ascii=False) + "\n")
            n += len(feats)
            offset += len(feats)
            if offset % 50000 < page:
                print(f"  {n}/{total}", file=sys.stderr)
            if not feats or not d.get("exceededTransferLimit"):
                break
            time.sleep(PAUSE_S)
    if n != total:
        raise RuntimeError(f"fetched {n} rows but the layer reports {total}")
    os.replace(tmp, path)
    return n


TRANSFORM_SQL = """
SET TimeZone = 'UTC';
CREATE TEMP TABLE raw AS
SELECT * FROM read_json('{raw}', format='newline_delimited', columns={{
  'EMBALSE_ID':'INTEGER','embalse_nombre':'VARCHAR','ambito_nombre':'VARCHAR',
  'agua_total':'DOUBLE','agua_actual':'DOUBLE','energia_total':'DOUBLE','energia_actual':'DOUBLE',
  'fecha':'BIGINT','Fecha_str':'VARCHAR','boletin_anyo':'INTEGER','boletin_num':'INTEGER',
  'Variacion_Reserva':'DOUBLE','Porcentaje_Reserva':'DOUBLE','ID_Unico':'VARCHAR','oid':'BIGINT'}});
-- The layer also holds ~42.6k orphan rows with no EMBALSE_ID and no fecha (and a bogus
-- boletin_anyo = 3); they cannot be keyed and are dropped.
-- fecha is 00:00 UTC of the bulletin's Tuesday. Reading it as a Europe/Madrid calendar date
-- gives the same day for 00:00 UTC and would also be right for epoch ms at local midnight
-- (which falls on the previous day in UTC).
CREATE TEMP TABLE keyed AS
SELECT *, CAST(timezone('Europe/Madrid', to_timestamp(fecha / 1000)) AS DATE) AS bulletin_date
FROM raw WHERE EMBALSE_ID IS NOT NULL AND fecha IS NOT NULL;
-- One row per (reservoir_id, bulletin_date): keep the newest object id if the layer repeats one.
CREATE TEMP TABLE dedup AS
SELECT * EXCLUDE (rn) FROM (
  SELECT *, row_number() OVER (PARTITION BY EMBALSE_ID, bulletin_date ORDER BY oid DESC) AS rn
  FROM keyed)
WHERE rn = 1;
SELECT (SELECT count(*) FROM raw) AS raw_rows,
       (SELECT count(*) FROM raw) - (SELECT count(*) FROM keyed) AS dropped_unkeyed,
       (SELECT count(*) FROM keyed) - (SELECT count(*) FROM dedup) AS dropped_duplicates,
       (SELECT count(*) FROM dedup WHERE dayofweek(bulletin_date) <> 2) AS not_tuesday,
       (SELECT count(*) FROM dedup) AS rows_out;
COPY (
  SELECT EMBALSE_ID AS reservoir_id,
         bulletin_date,
         boletin_anyo AS bulletin_year,
         boletin_num AS bulletin_number,
         agua_actual AS stored_volume_hm3,
         agua_total AS capacity_hm3,
         CASE WHEN agua_total IS NULL OR agua_total = 0 THEN NULL
              ELSE round(agua_actual / agua_total * 100, 2) END AS fill_pct,
         agua_actual - lag(agua_actual) OVER (PARTITION BY EMBALSE_ID ORDER BY bulletin_date)
           AS weekly_change_hm3,
         energia_actual AS stored_energy_gwh,
         energia_total AS energy_capacity_gwh,
         '{source}' AS source
  FROM dedup
  ORDER BY bulletin_date, reservoir_id
) TO '{out}' (FORMAT parquet, COMPRESSION zstd);
"""


def transform(raw, out):
    duckdb = shutil.which("duckdb") or "/opt/homebrew/bin/duckdb"
    sql = TRANSFORM_SQL.format(raw=raw, out=out, source=SOURCE)
    subprocess.run([duckdb, "-c", sql], check=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    out_dir = os.path.abspath(args[0])
    os.makedirs(os.path.join(out_dir, "raw"), exist_ok=True)
    raw = os.path.join(out_dir, "raw", "reservoir_weekly.ndjson")
    if "--skip-fetch" not in sys.argv:
        print(f"fetched {fetch(raw)} rows -> {raw}", file=sys.stderr)
    parquet = os.path.join(out_dir, "reservoir_weekly.parquet")
    transform(raw, parquet)
    print(f"wrote {parquet}", file=sys.stderr)


if __name__ == "__main__":
    main()
