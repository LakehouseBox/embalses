"""Ebro river basin: where each municipality's tap water is taken, from the CHE register of drinking-water intakes.

The 2022-2027 Ebro plan (Anejo 03, Apéndice 03.03) describes 51 urban demand units (UDU) but publishes no
UDU -> municipality list, and CHE's GIS services have no UDU layer. What CHE does publish, per intake, is its
Registro de Zonas Protegidas, "captaciones de agua para abastecimiento" (art. 7 DMA), in its SITEbro map server:
  https://sitebro-srv.chebro.es/server/rest/services/Sitebro_Internet/Medio_ambiente/MapServer/2  (surface, ~480)
  https://sitebro-srv.chebro.es/server/rest/services/Sitebro_Internet/Medio_ambiente/MapServer/3  (groundwater, ~2,200)
Each intake (COD_TOMA) has its type, toponym, water body (Masa_agua, UBIC) and the population units it serves:
  "Nº localidades: 6 - ARANDA DE MONCAYO (hab: 114; uso: Principal; prov: Zaragoza); BREA DE ARAGÓN (...)"
Those localidades are INE population units (entidades / núcleos), not municipalities, so they are placed in their
municipality with INE's own list of population units (Callejero del Censo Electoral, file UP):
  https://www.ine.es/prodyser/callejero/caj_esp/caj_esp_072025.zip

Model (our codes, see meta.json): one supply unit per municipality, "ZPA-<INE code>". Each intake that serves the
municipality's main population unit (the one named like the municipality, else the most populated one listed) is a
source with role main (uso Principal) or backup (uso Complementario); intakes that serve only other units of the
municipality are role minor and say which units in notes.

Writes, into OUT_DIR (default data/raw/plans/ebro): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md).

Usage: python3 tools/extract_supply_ebro.py [OUT_DIR]
"""
import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.request
import zipfile

LAYER = ("https://sitebro-srv.chebro.es/server/rest/services/Sitebro_Internet/Medio_ambiente/MapServer/{layer}/query"
         "?where=1%3D1&outFields=*&returnGeometry=false&orderByFields=OBJECTID&resultOffset={o}"
         "&resultRecordCount=1000&f=json")
LAYERS = {2: "che_captaciones_abastecimiento_superficiales.json", 3: "che_captaciones_abastecimiento_subterraneas.json"}
CALLEJERO = "https://www.ine.es/prodyser/callejero/caj_esp/caj_esp_072025.zip"
UA = "embalses-open-data/0.1"
REFERENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "ine",
                         "municipalities_reference.csv")
PROVINCES = {"Alava": "01", "Barcelona": "08", "Burgos": "09", "Cantabria": "39", "Castellón/Castelló": "12",
             "Girona": "17", "Guadalajara": "19", "Huesca": "22", "Lleida": "25", "Navarra": "31",
             "Rioja (La)": "26", "Soria": "42", "Tarragona": "43", "Teruel": "44", "Vizcaya": "48", "Zaragoza": "50"}
# Municipalities the register still lists under a former name (INE code of the municipality, current name).
RENAMED = {("50", "JARQUE"): "50130",                       # Jarque de Moncayo
           ("43", "SANT CARLES DE LA RÀPITA"): "43136",     # La Ràpita
           ("43", "BISBAL DE FALSET (LA)"): "43027",        # La Bisbal de Montsant
           ("12", "HERBÉS"): "12068",                       # Herbers
           ("09", "SANTA MARÍA RIVARREDONDA"): "09353"}     # Santa María Ribarredonda
LOCALITY = re.compile(r"\s*(.+?) \(hab: (\d+); uso: (\w+); prov: (.*?)\)(?=;|$)")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def download(out_dir):
    for layer, name in LAYERS.items():
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            continue
        feats, o = [], 0
        while True:
            page = json.loads(fetch(LAYER.format(layer=layer, o=o)))["features"]
            feats += [f["attributes"] for f in page]
            if len(page) < 1000:
                break
            o += 1000
        with open(path, "w") as f:
            json.dump(feats, f, ensure_ascii=False, indent=0)
    path = os.path.join(out_dir, os.path.basename(CALLEJERO))
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(fetch(CALLEJERO))
    return path


