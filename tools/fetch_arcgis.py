"""Download the MITECO layers the reference tables are built from, as GeoJSON (EPSG:4326).

Source: MITECO's public ArcGIS Online services (no key):
  https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services
Pages through each layer (resultOffset) so layers above the server's maxRecordCount come whole.

Usage: python3 tools/fetch_arcgis.py [OUT_DIR]   (default: data/raw/arcgis)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services"
UA = "embalses-open-data/0.1 (+https://github.com)"

# file name -> (service, layer id, extra query params)
LAYERS = {
    "bulletin_reservoirs": ("Embalses_Mapa", 0, {}),
    "reservoir_outlines": ("Láminas_Embalses", 0, {}),
    "dam_inventory": ("UP_Presas_y_embalses", 0, {}),
    "basin_districts": ("Demarcaciones", 0, {"maxAllowableOffset": "0.002"}),  # ~200 m simplification
    "saih_reservoir_points": ("SAIH", 3, {}),
    "saih_rain_gauges": ("SAIH", 4, {}),
    "saih_river_gauges": ("SAIH", 5, {}),
    "gauging_stations_roea": ("SAIH", 1, {}),
}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_layer(service, layer, extra):
    url = f"{BASE}/{urllib.parse.quote(service)}/FeatureServer/{layer}"
    info = get_json(url + "?f=json")
    page = int(info.get("maxRecordCount") or 1000)
    feats, offset = [], 0
    while True:
        q = {"where": "1=1", "outFields": "*", "outSR": "4326", "f": "geojson",
             "orderByFields": info.get("objectIdField") or "OBJECTID",
             "resultOffset": str(offset), "resultRecordCount": str(page), **extra}
        fc = get_json(url + "/query?" + urllib.parse.urlencode(q))
        batch = fc.get("features", [])
        feats += batch
        if len(batch) < page and not fc.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(batch)
        time.sleep(0.3)
    return {"type": "FeatureCollection", "features": feats}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw", "arcgis")
    os.makedirs(out, exist_ok=True)
    for name, (service, layer, extra) in LAYERS.items():
        fc = fetch_layer(service, layer, extra)
        path = os.path.join(out, f"{name}.geojson")
        with open(path, "w") as f:
            json.dump(fc, f)
        print(f"{name}: {len(fc['features'])} features -> {path}")
        time.sleep(0.5)


if __name__ == "__main__":
    main()
