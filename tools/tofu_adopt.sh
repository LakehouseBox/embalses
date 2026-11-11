#!/bin/sh
# Adopt the embalses catalog that already runs on LakehouseBox into OpenTofu state, then show the plan.
# Read-only against LakehouseBox: `tofu import` and `tofu plan` change nothing there.
# Needs LHBOX_API_KEY in the environment, `lhbox` signed in (to look up the sink ids) and `tofu` initialised.
set -eu
cd "$(dirname "$0")/.."
tofu import lakehousebox_catalog.embalses embalses
LHBOX_NO_VERSION_CHECK=1 lhbox sink list | python3 -c '
import json, sys
d = json.load(sys.stdin); sinks = d if isinstance(d, list) else d.get("sinks") or d.get("items") or []
ingest = ["saih_ebro", "saih_guadalquivir", "saih_segura", "saih_minosil", "saih_cantabrico", "saih_guadiana", "miteco_reservoir_weekly", "aemet_precipitation", "aemet_weather"]
ids = {s["name"]: s["sink_id"] for s in sinks if not s.get("deleted_at")}
for n in ingest: print("lakehousebox_sql_sink.ingest[\"%s\"] %s" % (n, ids[n]))
for n in ("now_rain_grid", "now_upstream_rain", "now_reservoir_status", "now_basin_summary", "now_station_status"): print("lakehousebox_sql_sink.derived[\"%s\"] %s" % (n, ids[n]))
' | while read -r address id; do tofu import "$address" "$id"; done
tofu plan
