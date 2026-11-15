"""Guadalquivir river-basin plan 2022-2027: which supply unit serves each municipality, and where the unit takes its water.

Sources (approved plan, Real Decreto 35/2023; CHG folder 2564531 only — folder 2230362 is the 2021 draft):
  - Anejo 3 "Usos y demandas", Apéndice 1 "Uso Urbano", Tabla 1 "Relación de Unidades de Demanda Urbana 2021":
    https://www.chguadalquivir.es/documents/10182/2564531/PHGuadalquivir_ANEJO3_Apendice1.pdf/1e4bfcb9-e844-f3d3-8537-cfc6538f59f6
    One row per municipality: UDU name (a vertically merged cell), UDU code, municipality name, INE code, remark
    ("Se abastece con recursos de la cuenca", "En la cuenca pero no se abastece de ella", …).
  - Normativa (BOE-A-2023-3511, Anexo VII), Apéndice 7 "Asignación de recursos" (the "Principales tomas" of every
    exploitation system and the urban demands they serve) and Apéndice 4.1 (groundwater-body names):
    https://www.chguadalquivir.es/documents/10182/2564531/PHGuadalquivir_Normativa.pdf/7b425c5a-0709-3bbc-f085-3f7934855ee1
  - Memoria, section 2.2 (La Carolina intake in La Fernandina reservoir):
    https://www.chguadalquivir.es/documents/10182/2564531/PHGuadalquivir_Memoria.pdf/25f1430c-0952-0045-af17-9224edba53e9

Tabla 1 gives no intakes; sources are per unit (municipality_code empty in supply_sources.csv):
  - "…AS####" units ("Abast. MAS 1201 …") draw on groundwater body ES050MSBT00005#### (name from Normativa Ap. 4.1);
    "07AS0000" is groundwater outside the listed bodies.
  - "…AF100" units are small surface intakes (unregulated rivers and small reservoirs, Normativa Ap. 7).
  - Named units (Sevilla y entorno, Córdoba, Consorcio Quiebrajano-Víboras, …) get the reservoirs, springs and wells
    the Normativa's Apéndice 7 lists as their "Principales tomas", written out by hand in UNIT_SOURCES with the
    sub-appendix cited in notes. Water-body codes of reservoirs are copied from Normativa Apéndice 3.3.1.

Writes meta.json, supply_units.csv, municipality_supply.csv, supply_sources.csv (and unmatched.csv) into OUT_DIR
(default data/raw/plans/guadalquivir), in the format of tools/supply_plans_format.md.

chguadalquivir.es fails TLS with macOS system curl; Python urllib (OpenSSL) verifies it fine.

Usage (from the repo root): uv run --with pdfplumber python tools/extract_supply_guadalquivir.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

BASE = "https://www.chguadalquivir.es/documents/10182/2564531/"
URL_AP1 = BASE + "PHGuadalquivir_ANEJO3_Apendice1.pdf/1e4bfcb9-e844-f3d3-8537-cfc6538f59f6"
URL_NORM = BASE + "PHGuadalquivir_Normativa.pdf/7b425c5a-0709-3bbc-f085-3f7934855ee1"
REFERENCE = "data/raw/ine/municipalities_reference.csv"
UNIT = re.compile(r"\d\dA[A-Z]*\d+")
DEFAULT_REMARK = "Se abastece con recursos de la cuenca"

N = "Normativa Ap. 7"
# Hand-written from the Normativa, Anexo VII Apéndice 7 (Asignación de recursos, "Principales tomas") unless noted.
# unit_code -> [(source_type, source_name, role, water_body_code, notes)]
UNIT_SOURCES = {
    "01A01": [  # El Condado de Huelva
        ("reservoir", "Corumbel", "main", "", "in the Tinto, Odiel y Piedras district; 3.13 hm3 transferred "
         "(Anejo 3 Ap. 1, note to Tabla 4; Normativa Ap. 7.1 'Transferencia demarcación Tinto, Odiel y Piedras')"),
        ("aquifer", "La Rocina", "minor", "ES050MSBT000055105", "Matalagrana and El Rocío boreholes, complement for "
         "Almonte and El Rocío (" + N + ".1)"),
    ],
    "02A01": "SEVILLA",  # Sevilla y entorno (EMASESA)
    "02A02": "SEVILLA",  # Mancomunidad Aljarafe
    "02A03": [  # Consorcio Huesna
        ("reservoir", "Huesna", "main", "ES050MSPF011100009", N + ".2.2 'E. de El Huesna'"),
    ],
    "03A01": [  # Córdoba
        ("reservoir", "Guadalmellato", "main", "ES050MSPF011100019", N + ".3"),
        ("reservoir", "San Rafael de Navallana", "backup", "ES050MSPF011100119", N + ".3 'Toma complementaria'"),
    ],
    "04A01": [  # Consorcio Quiebrajano-Víboras
        ("reservoir", "Quiebrajano", "main", "ES050MSPF011100042", N + ".4"),
        ("reservoir", "Víboras", "main", "ES050MSPF011100113", N + ".4"),
        ("spring", "Mingo", "main", "ES050MSBT000056600", N + ".4 'Manantiales del Mingo'; in groundwater body Grajales - Pandera - Carchel"),
        ("aquifer", "Grajales - Pandera - Carchel", "main", "ES050MSBT000056600", N + ".4 'Sondeo de la Merced' and 'Sondeos Quiebrajano' (MAS 056600)"),
        ("spring", "Fuentes de Martos", "main", "", N + ".4"),
        ("aquifer", "Gracia - Ventisquero", "main", "ES050MSBT000057000", N + ".4 'Sondeos Gracia Morenita' (MAS 057000)"),
        ("aquifer", "Jaén", "main", "ES050MSBT000051700", N + ".4 'Sondeos Ayuntamiento Jaén' (MAS 051700)"),
        ("aquifer", "Jabalcuz", "main", "ES050MSBT000051600", N + ".4 'Sondeos varios' (MAS 051600)"),
    ],
    "05A01": [("reservoir", "Francisco Abellán", "main", "ES050MSPF011100054", N + ".5")],
    "06A01": [  # Área Metropolitana Granada. Genil
        ("reservoir", "Quéntar", "main", "ES050MSPF011100118", N + ".6.1"),
        ("reservoir", "Canales", "main", "ES050MSPF011100052", N + ".6.1"),
        ("river", "río Genil", "main", "", N + ".6.1 'Río Genil hasta su confluencia con el Cubillas'"),
        ("aquifer", "Vega de Granada", "main", "ES050MSBT000053202", N + ".6.1 'Sondeos de la Vega para el abastecimiento de Granada'"),
        ("aquifer", None, "main", "", N + ".6.1 artificial recharge and other municipal boreholes"),
    ],
    "06A02": [  # Área Metropolitana Granada. Deifontes
        ("reservoir", "Cubillas", "main", "ES050MSPF011100048", N + ".6.1"),
        ("reservoir", "Colomera", "main", "ES050MSPF011100046", N + ".6.1"),
        ("spring", "Deifontes", "main", "ES050MSBT000053000", N + ".6.1 'Manantiales de Deifontes'; drains groundwater body Sierra Arana"),
        ("river", "río Cubillas", "main", "", N + ".6.1"),
        ("river", "río Colomera", "main", "", N + ".6.1"),
        ("aquifer", None, "main", "", N + ".6.1 artificial recharge"),
    ],
    "06A03": [("reservoir", "Los Bermejales", "main", "ES050MSPF011100049", N + ".6.2")],
    "07A01": [  # Abast La Loma
        ("reservoir", "Aguascebas", "main", "", N + ".7.3"),
        ("river", "río Guadalquivir", "backup", "", N + ".7.3 'Toma complementaria del río Guadalquivir'"),
        ("aquifer", None, "main", "", N + ".7.3 'Sondeos cabecera de embalse'"),
    ],
    "07A02": [  # Abast. Dañador
        ("reservoir", "Dañador", "main", "ES050MSPF011100051", N + ".7.2"),
        ("reservoir", "Guadalmena", "backup", "ES050MSPF011100053", N + ".7.2 'Toma complementaria'"),
    ],
    "07A03": [  # Abast. La Carolina - Vilches
        ("reservoir", "La Fernandina", "main", "ES050MSPF011100041", "Memoria 2.2: 'la toma de abastecimiento de La "
         "Carolina en este mismo embalse de La Fernandina'; Regulación General (" + N + ".7.1)"),
    ],
    "07A04": [  # Abast. Linares
        ("network", "Sistema de Regulación General", "main", "", N + ".7.1 assigns Linares to the Regulación General "
         "subsystem (Tranco de Beas, Giribaile, Guadalén, La Fernandina, … reservoirs) without naming its intake"),
    ],
    "07A05": [  # Consorcio del Rumblar
        ("reservoir", "Rumblar", "main", "ES050MSPF011100037", N + ".7.9"),
        ("river", "río Guadalquivir", "main", "", N + ".7.9 'Toma Río Guadalquivir'"),
    ],
    "07A06": [  # Abto. Puertollano y otros
        ("reservoir", "Montoro", "main", "ES050MSPF011100025", N + ".7.6 'E. de Montoro' (water body Embalse Montoro III)"),
        ("reservoir", "Jándula", "main", "ES050MSPF011100033", N + ".7.6 'E. de Jándula (elevación)', pumped"),
    ],
    "07A07": [("reservoir", "Fresneda", "main", "ES050MSPF011100040", N + ".7.4")],
    "07A08": [("reservoir", "Martín Gonzalo", "main", "ES050MSPF011100024", N + ".7.5")],
    "07A09": [("reservoir", "Sierra Boyera", "main", "ES050MSPF011100010", N + ".7.7")],
    "07A11": [  # Córdoba Sur
        ("network", "Sistema de Regulación General", "main", "", N + ".7.1 assigns Córdoba Sur to the Regulación "
         "General subsystem without naming the reservoir"),
        ("spring", "río de la Hoz", "main", "ES050MSBT000053600", N + ".7.1 'Manantiales del río de la Hoz' and 7.7.15; drains groundwater body Rute - Horconera"),
        ("spring", "Fuente Alhama", "main", "ES050MSBT000053500", N + ".7.1 and 7.7.15; drains groundwater body Cabra - Gaena"),
    ],
    "07A17": [("reservoir", "La Bolera", "main", "ES050MSPF011100056", N + ".7.10")],
    "07A19": [("reservoir", "Hurones", "main", "", "in the Guadalete y Barbate district, transferred (unit name "
               "'transferencia desde Guadalete Barbate Emb. Hurones'; " + N + ".7.1 note 3)")],
    "07A21": [("reservoir", "El Pintado", "backup", "ES050MSPF011100003", N + ".7.8 note 1: emergency support to the "
               "Mancomunidad de Tentudía; its ordinary supply is outside the basin")],
    "07A22": [("network", "Sistema de Regulación General", "main", "", N + ".7.1 assigns Lora del Río to the "
               "Regulación General subsystem without naming the reservoir")],
    "07A23": [("reservoir", "Iznájar", "main", "ES050MSPF011100036", N + ".7.1 'Abast. Municipios de Málaga desde E. de Iznájar'")],
    "08A01": "ECIJA",
    "08A02": [  # Mancomunidad de Llerena
        ("aquifer", "Sierra Morena", "main", "ES050MSBT000054500", N + ".8; the Mancomunidad's main intake is a dam on "
         "the arroyo Conejo in the Guadiana basin (Ap. 7.8 note 3)"),
    ],
    "08A03": "ECIJA",
}
SHARED = {
    "SEVILLA": [  # Normativa Ap. 7.2.1 (Sevilla y entorno, Mancomunidad Aljarafe)
        ("reservoir", "Aracena", "main", "ES050MSPF011100001", N + ".2.1"),
        ("reservoir", "Zufre", "main", "ES050MSPF011100002", N + ".2.1"),
        ("reservoir", "La Minilla", "main", "ES050MSPF011100004", N + ".2.1"),
        ("reservoir", "Gergal", "main", "ES050MSPF011100007", N + ".2.1"),
        ("reservoir", "Cala", "main", "ES050MSPF011100005", N + ".2.1"),
        ("reservoir", "Melonares", "main", "ES050MSPF011100006", N + ".2.1"),
        ("aquifer", None, "main", "", N + ".2.1 artificial recharge"),
        ("reservoir", "Huesna", "backup", "ES050MSPF011100009", N + ".2.1 note 1: drought plan"),
        ("reservoir", "El Pintado", "backup", "ES050MSPF011100003", N + ".2.1 note 1: drought plan"),
        ("river", "río Guadalquivir", "backup", "", N + ".2.1 note 1: drought plan"),
    ],
    "ECIJA": [  # Normativa Ap. 7.8 (Plan Écija, Sierra Sur de Sevilla y otros)
        ("reservoir", "Bembézar", "main", "ES050MSPF011100028", N + ".8"),
        ("reservoir", "Retortillo", "main", "ES050MSPF011100014", N + ".8"),
        ("reservoir", "José Torán", "main", "ES050MSPF011100013", N + ".8 'Regulación General (Embalse de José Torán)'"),
    ],
}


def download(url, out_dir, name):
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    return path


def clean(c):
    return re.sub(r"\s+", " ", c or "").strip()


def read_tabla1(pdf_path):
    rows, unit, uname = [], None, None
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if i < 3 or "Observaciones" not in text:
                continue
            stop = [w for w in page.extract_words() if w["text"] == "Tabla" and i > 3]
            stop = [w for w in stop if "Tabla 2." in text]
            region = page
            if stop:          # the page where Tabla 2 (2027) starts: keep only what is above its caption
                region = page.crop((0, 0, page.width, stop[0]["top"]))
            for table in region.extract_tables():
                for raw in table:
                    c = [clean(x) for x in raw]
                    nz = [x for x in c if x]
                    codes = [x for x in nz if re.fullmatch(r"\d{4,5}", x)]
                    if not codes:
                        continue
                    u = [x for x in nz if UNIT.fullmatch(x)]
                    if u:
                        unit = u[0]
                        uname = c[0] if c[0] and c[0] != u[0] else uname
                    elif c[0] and c[0] not in nz[1:]:
                        uname = c[0]
                    k = nz.index(codes[0])
                    start = nz.index(unit) + 1 if unit in nz else (1 if c[0] else 0)
                    remark = " ".join(nz[k + 1:])
                    rows.append(dict(code=codes[0].zfill(5), name=" ".join(nz[start:k]), unit_code=unit,
                                     unit_name=uname, remark=remark, page=i + 1))
            if stop:
                break
    return rows


def read_mas_names(pdf_path):
    names = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Apéndice 4.1. Masas de agua subterránea" not in text and not names:
                continue
            found = False
            for line in text.splitlines():
                m = re.match(r"\s*(ES050MSBT0000\d{5})\s+(.+?)\s+[\d.]+,\d+\s*$", line)
                if m:
                    names.setdefault(m.group(1), m.group(2).strip())
                    found = True
            if names and not found:
                break
    return names


def fold(s):
    """Accent-, case- and article-insensitive key: 'Palmar de Troya, El' == 'El Palmar de Troya' == 'Palmar de Troya (el)'."""
    s = re.sub(r"\s*(?:,\s*|\()(el|la|los|las)\)?\s*$", "", s.strip(), flags=re.I)
    s = re.sub(r"^(el|la|los|las)\s+", "", s, flags=re.I)
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z]", "", "".join(ch for ch in s if not unicodedata.combining(ch)))


def unit_sources(code, name, mas):
    """-> list of (source_type, source_name, role, water_body_code, notes)"""
    if code in UNIT_SOURCES:
        v = UNIT_SOURCES[code]
        return SHARED[v] if isinstance(v, str) else v
    m = re.fullmatch(r"\d\dAS(\d{4})", code)
    if m and m.group(1) == "0000":
        return [("aquifer", None, "main", "", "groundwater outside the listed groundwater bodies (unit '" + name + "')")]
    if m:
        wb = "ES050MSBT00005" + m.group(1)
        official = mas.get(wb)
        if official is None:
            return [("aquifer", None, "main", wb, "groundwater body code from the unit code; not in Normativa Ap. 4.1")]
        label = re.sub(r"^Abast(ecimiento)?\.?\s*(MAS\s*\d+\s*)?", "", name).strip()
        note = None
        if label and fold(label)[:6] not in fold(official) and fold(official)[:6] not in fold(label):
            note = f"unit name says '{label}'; body {wb} is '{official}' in Normativa Ap. 4.1"
        return [("aquifer", official, "main", wb, note)]
    if code.endswith("AF100"):
        return [("river", None, "main", "", "small surface intakes: unregulated rivers and small reservoirs (Normativa Ap. 7)")]
    return []


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/guadalquivir"
    os.makedirs(out_dir, exist_ok=True)
    rows = read_tabla1(download(URL_AP1, out_dir, "PHGuadalquivir_ANEJO3_Apendice1.pdf"))
    mas = read_mas_names(download(URL_NORM, out_dir, "PHGuadalquivir_Normativa.pdf"))
    ref = {}
    with open(REFERENCE, newline="") as f:
        for r in csv.DictReader(f):
            ref[r["municipality_code"]] = r["official_name"]

    units, muni, unmatched, seen = {}, [], [], set()
    for r in rows:
        units.setdefault(r["unit_code"], r["unit_name"])
        if r["code"] not in ref:
            # a few codes in Tabla 1 are not INE codes (11540 Sanlúcar de Barrameda, 41719 El Palmar de Troya):
            # match the name within the province, and only when exactly one municipality has it
            hits = [c for c, n in ref.items() if c[:2] == r["code"][:2] and fold(n) == fold(r["name"])]
            if len(hits) != 1:
                unmatched.append((r["name"], r["code"][:2], f"INE code {r['code']} (page {r['page']}) not in the INE "
                                  "reference and the name has no unique match in the province"))
                continue
            print(f"plan code {r['code']} '{r['name']}' -> INE {hits[0]} '{ref[hits[0]]}' (name match)", file=sys.stderr)
            r["code"] = hits[0]
        if fold(r["name"])[:4] not in fold(ref[r["code"]]):
            print(f"check name: {r['code']} plan '{r['name']}' vs INE '{ref[r['code']]}'", file=sys.stderr)
        if (r["code"], r["unit_code"]) in seen:
            continue
        seen.add((r["code"], r["unit_code"]))
        remark = "" if r["remark"] == DEFAULT_REMARK else r["remark"]
        muni.append([r["code"], r["unit_code"], "", remark, ""])

    sources, missing = [], []
    for code, name in sorted(units.items()):
        found = unit_sources(code, name, mas)
        if not found:
            missing.append(code)
        for rank, (kind, sname, role, wb, notes) in enumerate(found, 1):
            sources.append([code, "", rank, kind, sname or "", role, wb, "", notes or ""])

    meta = {
        "plan": "guadalquivir", "basin_id": "ES050", "source": "ph-guadalquivir-2022-2027", "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Guadalquivir 2022–2027 (RD 35/2023): "
                           "Anejo 3 Apéndice 1 Uso Urbano, Tabla 1 (municipality -> UDU, 2021); sources from the "
                           "Normativa, Apéndice 7 Asignación de recursos, and Apéndice 4.1 (groundwater bodies)",
        "source_url": URL_AP1,
        "notes": "Tabla 1 (2021 situation) places each municipality in a unit but names no intakes. Sources are per "
                 "unit: 'AS####' units are the groundwater body ES050MSBT00005#### (official name from Normativa "
                 "Ap. 4.1); 'AF100' units are small surface intakes; named units take the 'Principales tomas' of "
                 "Normativa Ap. 7 (cited in each note; drought-plan sources as backup). Units served by the "
                 "Regulación General subsystem without a named intake (Linares, Córdoba Sur, Lora del Río) get a "
                 "network row. intake_description holds the Tabla 1 remark when it is not the default 'Se abastece "
                 "con recursos de la cuenca' (e.g. 'En la cuenca pero no se abastece de ella'). Normativa: " + URL_NORM,
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
    print(f"{len(muni)} municipality rows ({len({m[0] for m in muni})} municipalities), {len(units)} supply units, "
          f"{len(sources)} sources, {len(unmatched)} unmatched, units without sources: {missing} -> {out_dir}")


if __name__ == "__main__":
    main()
