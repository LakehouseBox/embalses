"""AEMET OpenData station inventory -> data/raw/aemet/stations.json (UTF-8).

Source: /api/valores/climatologicos/inventarioestaciones/todasestaciones (two-step: the
response's `datos` URL holds the list). Coordinates come as DMS strings ("394924N", "0055354W").
Needs AEMET_API_KEY in the environment.
"""
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://opendata.aemet.es/opendata/api/valores/climatologicos/inventarioestaciones/todasestaciones"


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode(r.headers.get_content_charset() or "iso-8859-15")


def dms(s):
    """'394924N' -> 39.823333; '0055354W' -> -5.898333"""
    hemi, digits = s[-1], s[:-1]
    deg, mins, secs = int(digits[:-4]), int(digits[-4:-2]), int(digits[-2:])
    v = deg + mins / 60 + secs / 3600
    return -v if hemi in "SW" else v


def main():
    meta = json.loads(get(API, {"api_key": os.environ["AEMET_API_KEY"]}))
    rows = json.loads(get(meta["datos"]))
    out = [dict(native_code=r["indicativo"], station_name=r["nombre"], province=r.get("provincia"),
                elevation_m=float(r["altitud"]) if r.get("altitud") else None,
                lat=dms(r["latitud"]), lon=dms(r["longitud"]), wmo_id=r.get("indsinop") or None) for r in rows]
    path = os.path.join(ROOT, "data", "raw", "aemet", "stations.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"{len(out)} AEMET stations -> {path}")


if __name__ == "__main__":
    main()
