"""Guadiana river-basin plan 2022-2027: which supply unit serves each municipality, and where its water comes from.

Source: Plan Hidrológico de la parte española de la Demarcación Hidrográfica del Guadiana, tercer ciclo (2022-2027),
Anejo 4 "Usos y demandas", Apéndice 2 "Demanda urbana":
  https://www.chguadiana.es/sites/default/files/2023-02/ES040PH3_AN04_Apendices.pdf
  - Tabla 7 "Demanda Municipal 2021 por origen del recurso" (PDF pages ~101-117): one row per municipality with
    COD (INE code, leading zero dropped) | NOMBRE | UDU | NOMBRE | SISTEMA | SUB | POB | DEM |
    ORIGEN 1 (TOMA, DH, %) | ORIGEN 2 (…) | ORIGEN 3 (…). Horizon 2021 is the plan's current scenario
    (Tablas 8 and 9 repeat it for 2027 and 2033 and are not used).
  - Tabla 10 "Demanda 2021 por origen del recurso" (PDF pages ~149-150): every intake name (TOMA) with its type
    (SUPERFICIAL / SUBTERRÁNEO) and water-body code (ES040MSPF…, ES040MSBT…), grouped by the basin it lies in.
    Used to give each source its water_body_code.

Sources are per municipality (municipality_code filled in supply_sources.csv) with the plan's own % shares.
source_type: "E. X" = reservoir X; groundwater bodies of Tabla 10 and "Sondeo(s)" = aquifer; "Río X" = river;
"ATS" = transfer (Acueducto Tajo-Segura); a handful of special names are written out in OVERRIDES.
Sources whose DH column is not Guadiana get a note ("source in the Tajo basin").

Writes meta.json, supply_units.csv, municipality_supply.csv, supply_sources.csv (and unmatched.csv if any row cannot
be placed) into OUT_DIR (default data/raw/plans/guadiana), in the format of tools/supply_plans_format.md.

Usage (from the repo root): uv run --with pdfplumber python tools/extract_supply_guadiana.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import urllib.request

import pdfplumber

URL = "https://www.chguadiana.es/sites/default/files/2023-02/ES040PH3_AN04_Apendices.pdf"
REFERENCE = "data/raw/ine/municipalities_reference.csv"

NUM_POB = re.compile(r"\d[\d.]*")
NUM_DEM = re.compile(r"\d+,\d+")
PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
UDU = re.compile(r"A\d+[A-C]\d*")
BASINS = ("Guadiana", "Tajo", "Guadalquivir", "Segura", "Tinto-Odiel-Piedras", "TOP")

# Intake names (TOMA) that the generic rules below would misread: name -> list of (type, name, notes, split).
# "split" marks a pair the plan lists jointly with one share; both rows then get an empty share_pct.
OVERRIDES = {
    "Guadiana Transición I (Bocachanza)": [("river", "río Guadiana", "Bocachanza intake on the Guadiana (transitional water body)")],
    "Río Guadalupejo/E. Guadalupe": [("reservoir", "Guadalupe", "on the río Guadalupejo")],
    "E. Ardila /Las Culebras": [("reservoir", "Ardila", "also called Las Culebras")],
    "E. Ardila/Las Culebras": [("reservoir", "Ardila", "also called Las Culebras")],
    "E. de Rubiales/Valle de Matamoros": [("reservoir", "Rubiales", "plan name 'E. de Rubiales/Valle de Matamoros'")],
    "E. Orellana (canal)": [("reservoir", "Orellana", "through the Orellana canal")],
    "E. Alqueva (Parte española)": [("reservoir", "Alqueva", "Spanish part of the reservoir")],
    "E. Pto. Vallehermoso": [("reservoir", "Puerto de Vallehermoso", None)],
    "E. Torre de Abrahám": [("reservoir", "Torre de Abraham", "plan spells it 'Abrahám'")],
    "Laguna del Rey": [("reservoir", "Laguna del Rey", "natural lake (Lagunas de Ruidera), surface water body")],
    "Sondeo Fuera de masa": [("aquifer", None, "borehole outside a defined groundwater body")],
    "Sondeo (Fuera de masa)": [("aquifer", None, "borehole outside a defined groundwater body")],
    "Sondeos (Gvir)": [("aquifer", None, "boreholes in the Guadalquivir basin")],
    "ATS": [("transfer", "Acueducto Tajo-Segura", None)],
    "E. de Almoguera/E. de Finisterre": [("reservoir", "Almoguera", "listed jointly as 'E. de Almoguera/E. de Finisterre'"),
                                         ("reservoir", "Finisterre", "listed jointly as 'E. de Almoguera/E. de Finisterre'")],
}


def download(out_dir):
    path = os.path.join(out_dir, os.path.basename(URL))
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    return path


def clean(c):
    return re.sub(r"\s+", " ", c or "").strip()


def norm(s):
    return re.sub(r"\s+", " ", s).replace("Abrahám", "Abraham").strip().lower()


def read_tables(pdf_path):
    rows, codes = [], {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "DEMANDA URBANA A NIVEL MUNICIPAL HORIZONTE 2021" in text:
                for table in page.extract_tables():
                    for raw in table:
                        cells = [clean(c) for c in raw if clean(c)]
                        if len(cells) < 6 or not re.fullmatch(r"\d{4,5}", cells[0]):
                            continue
                        rows.append(parse_row(cells, i + 1))
            elif "DEMANDA_2021" in text:                     # Tabla 10 (two pages; the caption is on the second)
                basin = "Guadiana"
                for line in text.splitlines():
                    m = re.search(r"ORIGEN DEMARCACI[ÓO]N DEL (\w+)", line)
                    if m:
                        basin = m.group(1).capitalize()
                        continue
                    m = re.match(r"\s*(SUPERFICIAL|SUBTERR[ÁA]NEO)\s+(ES040MS\w+|sin asignar)\s+(.+?)\s+[\d.,]+\s*$", line)
                    if m:
                        code = m.group(2) if m.group(2).startswith("ES040") else ""
                        codes[norm(m.group(3))] = (m.group(1), code, basin)
    return rows, codes


def parse_row(cells, page):
    """[COD, NOMBRE, UDU, NOMBRE UDU, SISTEMA, (SUB), POB, DEM, TOMA, DH, %, TOMA, DH, %, …]"""
    k = next(j for j, c in enumerate(cells) if j > 1 and UDU.fullmatch(c))
    # POB and DEM: the first integer followed by a decimal with comma, after SISTEMA
    p = next(j for j in range(k + 3, len(cells) - 1) if NUM_POB.fullmatch(cells[j]) and NUM_DEM.fullmatch(cells[j + 1]))
    rest = cells[p + 2:]
    origins = []
    j = 0
    while j < len(rest):
        # TOMA [DH] [%]
        toma = rest[j]
        dh = pct = ""
        j += 1
        if j < len(rest) and rest[j].replace(" ", "") in BASINS:      # 'Guadalqui vir' wraps inside the cell
            dh = rest[j].replace(" ", "")
            j += 1
        if j < len(rest) and PCT.fullmatch(rest[j]):
            pct = PCT.fullmatch(rest[j]).group(1).replace(",", ".")
            j += 1
        origins.append((toma, dh, pct))
    return dict(code=cells[0].zfill(5), name=" ".join(cells[1:k]), unit_code=cells[k], unit_name=cells[k + 1],
                system=cells[k + 2], pob=cells[p], dem=cells[p + 1], origins=origins, page=page)


def classify(toma, codes):
    """-> list of (source_type, source_name, water_body_code, notes)"""
    info = codes.get(norm(toma))
    wb = info[1] if info else ""
    over = {norm(k): v for k, v in OVERRIDES.items()}
    if norm(toma) in over:
        return [(t, n, wb, notes) for t, n, notes in over[norm(toma)]]
    m = re.match(r"E\.\s*(?:de\s+)?(.+?)(?:\s*\((Tajo|Guadalquivir)\))?$", toma)   # 'E. Nogales (Tajo)'
    if m:
        return [("reservoir", m.group(1).strip(), wb, None)]
    m = re.match(r"R[íi]o\s+(.+)$", toma)
    if m:
        name = re.sub(r"\s+[IVX]+$", "", m.group(1).strip())     # 'Río Guadiana V' is a water-body segment
        return [("river", "río " + name, wb, None if name == m.group(1).strip() else f"water body '{toma}'")]
    if info and info[0].startswith("SUBTERR"):
        return [("aquifer", toma, wb, None)]
    return None


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/guadiana"
    os.makedirs(out_dir, exist_ok=True)
    rows, codes = read_tables(download(out_dir))
    ref = {}
    with open(REFERENCE, newline="") as f:
        for r in csv.DictReader(f):
            ref[r["municipality_code"]] = r["official_name"]

    units, muni, sources, unmatched, unknown = {}, [], [], [], set()
    seen = set()
    for r in rows:
        pseudo = r["code"] not in ref
        if pseudo:
            # 21999 'Abas. Chanza': the plan lumps the Huelva municipalities of unit A10C (DC Piedras, in the
            # Tinto-Odiel-Piedras district) into one row. The unit and its sources are kept at unit level.
            unmatched.append((r["name"], r["code"][:2], f"plan row {r['code']} (page {r['page']}) is not a municipality: "
                              f"an aggregate of unit {r['unit_code']} ({r['pob']} inhabitants); sources kept at unit level"))
        if (r["code"], r["unit_code"]) in seen:
            continue
        seen.add((r["code"], r["unit_code"]))
        units.setdefault(r["unit_code"], r["unit_name"])
        desc = "; ".join(f"{t} ({dh}) {p}%".replace(" ()", "") if p else f"{t} ({dh})".replace(" ()", "")
                         for t, dh, p in r["origins"])
        if not pseudo:
            muni.append([r["code"], r["unit_code"], "", desc, ""])
        rank = 0
        for toma, dh, pct in r["origins"]:
            parsed = classify(toma, codes)
            if parsed is None:
                unknown.add(toma)
                continue
            joint = len(parsed) > 1
            for kind, name, wb, notes in parsed:
                rank += 1
                info = codes.get(norm(toma))
                basin = dh or (info[2] if info else "Guadiana")
                extra = [notes] if notes else []
                if basin and basin != "Guadiana":
                    extra.append(f"source in the {basin} basin")
                if joint and pct:
                    extra.append(f"joint share {pct}%")
                if pseudo:
                    extra.append(f"plan row '{r['name']}' ({r['code']}), the unit's municipalities are not listed")
                sources.append([r["unit_code"], "" if pseudo else r["code"], rank, kind, name or "", "main", wb,
                                "" if joint else pct, "; ".join(extra)])
    if unknown:
        sys.exit(f"intake names with no rule, add them to OVERRIDES: {sorted(unknown)}")

    meta = {
        "plan": "guadiana", "basin_id": "ES040", "source": "ph-guadiana-2022-2027", "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Guadiana 2022–2027, Anejo 4 Usos y "
                           "demandas, Apéndice 2 Demanda urbana, Tabla 7 (Demanda Municipal 2021 por origen del "
                           "recurso) and Tabla 10 (water-body codes of each intake)",
        "source_url": URL,
        "notes": "Horizon 2021 (the plan's current scenario); Tablas 8-9 (2027, 2033) not used. Sources are given per "
                 "municipality with the plan's % share (up to three origins). Water-body codes come from Tabla 10. "
                 "Intakes in other basins (Tajo, Guadalquivir) keep a note; 'ATS' is the Acueducto Tajo-Segura. The "
                 "table covers municipalities supplied from the Guadiana, including some located in the Tajo, "
                 "Guadalquivir and Tinto-Odiel-Piedras districts.",
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        w.writerows(sorted(units.items()))
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        w.writerows(muni)
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        w.writerows(sources)
    upath = os.path.join(out_dir, "unmatched.csv")
    if unmatched:
        with open(upath, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["plan_name", "province_hint", "reason"])
            w.writerows(unmatched)
    elif os.path.exists(upath):
        os.remove(upath)
    print(f"{len(muni)} municipalities, {len(units)} supply units, {len(sources)} sources, "
          f"{len(unmatched)} unmatched -> {out_dir}")


if __name__ == "__main__":
    main()
