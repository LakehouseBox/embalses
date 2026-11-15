"""Download the official sources ref.municipalities is built from.

- INE, Relación de municipios y sus códigos (1 January of the given year), xlsx:
    https://www.ine.es/daco/daco42/codmun/diccionario<YY>.xlsx
- INE, Cifras oficiales de población de los municipios españoles (Revisión del Padrón), one table per province,
  through the Tempus API with metadata (tip=AM) so every value carries its municipality code:
    https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/<table>?nult=1&tip=AM   (the per-province tables among ids 2852-2909)
- IGN municipal boundaries (Líneas límite municipales, "recintos_municipales_inspire"; NATCODE ends in the INE code):
  · peninsula, Balearic Islands, Ceuta and Melilla: IGN's file as MITECO hosts it on ArcGIS Online, simplified by the
    server to ~20 m (maxAllowableOffset):
    https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/recintos_municipales_inspire_peninbal_etrs89
  · Canary Islands (not in that file): IGN's INSPIRE administrative units WFS, island by island (the service times out
    on large requests): https://www.ign.es/wfs-inspire/unidades-administrativas
  · municipalities created after that file (segregations such as Valderrubio or El Palmar de Troya): the same WFS,
    one request per INE code that no file above covers. sql/reference/municipalities.sql cuts them out of the older
    outline they were taken from.

Usage: python3 tools/fetch_municipalities.py [OUT_DIR] [YEAR]   (defaults: data/raw, 2026)
Writes OUT_DIR/ine/diccionario<YY>.xlsx, OUT_DIR/ine/population/t<table>.json,
OUT_DIR/ign/peninbal_<offset>.geojson, OUT_DIR/ign/canarias_<island>.geojson and OUT_DIR/ign/new_<code>.geojson.
"""
import json
import os
import re
import urllib.parse
import zipfile
import sys
import time
import urllib.error
import urllib.request

UA = "embalses-open-data/0.1 (+https://github.com)"
RECINTOS = ("https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/"
            "recintos_municipales_inspire_peninbal_etrs89/FeatureServer/0/query?where=1%3D1"
            "&outFields=NATCODE,NAMEUNIT,NATLEVEL&outSR=4326&maxAllowableOffset=0.0002"
            "&resultOffset={o}&resultRecordCount=2000&f=geojson")
IGN_WFS = ("https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&version=2.0.0&request=GetFeature"
           "&typeNames=au:AdministrativeUnit&outputFormat=application/geo%2Bjson&count=100"
           "&BBOX={s},{w},{n},{e},urn:ogc:def:crs:EPSG::4258")
IGN_CODE = ("https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&version=2.0.0&request=GetFeature"
            "&typeNames=au:AdministrativeUnit&outputFormat=application/geo%2Bjson&FILTER=")
FILTER = ('<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" xmlns:au="http://inspire.ec.europa.eu/schemas/au/4.0">'
          '<fes:PropertyIsEqualTo><fes:ValueReference>au:nationalCode</fes:ValueReference>'
          '<fes:Literal>{code}</fes:Literal></fes:PropertyIsEqualTo></fes:Filter>')
ISLANDS = {   # south, west, north, east (EPSG:4258 axis order is latitude, longitude)
    "el_hierro": (27.62, -18.17, 27.86, -17.87), "la_palma": (28.44, -18.02, 28.86, -17.71),
    "la_gomera": (28.00, -17.36, 28.23, -17.08), "tenerife": (27.99, -16.93, 28.60, -16.11),
    "gran_canaria": (27.73, -15.84, 28.19, -15.35), "fuerteventura": (28.03, -14.52, 28.76, -13.82),
    "lanzarote": (28.83, -13.88, 29.43, -13.40),
}


def get(url, timeout=120, tries=6):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"  retry {attempt + 1}: HTTP {e.code}", flush=True)
            time.sleep(10 * (attempt + 1))
        except Exception as e:
            print(f"  retry {attempt + 1}: {type(e).__name__}: {e}", flush=True)
            time.sleep(10 * (attempt + 1))
    raise SystemExit(f"could not fetch {url}")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    yy = f"{year % 100:02d}"

    os.makedirs(f"{out}/ine/population", exist_ok=True)
    path = f"{out}/ine/diccionario{yy}.xlsx"
    if not os.path.exists(path):
        open(path, "wb").write(get(f"https://www.ine.es/daco/daco42/codmun/diccionario{yy}.xlsx"))
    print("INE municipality list:", path)

    for table in range(2852, 2910):
        path = f"{out}/ine/population/t{table}.json"
        if not os.path.exists(path):   # the ids are not contiguous: a missing table answers 404 and is skipped
            body = get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult=1&tip=AM")
            if body:
                open(path, "wb").write(body)
    print("INE population tables:", f"{out}/ine/population/")

    os.makedirs(f"{out}/ign", exist_ok=True)
    offset = 0
    while True:
        path = f"{out}/ign/peninbal_{offset:05d}.geojson"
        if not os.path.exists(path):
            open(path, "wb").write(get(RECINTOS.format(o=offset)))
        data = json.load(open(path))
        if not data.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(data["features"])
    print("IGN boundaries, peninsula and Balearics:", offset + len(data["features"]), "features")

    for island, (s_, w, n, e) in ISLANDS.items():   # keeps only municipalities (the WFS also returns province, region, country)
        path = f"{out}/ign/canarias_{island}.geojson"
        if not os.path.exists(path):
            data = json.loads(get(IGN_WFS.format(s=s_, w=w, n=n, e=e), timeout=280))
            data["features"] = [f for f in data["features"]
                                if f["properties"]["nationalLevelName"]["LocalisedCharacterString"] == "Municipio"]
            json.dump(data, open(path, "w"))
        print(f"IGN boundaries, {island}:", len(json.load(open(path))["features"]), "municipalities")

    # Municipalities in INE's list that no boundary file covers: ask the WFS for each by its national code.
    covered = set()
    for name in os.listdir(f"{out}/ign"):
        for f in json.load(open(f"{out}/ign/{name}"))["features"]:
            p = f["properties"]
            covered.add((p.get("NATCODE") or p.get("nationalCode"))[-5:])
    for code, region in ine_codes(f"{out}/ine/diccionario{yy}.xlsx"):
        path = f"{out}/ign/new_{code}.geojson"
        if code in covered or os.path.exists(path):
            continue
        national = f"34{region}{code[:2]}{code}"
        body = get(IGN_CODE + urllib.parse.quote(FILTER.format(code=national)))
        if body and json.loads(body)["features"]:
            open(path, "wb").write(body)
            print("IGN boundary, new municipality:", code)
        else:
            print("IGN boundary not found:", code)


def ine_codes(xlsx):
    """(municipality code, region code) for every row of INE's list, read from the xlsx with the standard library."""
    z = zipfile.ZipFile(xlsx)
    strings = [re.sub(r"<[^>]+>", "", s) for s in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    for row in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = {}
        for ref, typ, val in re.findall(r'<c r="([A-Z]+)\d+"(?:[^>]*t="(\w+)")?[^>]*>(?:<v>(.*?)</v>)?', row):
            cells[ref] = strings[int(val)] if typ == "s" and val else val
        if (cells.get("B") or "").isdigit() and (cells.get("C") or "").isdigit():
            yield cells["B"].zfill(2) + cells["C"].zfill(3), (cells.get("A") or "").zfill(2)

if __name__ == "__main__":
    main()
