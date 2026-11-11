"""AEMET OpenData daily climatological values (all stations) -> embalses.obs.daily_weather.

Source: AEMET OpenData,
  /api/valores/climatologicos/diarios/datos/fechaini/{d0}T00:00:00UTC/fechafin/{d1}T23:59:59UTC/todasestaciones
The call answers with a `datos` URL; that file is JSON encoded ISO-8859-15, numbers with a
decimal comma. At most 15 days per call (longer ranges answer 400). AEMET publishes with a
delay of about 4 days.
  prec    = "precipitación diaria de 07 a 07" (UTC), mm; 'Ip' = <0.1 mm; 'Acum' = accumulated
  tmed/tmin/tmax = °C; hrMedia = mean relative humidity, %

Mapping (data model): station_id = 'aemet:' || indicativo, observation_date = fecha,
precipitation_mm ('Ip' -> 0.0, 'Acum'/other non-numeric -> null), hydrological_year
(year of the 1 October the date falls after), is_complete (false when prec is missing,
'Acum' or not numeric), source = 'aemet-climatological'.

Needs AEMET_API_KEY in the environment (never logged or written). Raw responses are cached
per 15-day window in OUT_DIR/raw/ so an interrupted run resumes where it stopped.

Usage: python3 tools/aemet_daily.py OUT_DIR [--start 2023-10-01] [--end YYYY-MM-DD]
  writes OUT_DIR/daily_weather.parquet (DuckDB CLI 1.5.5+ on PATH).

Loading: `lhbox table import ... --mode append` (lhbox 0.6.128 + DuckDB 1.5.5) fails on these
year()-partitioned tables ("target-file-size-bytes is currently not supported for partitioned
tables"), so load with one INSERT in `lhbox duckdb`:
  SET TimeZone='UTC'; SET preserve_insertion_order=true;
  SET ignore_target_file_size_for_partitioned_tables=true;
  INSERT INTO embalses.obs.daily_weather (<columns>) SELECT <columns> FROM read_parquet('OUT_DIR/daily_weather.parquet') ORDER BY observation_date, station_id;
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = ("https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/"
       "fechaini/{d0}T00:00:00UTC/fechafin/{d1}T23:59:59UTC/todasestaciones")
SOURCE = "aemet-climatological"
WINDOW_DAYS = 15
PAUSE_S = 2.5
NUM = re.compile(r"-?\d+(,\d+)?")


def http_get(url, headers=None):
    """GET with a pause before every request and back-off on 429 / 5xx / network errors."""
    for attempt in range(8):
        time.sleep(PAUSE_S)
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), (r.headers.get_content_charset() or "iso-8859-15")
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = min(60 * (attempt + 1), 300)
                print(f"  HTTP {e.code}, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code} for {url.split('?')[0]}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            wait = 20 * (attempt + 1)
            print(f"  network error ({e}), waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"gave up on {url.split('?')[0]}")


def fetch_window(d0, d1):
    """Records for d0..d1 (inclusive), or [] when AEMET has none (404 'no hay datos')."""
    key = os.environ["AEMET_API_KEY"]
    raw, cs = http_get(API.format(d0=d0.isoformat(), d1=d1.isoformat()), {"api_key": key})
    meta = json.loads(raw.decode(cs))
    estado = meta.get("estado")
    if estado == 404:
        return []
    if estado == 429:
        time.sleep(60)
        return fetch_window(d0, d1)
    if estado != 200:
        raise RuntimeError(f"AEMET answered {estado}: {meta.get('descripcion')}")
    raw, _ = http_get(meta["datos"])
    return json.loads(raw.decode("iso-8859-15"))


def num(v):
    if v is None or not NUM.fullmatch(v.strip()):
        return None
    return float(v.strip().replace(",", "."))


def to_row(r):
    d = dt.date.fromisoformat(r["fecha"])
    p = r.get("prec")
    p = p.strip() if isinstance(p, str) else p
    precip = 0.0 if p == "Ip" else num(p)
    return dict(
        station_id="aemet:" + r["indicativo"].strip(),
        observation_date=d.isoformat(),
        precipitation_mm=precip,
        air_temperature_mean_c=num(r.get("tmed")),
        air_temperature_min_c=num(r.get("tmin")),
        air_temperature_max_c=num(r.get("tmax")),
        relative_humidity_mean_pct=num(r.get("hrMedia")),
        hydrological_year=d.year if d.month >= 10 else d.year - 1,
        is_complete=precip is not None,
        source=SOURCE,
        prec_raw=p,  # kept in the NDJSON for QA; not written to Parquet
    )


TO_PARQUET = """
SET TimeZone = 'UTC';
COPY (
  SELECT station_id, observation_date, precipitation_mm, air_temperature_mean_c,
         air_temperature_min_c, air_temperature_max_c, relative_humidity_mean_pct,
         hydrological_year, is_complete, source
  FROM read_json('{src}', format='newline_delimited', columns={{
    'station_id':'VARCHAR','observation_date':'DATE','precipitation_mm':'DOUBLE',
    'air_temperature_mean_c':'DOUBLE','air_temperature_min_c':'DOUBLE',
    'air_temperature_max_c':'DOUBLE','relative_humidity_mean_pct':'DOUBLE',
    'hydrological_year':'INTEGER','is_complete':'BOOLEAN','source':'VARCHAR','prec_raw':'VARCHAR'}})
  ORDER BY observation_date, station_id
) TO '{out}' (FORMAT parquet, COMPRESSION zstd);
"""


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        sys.exit(__doc__)
    out_dir = os.path.abspath(args[0])
    opt = dict(zip(args[1::2], args[2::2]))
    start = dt.date.fromisoformat(opt.get("--start", "2023-10-01"))
    end = dt.date.fromisoformat(opt.get("--end", (dt.date.today() - dt.timedelta(days=1)).isoformat()))
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    rows, seen = [], set()
    d0 = start
    while d0 <= end:
        d1 = min(d0 + dt.timedelta(days=WINDOW_DAYS - 1), end)
        cache = os.path.join(raw_dir, f"aemet_daily_{d0}_{d1}.json")
        if os.path.exists(cache):
            recs = json.load(open(cache))
        else:
            recs = fetch_window(d0, d1)
            with open(cache + ".part", "w") as f:
                json.dump(recs, f, ensure_ascii=False)
            os.replace(cache + ".part", cache)
        dup = 0
        for r in recs:
            row = to_row(r)
            k = (row["station_id"], row["observation_date"])
            if k in seen:
                dup += 1
                continue
            seen.add(k)
            rows.append(row)
        print(f"{d0}..{d1}: {len(recs)} records" + (f", {dup} duplicate keys dropped" if dup else ""),
              file=sys.stderr)
        d0 = d1 + dt.timedelta(days=1)

    ndjson = os.path.join(out_dir, "daily_weather.ndjson")
    with open(ndjson, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    out = os.path.join(out_dir, "daily_weather.parquet")
    duckdb = shutil.which("duckdb") or "/opt/homebrew/bin/duckdb"
    subprocess.run([duckdb, "-c", TO_PARQUET.format(src=ndjson, out=out)], check=True)
    print(f"wrote {len(rows)} rows -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
