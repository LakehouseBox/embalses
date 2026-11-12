#!/bin/sh
# Adopt the embalses catalog that already runs on LakehouseBox into OpenTofu state, then show the plan.
# Read-only against LakehouseBox: `tofu import` and `tofu plan` change nothing there.
# Needs LHBOX_API_KEY in the environment, `lhbox` signed in (to look up the sink ids), `tofu init` done,
# and provider >= 0.1.1 (earlier versions import only the catalog and the sinks).
set -eu
cd "$(dirname "$0")/.."
have=$(tofu state list 2>/dev/null || true)
adopt() {   # skip what is already in state; retry, because 40 imports in a row do meet the odd network timeout
  printf '%s\n' "$have" | grep -qxF "$1" && return 0
  tofu import "$1" "$2" || { sleep 5; tofu import "$1" "$2"; } || { sleep 15; tofu import "$1" "$2"; }
}

adopt lakehousebox_catalog.embalses embalses
adopt lakehousebox_catalog_agents_md.embalses embalses
adopt lakehousebox_sql_connection.aemet 'embalses|aemet'
for p in https://saihweb.chsegura.es/apps/iVisor/ https://visor.saichcantabrico.es/wp-admin/ https://siraguadiana.com/backend/; do
  adopt "lakehousebox_sql_post_prefix.saih[\"$p\"]" "embalses|$p"
done
python3 -c 'import json; [print(t) for t in json.load(open("docs/table_docs.json"))]' | while read -r t; do
  adopt "lakehousebox_table_description.docs[\"$t\"]" "embalses|$t"
done
LHBOX_NO_VERSION_CHECK=1 lhbox sink list | python3 -c '
import json, sys
d = json.load(sys.stdin); sinks = d if isinstance(d, list) else d.get("sinks") or d.get("items") or []
ingest = ["saih_ebro", "saih_guadalquivir", "saih_segura", "saih_minosil", "saih_cantabrico", "saih_guadiana", "miteco_reservoir_weekly", "aemet_precipitation", "aemet_weather"]
ids = {s["name"]: s["sink_id"] for s in sinks if not s.get("deleted_at")}
for n in ingest: print("lakehousebox_sql_sink.ingest[\"%s\"] %s" % (n, ids[n]))
for n in ("now_rain_grid", "now_upstream_rain", "now_reservoir_status", "now_basin_summary", "now_station_status"): print("lakehousebox_sql_sink.derived[\"%s\"] %s" % (n, ids[n]))
' | while read -r address id; do adopt "$address" "$id"; done
tofu plan "$@"