def norm(name):
    """'ARCOS (LOS)', 'Arcos, Los', 'Los Arcos' -> 'ARCOS'; accents and punctuation dropped."""
    s = unicodedata.normalize("NFD", name.upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s*\((?:EL|LA|LOS|LAS|L'|LO|ELS|LES|O|A|OS|AS)\)\s*$", "", s)
    s = re.sub(r",\s*(?:EL|LA|LOS|LAS|L'|LO|ELS|LES|O|A|OS|AS)\s*$", "", s)
    s = re.sub(r"^(?:EL|LA|LOS|LAS|LO|ELS|LES)\s+|^L'", "", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def variants(name):
    out = {norm(name)}
    if "/" in name:
        out |= {norm(p) for p in name.split("/")}
    return {v for v in out if v}


def load_reference():
    with open(REFERENCE, newline="") as f:
        return {r["municipality_code"]: r for r in csv.DictReader(f)}


def municipality_index(ref):
    idx = {}
    for code, r in ref.items():
        for v in variants(r["official_name"]):
            idx.setdefault((code[:2], v), set()).add(code)
    return idx


def entity_index(zip_path, provinces):
    """(province, normalised name) -> municipality codes, from every name in INE's population-unit file."""
    idx = {}
    with zipfile.ZipFile(zip_path) as z:
        member = next(n for n in z.namelist() if "/UP." in n)
        for line in io.TextIOWrapper(z.open(member), encoding="latin-1"):
            if line[:2] not in provinces:
                continue
            for m in re.finditer(r"\S+(?: \S+)*", line[160:]):
                if m.group() == "*DISEMINADO*":
                    continue
                for v in variants(m.group()):
                    idx.setdefault((line[:2], v), set()).add(line[:5])
    return idx


def smart_title(s):
    small = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "a", "d", "l", "i", "dels", "les"}
    words = re.split(r"(\s+|-|/|')", s.lower())
    out = []
    for i, w in enumerate(words):
        if re.fullmatch(r"[ivx]+", w) and len(w) <= 4:
            out.append(w.upper())
        elif w in small and i > 0:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return "".join(out)


def tidy(s):
    return re.sub(r"\s+", " ", (s or "").replace('"', "")).strip(" .,;-")


def source_of(rec, surface):
    """(source_type, source_name, water_body_code, note) for one register intake."""
    kind, topo, ubic, masa = rec["TIPO_TOMA"], tidy(rec["TOPONIMIA"]), tidy(rec["UBIC"]), rec["Masa_agua"] or 0
    code = rec["COD_TOMA"]
    if not surface:
        wb = f"ES091MSBT{int(masa):03d}" if masa else ""
        body = "" if not ubic or ubic.upper().startswith("SIN DEFINIR") else smart_title(ubic)
        if kind in ("Manantial", "Fuente"):
            name = re.sub(r"^(?:MANANTIAL(?:ES)?|Manantial(?:es)?)\s+(?:(?:DE|de)\s+(?:(?:LA|LAS|LOS|EL)\s+)?)?", "", topo)
            name = smart_title(name) if name.isupper() else name
            return "spring", name, wb, f"CHE intake {code}" + (f"; groundwater body {body}" if body else "")
        return "aquifer", body, wb, f"CHE intake {code}: {kind.lower()} {topo}"
    wb = f"ES091MSPF{int(masa)}" if masa else ""
    m = re.match(r"Embalse (?:de |del )?(.+)$", ubic)
    if m:   # intake in, or in a canal fed by, a reservoir water body
        note = f"CHE intake {code}" + ("" if kind == "Lago/Ibón/Embalse" else f" via {topo}")
        return "reservoir", m.group(1), wb, note
    m = re.match(r"((?:Río|Arroyo|Barranco|Regato) .+?)(?: desde | hasta |\.|\(|$)", ubic)
    if m and kind != "Lago/Ibón/Embalse":
        name = tidy(m.group(1))
        note = f"CHE intake {code}" + ("" if kind == "Directa de cauce" else f" via {topo}")
        return "river", name[0].lower() + name[1:], wb, note
    if kind == "Lago/Ibón/Embalse":   # reservoir not a water body of its own (Urdalur, Mairaga, ibones)
        name = re.sub(r"^(?:EMBALSE|Embalse)\s+(?:(?:DE|DEL|de|del)\s+)?", "", topo)
        name = smart_title(name) if name.isupper() else name
        return "reservoir", name, wb, f"CHE intake {code}" + ("; mountain lake" if "bón" in topo.lower() else "")
    if ubic.startswith("Canal Imperial"):
        return "river", "Canal Imperial de Aragón", wb, f"CHE intake {code}; canal (artificial water body)"
    m = re.match(r"(?i)((?:r[ií]o|arroyo|barranco|regato|riera|torrent)\s+.+?)(?:\s+[-–(.,]|$)", topo)
    name = smart_title(m.group(1)) if m else ""
    name = name[:1].lower() + name[1:] if name else ""
    return "river", name, wb, f"CHE intake {code}: {topo}" + ("" if masa else "; not linked to a water body")


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/ebro"
    os.makedirs(out_dir, exist_ok=True)
    zip_path = download(out_dir)
    ref = load_reference()
    by_name = municipality_index(ref)
    by_entity = entity_index(zip_path, set(PROVINCES.values()))

    served = {}        # municipality -> {locality: hab}
    links = []         # (municipality, locality, intake record, surface?, uso)
    unmatched = {}
    for layer, fname in LAYERS.items():
        with open(os.path.join(out_dir, fname)) as f:
            records = json.load(f)
        for rec in records:
            body = re.sub(r"^Nº localidades: \d+ - ", "", rec["localidades"] or "")
            for loc, hab, uso, prov in LOCALITY.findall(body):
                loc = tidy(loc)
                pc = PROVINCES.get(prov)
                if not pc:
                    unmatched[(loc, prov)] = "province not recognised"
                    continue
                cands = {RENAMED[(pc, loc)]} if (pc, loc) in RENAMED else set()
                for v in variants(loc):
                    cands |= by_name.get((pc, v), set())
                if not cands:
                    for v in variants(loc):
                        cands |= by_entity.get((pc, v), set())
                cands &= set(ref)
                if len(cands) != 1:
                    unmatched[(loc, prov)] = (f"ambiguous: population units with this name in {len(cands)} municipalities"
                                              if cands else "no INE municipality or population unit with this name")
                    continue
                mun = cands.pop()
                served.setdefault(mun, {})[loc] = max(int(hab), served.get(mun, {}).get(loc, 0))
                links.append((mun, loc, rec, layer == 2, uso))

    core = {}
    for mun, locs in served.items():
        own = variants(ref[mun]["official_name"])
        named = [l for l in locs if variants(l) & own]
        core[mun] = named[0] if named else max(locs, key=locs.get)

    per_intake = {}    # (municipality, intake code) -> intake record, surface?, uso for the main unit, other units
    for mun, loc, rec, surface, uso in links:
        e = per_intake.setdefault((mun, rec["COD_TOMA"], surface), {"rec": rec, "uso": None, "others": set()})
        if loc == core[mun]:
            e["uso"] = uso if e["uso"] in (None, "Complementario") else e["uso"]
        else:
            e["others"].add(loc)
    sources, descr = {}, {}
    for (mun, _, surface), e in per_intake.items():
        rec = e["rec"]
        kind, name, wb, note = source_of(rec, surface)
        role = {"Principal": "main", "Complementario": "backup", None: "minor"}[e["uso"]]
        entry = sources.setdefault(mun, {}).setdefault((kind, name, wb, role), {"notes": [], "locs": set()})
        entry["notes"].append(note)
        if role == "minor":
            entry["locs"] |= e["others"]
        d = f"{tidy(rec['TOPONIMIA'])} [{rec['TIPO_TOMA']}; {e['uso'] or 'only ' + ', '.join(sorted(e['others']))}]"
        descr.setdefault(mun, []).append(d)

    order = {"main": 0, "backup": 1, "minor": 2}
    munis = sorted(sources)
    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for mun in munis:
            w.writerow([f"ZPA-{mun}", f"Abastecimiento de {ref[mun]['official_name']}"])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for mun in munis:
            w.writerow([mun, f"ZPA-{mun}", "", "; ".join(descr[mun]), ""])
    n_src = 0
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        for mun in munis:
            items = sorted(sources[mun].items(), key=lambda kv: (order[kv[0][3]], kv[0][0] != "reservoir"))
            for rank, ((kind, name, wb, role), e) in enumerate(items, 1):
                notes = "; ".join(e["notes"][:6]) + (f"; +{len(e['notes']) - 6} more intakes" if len(e["notes"]) > 6 else "")
                if e["locs"]:
                    notes += "; serves only " + ", ".join(sorted(e["locs"])[:8]) + (" …" if len(e["locs"]) > 8 else "")
                w.writerow([f"ZPA-{mun}", mun, rank, kind, name, role, wb, "", notes])
                n_src += 1
    with open(os.path.join(out_dir, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_name", "province_hint", "reason"])
        for (loc, prov), reason in sorted(unmatched.items()):
            w.writerow([loc, prov, reason])
    meta = {
        "plan": "ebro", "basin_id": "ES091", "source": "che-zonas-protegidas-abastecimiento", "plan_cycle": "2022-2027",
        "source_document": ("Confederación Hidrográfica del Ebro, Registro de Zonas Protegidas: captaciones de agua "
                            "para abastecimiento (superficiales y subterráneas), SITEbro map service, layers 2 and 3; "
                            "population units placed in municipalities with INE Callejero del Censo Electoral "
                            "(unidades poblacionales, 30/06/2025)"),
        "source_url": "https://sitebro-srv.chebro.es/server/rest/services/Sitebro_Internet/Medio_ambiente/MapServer",
        "notes": (f"{len(munis)} municipalities, {n_src} source rows, {len(unmatched)} unmatched population units. "
                  "The plan's 51 UDU fichas (Anejo 03, Apéndice 03.03) publish no UDU -> municipality list and CHE "
                  "serves no UDU layer, so this folder uses CHE's register of drinking-water intakes instead, which "
                  "lists per intake the population units served (INE names, inhabitants, uso Principal/Complementario). "
                  "unit_code is ours: one unit per municipality, ZPA-<INE code>. Roles: main/backup = intake serves "
                  "the municipality's main population unit with uso Principal/Complementario; minor = serves only "
                  "other units of the municipality (named in notes). Canal intakes are attributed to the water body "
                  "the register links them to (e.g. Acequia de Sora -> Embalse de Yesa, for Zaragoza). The register "
                  "also lists municipalities outside the Ebro district supplied by transfers (Bilbao from the "
                  "Zadorra reservoirs, Santander and Torrelavega from the Embalse del Ebro, the Tarragona coast "
                  "from the Ebro at Xerta). water_body_code is built from the register's Masa_agua number "
                  "(ES091MSPF<n> surface, ES091MSBT<nnn> groundwater). Population units whose name is not unique "
                  "in their province are left in unmatched.csv.")}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(munis)} municipalities, {n_src} sources, {len(unmatched)} unmatched -> {out_dir}")


if __name__ == "__main__":
    main()
