"""Duero river-basin plan 2022-2027: which supply unit (UDU) serves each municipality, and where it takes its water.

Sources, all from the Confederación Hidrográfica del Duero (CHD):
  1. Open data "Demandas urbanas" (datos.chduero.es, on datos.gob.es as ea0043420-demandas-urbanas): the plan's urban
     demand units. Sheet "Datos generales" gives code and name of each UDU; sheet "Tomas, retornos e infraestructuras"
     gives, per UDU, the water bodies it takes water from ("Toma") with the % split between them.
       https://datos.chduero.es/data-integration/Demandas%20urbanas/Demandas%20urbanas%20-%20CSV.zip
  2. Mírame-IDEDuero (the CHD geoportal, same database as the open data) WFS layers:
       mirame:Unidades_Elementales_Demanda_Urbana  one row per population nucleus: UDU code, CHD nucleus code, and the
                                                    nucleus' 11-digit INE code (province+municipality+entidad+núcleo)
       mirame:Nucleos_Poblacion                    permanent population of each nucleus
     The first 5 digits of the INE code are the municipality, so no name matching is needed.
  3. The masas de agua open data (río, embalse, subterránea, canal, lago) to turn the CHD element codes of the intakes
     into European water body codes (ES020MSPF…, ES020MSBT…).
  4. Cross-check only: Anejo 6, Apéndice I of the plan, which lists UDU code and nucleus code for every nucleus
     (it uses an earlier UDU coding for part of the nuclei; the agreement rate is printed and stored in meta.json).

A municipality whose nuclei fall in several UDUs gets one row per UDU, with share_pct = share of the municipality's
nucleus population (within the Duero layer) that the UDU serves.

Writes, into OUT_DIR (default data/raw/plans/duero): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv. Downloads are kept in OUT_DIR/source/.

Usage: uv run --with pdfplumber python tools/extract_supply_duero.py [OUT_DIR]
"""
import collections
import csv
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

import pdfplumber

DATA = "https://datos.chduero.es/data-integration/"
DEMANDS_ZIP = DATA + "Demandas urbanas/Demandas urbanas - CSV.zip"
WATER_BODY_ZIPS = {
    "Masa río": DATA + "Masas de agua río/Masas Rio - CSV.zip",
    "Masa embalse": DATA + "Masas de agua embalse/Masas Embalse - CSV.zip",
    "Masa subterránea": DATA + "Masas de agua subterráneas/Masas Subterraneas - CSV.zip",
    "Masa canal": DATA + "Masas de agua canal/Masas Canal - CSV.zip",
    "Masa lago": DATA + "Masas de agua lago/Masas Lago - CSV.zip",
}
WFS = "https://mirame.chduero.es/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&outputFormat=csv"
UEDU_URL = WFS + "&typeNames=mirame:Unidades_Elementales_Demanda_Urbana&propertyName=code,uedu_nombre,udu,nombre_udu,nucleo,nucleo_nombre,cod_ine"
NUCLEI_URL = WFS + "&typeNames=mirame:Nucleos_Poblacion&propertyName=idm,cod_ine,nombre,pob_permament"
APPENDIX_URL = ("https://www.chduero.es/documents/20126/1883851/PHD22-27_060_01_Balances_APENDICE_I_v03.pdf/"
                "62970d1b-365b-683a-bdb7-13236f8212ce")
REFERENCE = "data/raw/ine/municipalities_reference.csv"


def download(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(urllib.parse.quote(url, safe=":/?&=%,"), headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    return path


def zip_csv(path, suffix):
    """Rows (as dicts) of the CSV in the zip whose name ends with suffix."""
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(suffix))
        text = z.read(name).decode("utf-8-sig")
    return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


def num(s):
    return float(s) if s not in ("", None) else None


def fmt(x):
    if x is None:
        return ""
    return f"{x:.1f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))


def lower_generic(name):
    """'Río Porma' -> 'río Porma', 'Azud de Riolobos' -> 'azud de Riolobos'."""
    return re.sub(r"^(Río|Ríos|Arroyo|Regueiro|Rivera|Riera|Garganta|Regato|Azud|Canal|Lago|Laguna)\b",
                  lambda m: m.group(1).lower(), name)


def source_of(kind, name):
    """CHD element type and water body name -> (source_type, source_name, notes)."""
    name = re.sub(r"\s+", " ", name).strip()
    if kind == "Masa embalse":
        if name.startswith("Azud"):
            return "river", lower_generic(name), "weir (reservoir water body)"
        n = re.sub(r"^Embalses? del?\s+", "", name)
        return "reservoir", n, ("one water body for two reservoirs" if name.startswith("Embalses") else "")
    if kind == "Masa río":
        n = re.sub(r"\s+\d+(?=\s*\(|$)", "", name)          # 'Río Porma 3' -> 'Río Porma'; 'Río Frío 1 (Segovia)'
        return "river", lower_generic(n), ""
    if kind == "Masa canal":
        return "river", lower_generic(name), "canal (canal water body)"
    if kind == "Masa lago":
        return "river", lower_generic(name), "lake or lagoon (lake water body)"
    if kind == "Masa subterránea":
        return "aquifer", name, ""
    raise ValueError(kind)


def appendix_pairs(path):
    """(UDU code, CHD nucleus code) pairs printed in Anejo 6 Apéndice I; matched by row position on each page."""
    pairs = set()
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            udus = [w for w in words if re.fullmatch(r"30\d{5}", w["text"])]
            for n in (w for w in words if re.fullmatch(r"26\d{5}", w["text"])):
                mid = (n["top"] + n["bottom"]) / 2
                best = min(udus, key=lambda w: abs((w["top"] + w["bottom"]) / 2 - mid), default=None)
                if best and abs((best["top"] + best["bottom"]) / 2 - mid) < 3:
                    pairs.add((best["text"], n["text"]))
    return pairs


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/duero"
    src = os.path.join(out_dir, "source")
    os.makedirs(src, exist_ok=True)

    demands = download(DEMANDS_ZIP, os.path.join(src, "demandas_urbanas_csv.zip"))
    units = {r["Código"]: r["Nombre"] for r in zip_csv(demands, "_Datos generales.csv")}
    intakes = [r for r in zip_csv(demands, "_Tomas, retornos e infraestructu.csv") if r["Relación"] == "Toma"]

    eu_code = {}
    for kind, url in WATER_BODY_ZIPS.items():
        path = download(url, os.path.join(src, re.sub(r"\W+", "_", url.rsplit("/", 1)[1][:-4]).lower() + ".zip"))
        for r in zip_csv(path, "_Datos generales.csv"):
            eu_code[(kind, r["Código"])] = r["Código europeo"]

    uedu = list(csv.DictReader(open(download(UEDU_URL, os.path.join(src, "mirame_uedu.csv")), encoding="utf-8")))
    nuclei = {r["idm"]: r for r in csv.DictReader(open(download(NUCLEI_URL, os.path.join(src, "mirame_nucleos.csv")), encoding="utf-8"))}
    ref = {r["municipality_code"]: r for r in csv.DictReader(open(REFERENCE, encoding="utf-8"))}

    # nucleus -> municipality, population by (municipality, unit)
    pop = collections.defaultdict(float)
    has_pop = collections.defaultdict(bool)
    unmatched = []
    for r in uedu:
        muni = r["cod_ine"][:5]
        if muni not in ref:
            unmatched.append((r["nucleo_nombre"], r["cod_ine"][:2], f"INE code {r['cod_ine']} not in municipalities_reference"))
            continue
        p = num(nuclei.get(r["nucleo"], {}).get("pob_permament")) or 0.0
        pop[(muni, r["udu"])] += p
        has_pop[(muni, r["udu"])] |= r["nucleo"] in nuclei
    by_muni = collections.defaultdict(list)
    for (muni, unit) in pop:
        by_muni[muni].append(unit)

    ms_rows, split_no_pop = [], 0
    for muni in sorted(by_muni):
        us = sorted(by_muni[muni])
        total = sum(pop[(muni, u)] for u in us)
        for u in us:
            share = ""
            if len(us) > 1:
                if total > 0:
                    share = fmt(round(100 * pop[(muni, u)] / total, 1))
                else:
                    split_no_pop += 1
            ms_rows.append((muni, u, share, "", ""))

    served_units = sorted({u for _, u, *_ in ms_rows})
    ss_rows, no_intake = [], []
    per_unit = collections.defaultdict(list)
    for r in intakes:
        per_unit[r["Código"]].append(r)
    for u in served_units:
        if u not in per_unit:
            no_intake.append(u)
        for rank, r in enumerate(per_unit.get(u, []), 1):
            kind, name, notes = source_of(r["Tipo de elemento"], r["Nombre elemento"])
            share = num(r["Reparto tomas/retornos [%]"])
            ss_rows.append((u, "", rank, kind, name, "main", eu_code.get((r["Tipo de elemento"], r["Código elemento"]), ""),
                            fmt(share), notes))

    write_csv(os.path.join(out_dir, "supply_units.csv"), ["unit_code", "unit_name"], [(u, units.get(u, "")) for u in served_units])
    write_csv(os.path.join(out_dir, "municipality_supply.csv"),
              ["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"], ms_rows)
    write_csv(os.path.join(out_dir, "supply_sources.csv"),
              ["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role", "water_body_code",
               "share_pct", "notes"], ss_rows)
    write_csv(os.path.join(out_dir, "unmatched.csv"), ["plan_name", "province_hint", "reason"], unmatched)

    # cross-check against the plan's own nucleus list (Anejo 6, Apéndice I)
    appendix = appendix_pairs(download(APPENDIX_URL, os.path.join(src, "PHD22-27_060_01_Balances_APENDICE_I_v03.pdf")))
    layer = {(r["udu"], r["nucleo"]) for r in uedu}
    same = len(appendix & layer)
    check = (f"Cross-check with Anejo 6 Apéndice I: {len(appendix)} nucleus rows, {same} ({100 * same / len(appendix):.0f}%) "
             f"in the same UDU as in Mírame; the rest carry earlier UDU codes, some no longer in the open data.")

    pop_total = sum(pop.values())
    meta = {
        "plan": "duero", "basin_id": "ES020", "source": "ph-duero-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("Plan Hidrológico de la parte española de la D.H. del Duero 2022–2027: CHD open data "
                            "'Demandas urbanas' (Datos generales; Tomas, retornos e infraestructuras) and the Mírame-IDEDuero "
                            "layers Unidades_Elementales_Demanda_Urbana and Nucleos_Poblacion"),
        "source_url": "https://datos.chduero.es/dataset/demandas-urbanas",
        "notes": (f"{len(uedu)} population nuclei (permanent population {int(pop_total):,}) assigned to {len(served_units)} UDUs; "
                  "each nucleus carries its INE code in Mírame, so municipalities are taken from the code, not matched by name. "
                  "share_pct in municipality_supply = share of the municipality's nucleus population (Mírame, Duero part only) "
                  "in that UDU, given only when the municipality is split"
                  + (f"; {split_no_pop} split rows have no population and no share" if split_no_pop else "") + ". "
                  "Sources are the UDU's 'Toma' rows with the plan's % split (empty when not given, mostly in the aggregate "
                  "'Abastecimientos ... en la unidad territorial' units, which list every water body they draw from). "
                  "Canal and lake water bodies are typed 'river' with a note. Regulating reservoirs listed as 'Infraestructura' "
                  "(not intakes) are left out. "
                  + (f"UDUs with nuclei but no intake rows: {', '.join(no_intake)}. " if no_intake else "")
                  + check),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(by_muni)} municipalities, {len(served_units)} units, {len(ms_rows)} municipality rows, "
          f"{len(ss_rows)} source rows, {len(unmatched)} unmatched nuclei -> {out_dir}")
    print(check)


if __name__ == "__main__":
    main()
