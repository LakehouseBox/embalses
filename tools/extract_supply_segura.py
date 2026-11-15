"""Segura river-basin plan 2022-2027: which supply unit (UDU) serves each municipality, and where it takes its water.

Sources (Confederación Hidrográfica del Segura, Plan Hidrológico 2022-2027):
  Anejo 3 "Usos y demandas"
    https://www.chsegura.es/export/sites/chs/descargas/planificacionydma/planificacion21-27/docsdescarga/docplan2227BOE/A03_usos_y_demandas/ANEJO_03_Usos_demandas.pdf
    Tabla 62 (p. 120): the 13 UDUs and the municipalities in each (names only).
    Tabla 61 (p. 118): matrix of the resources each Mancomunidad de los Canales del Taibilla (MCT) unit can use; the
      ticks are coloured cell fills, read here from the PDF drawing (fill colour per cell; '***' = serves only part).
    Section 4.1.1 text: municipality exceptions (own intakes from the río Segura, own groundwater, Férez, Hellín).
  Anexo I del Anejo 3 "Fichas de caracterización de las unidades de demanda urbana"
    https://www.chsegura.es/export/sites/chs/descargas/planificacionydma/planificacion21-27/docsdescarga/docplan2227BOE/A03_usos_y_demandas/Anexos/Anexo_I_Unidades_de_demanda_urbana.pdf
    One ficha per UDU: "Origen del agua/masa de la que procede", ETAP, desalination plants.

The municipality lists and the per-unit sources of the non-MCT units are short, so they are written out below as the
plan prints them; the script checks that every name and phrase is present in the downloaded PDFs (it stops if one is
not), and matches the names to INE codes in data/raw/ine/municipalities_reference.csv within the plan's provinces.

Writes, into OUT_DIR (default data/raw/plans/segura): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv. Downloads are kept in OUT_DIR/source/.

Usage: uv run --with pdfplumber python tools/extract_supply_segura.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

BASE = ("https://www.chsegura.es/export/sites/chs/descargas/planificacionydma/planificacion21-27/docsdescarga/"
        "docplan2227BOE/A03_usos_y_demandas/")
ANEJO_URL = BASE + "ANEJO_03_Usos_demandas.pdf"
FICHAS_URL = BASE + "Anexos/Anexo_I_Unidades_de_demanda_urbana.pdf"
REFERENCE = "data/raw/ine/municipalities_reference.csv"
PROVINCES = {"MURCIA": "30", "ALICANTE": "03", "ALBACETE": "02", "ALMERÍA": "04", "JAÉN": "23", "GRANADA": "18"}

# Tabla 62, as printed. Each unit: code, name, [(province, [municipality, ...])]. "de forma parcial" municipalities
# are flagged with a trailing '*'. Province for units 7-13 comes from the fichas ("todos ellos en la provincia de ...").
TABLE_62 = [
    ("UDU01", "MCT-Taibilla", [("MURCIA", ["Albudeite", "Bullas", "Calasparra", "Campos del Río", "Caravaca de la Cruz",
                                           "Cehegín", "Moratalla", "Mula", "Pliego", "Lorca*"]),
                               ("ALBACETE", ["Socovos"])]),
    ("UDU02", "MCT-Sierra de la Espada", [("MURCIA", ["Abarán", "Archena", "Blanca", "Ceutí", "Cieza", "Ojós", "Ricote",
                                                      "Ulea", "Villanueva del Río Segura"])]),
    ("UDU03", "MCT-Central", [("MURCIA", ["Abanilla", "Alcantarilla", "Alguazas", "Beniel", "Fortuna", "Las Torres de Cotillas",
                                          "Lorquí", "Molina de Segura", "Murcia", "Santomera", "Los Alcázares*", "Cartagena*",
                                          "San Javier*", "San Pedro del Pinatar*", "Torre Pacheco*", "La Unión*"]),
                              ("ALICANTE", ["Albatera", "Algorfa", "Almoradí", "Benejúzar", "Benferri", "Benijófar", "Bigastro",
                                            "Callosa de Segura", "Catral", "Crevillente", "Cox", "Daya Nueva", "Daya Vieja",
                                            "Dolores", "Formentera del Segura", "Granja de Rocamora", "Guardamar del Segura",
                                            "Jacarilla", "Los Montesinos", "Orihuela", "Pilar de la Horadada", "Rafal",
                                            "Redován", "Rojales", "San Fulgencio", "San Isidro", "San Miguel de Salinas",
                                            "Torrevieja"])]),
    ("UDU04", "MCT-Alicante I y II", [("ALICANTE", ["Alicante/Alacant", "Aspe", "El Fondó de les Neus", "Elche/Elx",
                                                    "Hondón de los Frailes", "Santa Pola",
                                                    "San Vicente del Raspeig/San Vicent del Raspeig"])]),
    ("UDU05", "MCT-Lorca-Águilas", [("MURCIA", ["Águilas", "Aledo", "Alhama de Murcia", "Librilla", "Lorca",
                                                "Puerto Lumbreras", "Totana"])]),
    ("UDU06", "MCT-Valdelentisco", [("MURCIA", ["Mazarrón", "Fuente Álamo de Murcia", "Los Alcázares*", "Cartagena*",
                                                "San Javier*", "San Pedro del Pinatar*", "Torre Pacheco*", "La Unión*"])]),
    ("UDU07", "Altiplano", [("MURCIA", ["Jumilla", "Yecla"])]),
    ("UDU08", "Hellín", [("ALBACETE", ["Hellín"])]),
    ("UDU09", "Cabecera del Segura", [("ALBACETE", ["Yeste", "Santiago de la Espada-Pontones", "Férez", "Nerpio",
                                                    "Elche de la Sierra", "Letur"])]),
    ("UDU10", "Cabecera del Mundo", [("ALBACETE", ["Ayna", "Bogarra", "Liétor", "Molinicos", "Montealegre del Castillo",
                                                   "Paterna de Madera", "Riópar", "Albatana", "Alcadozo", "Bonete",
                                                   "Corral-Rubio", "Fuente Álamo (Albacete)", "Ontur", "Pétrola", "Tobarra"])]),
    ("UDU11", "Cabecera del Guadalentín", [("ALMERÍA", ["Chirivel", "María", "Vélez-Blanco", "Vélez-Rubio"])]),
    ("UDU12", "Serral-Salinas", [("ALICANTE", ["La Algueña", "Pinoso"])]),
    ("UDU13", "GALASA", [("ALMERÍA", ["Pulpí"])]),
]
# The plan's spelling -> INE name, where the two differ by more than accents, articles, hyphens or bilingual order.
ALIASES = {"Crevillente": "Crevillent", "Santiago de la Espada-Pontones": "Santiago-Pontones",
           "Paterna de Madera": "Paterna del Madera", "Fuente Álamo (Albacete)": "Fuente-Álamo"}

# Tabla 61 columns, left to right: (header words to check, source_type, source_name)
T61_COLUMNS = [("Rio Taibilla", "river", "río Taibilla"),
               ("Trasvase Tajo-", "transfer", "Trasvase Tajo-Segura"),
               ("Alicante I y II", "desalination", "IDAM Alicante I y II"),
               ("San Pedro I y II", "desalination", "IDAM San Pedro I y II"),
               ("Águilas", "desalination", "IDAM Águilas"),
               ("Torrevieja", "desalination", "IDAM Torrevieja"),
               ("Valdelentisco", "desalination", "IDAM Valdelentisco"),
               ("Recursos", None, None),          # 'otros recursos': municipality-level, from the text below
               ("Tomas Rio Segura", None, None)]

# Sources the plan gives for single municipalities (MCT units) and for the units outside the MCT.
# (unit, municipality or None, source_type, source_name, role, notes, phrase that must be in the plan, intake text)
EXTRA_SOURCES = [
    ("UDU01", "Caravaca de la Cruz", "aquifer", "", "main", "own resources, not managed by the MCT",
     "Caravaca de la Cruz y Moratalla disponen, además, de recursos propios no gestionados por la MCT",
     "Caravaca de la Cruz y Moratalla disponen de recursos propios subterráneos"),
    ("UDU01", "Moratalla", "aquifer", "", "main", "own resources, not managed by the MCT",
     "Caravaca de la Cruz y Moratalla disponen, además, de recursos propios no gestionados por la MCT",
     "Caravaca de la Cruz y Moratalla disponen de recursos propios subterráneos"),
    ("UDU02", "Abarán", "river", "río Segura", "main", "own intake",
     "Abarán dispone de toma superficial desde el Río Segura", "Abarán dispone de toma superficial desde el Río Segura."),
    ("UDU03", "Alcantarilla", "river", "río Segura", "main", "own intake",
     "Alcantarilla y Murcia tienen toma directa del rio Segura", "Alcantarilla y Murcia tienen toma directa del rio Segura."),
    ("UDU03", "Murcia", "river", "río Segura", "main", "own intake",
     "Alcantarilla y Murcia tienen toma directa del rio Segura", "Alcantarilla y Murcia tienen toma directa del rio Segura."),
    ("UDU04", "San Vicente del Raspeig/San Vicent del Raspeig", "desalination", "IDAM Mutxamel/El Campello", "backup",
     "may receive water from this plant", "podrá recibir recursos desde la desalinizadora de Mutxamel/El Campello",
     "podrá recibir recursos desde la desalinizadora de Mutxamel/El Campello"),
    ("UDU07", None, "aquifer", "Cingla", "main", "", "Captaciones en el acuífero Cingla", ""),
    ("UDU08", None, "river", "río Mundo", "main", "through the Canal de Hellín, upstream of the Talave reservoir",
     "Río Mundo mediante Canal de Hellín", ""),
    ("UDU08", None, "reservoir", "Talave", "backup", "complementary direct intake from the reservoir",
     "complementariamente, dispone de toma directa del embalse", ""),
    ("UDU09", None, "spring", "", "main", "springs and groundwater outflows", "Manantiales", ""),
    ("UDU09", "Férez", "network", "Mancomunidad de los Canales del Taibilla", "minor", "small contribution",
     "El municipio de Férez cuenta con una pequeña aportación de recursos desde la MCT",
     "El municipio de Férez cuenta con una pequeña aportación de recursos desde la MCT."),
    ("UDU10", None, "spring", "", "main", "", "Manantiales", ""),
    ("UDU10", None, "aquifer", "", "main", "groundwater intakes", "proceden básicamente de manantiales y tomas subterráneas", ""),
    ("UDU11", None, "aquifer", "Alto Guadalentín", "main", "", "Captaciones en el acuífero del Alto Guadalentín", ""),
    ("UDU11", None, "spring", "", "main", "", "proceden básicamente de manantiales y tomas subterráneas", ""),
    ("UDU12", None, "aquifer", "Serral-Salinas", "main", "", "Captaciones en el acuífero Serral-Salinas", ""),
    ("UDU13", None, "transfer", "Trasvase Tajo-Segura", "main", "", "Tajo-Segura.", ""),
    ("UDU13", None, "desalination", "IDAM Águilas", "main", "", "Águilas-Acuamed", ""),
]


def download(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    return path


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def tokens(s):
    return [t for t in (re.sub(r"^[^\w]+|[^\w]+$", "", w) for w in s.split()) if t]


def contains(text_tokens, phrase, gap=6):
    """True when the phrase's words appear in order in the text, with at most `gap` other words between two of them
    (the PDFs interleave neighbouring columns into a sentence)."""
    want = tokens(phrase)
    for start, t in enumerate(text_tokens):
        if t != want[0]:
            continue
        i, ok = start, True
        for w in want[1:]:
            nxt = next((j for j in range(i + 1, min(i + 2 + gap, len(text_tokens))) if text_tokens[j] == w), None)
            if nxt is None:
                ok = False
                break
            i = nxt
        if ok:
            return True
    return False


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s*\(.*?\)", "", s).replace("-", " ").replace("'", " ")
    return flat(s)


def variants(name):
    """All spellings of a name: each '/' part, article moved to the front, and without the article."""
    out = set()
    for part in name.split("/"):
        part = part.strip()
        m = re.match(r"(.+),\s*(el|la|los|las|l'|els|les|o|a|os|as)$", part, re.I)
        if m:
            part = f"{m.group(2)} {m.group(1)}"
        n = norm(part)
        out.add(n)
        out.add(re.sub(r"^(el|la|los|las|l|els|les) ", "", n))
    return out


def read_texts(anejo, fichas):
    with pdfplumber.open(anejo) as pdf:
        t62 = t61 = None
        pages = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
            if "Tabla 62. Unidades de demanda Urbana definidas" in text and "GALASA" in text:
                t62 = page.crop((150, 0, page.width, page.height)).extract_text()
            if "Tabla 61. UDU definidas" in text and len(page.curves) > 20:
                t61 = read_table_61(page)
        anejo_text = flat(" ".join(pages))
    with pdfplumber.open(fichas) as pdf:
        fichas_text = flat(" ".join(p.extract_text() or "" for p in pdf.pages))
    if not t62 or not t61:
        sys.exit("Tabla 61 or 62 not found in Anejo 3")
    return flat(t62), t61, anejo_text, fichas_text


def read_table_61(page):
    """Tabla 61: {UDU number: {column index: partial?}} from the coloured cell fills of the drawing."""
    curves = page.curves + page.rects
    # column edges: the black vertical rules of the resource columns
    xs = sorted({round(c["x0"]) for c in curves if c.get("non_stroking_color") in (0, 0.0, [0], (0,))
                 and c["x1"] - c["x0"] < 3 and c["bottom"] - c["top"] > 50})
    edges = [x for i, x in enumerate(xs) if i == 0 or x - xs[i - 1] > 5]
    edges = edges[-(len(T61_COLUMNS) + 1):]          # the leftmost rules frame the UDU number and name columns
    if len(edges) != len(T61_COLUMNS) + 1 or edges[-1] - edges[0] < 250:
        sys.exit(f"Tabla 61: expected {len(T61_COLUMNS) + 1} column rules, found {edges}")
    # the table's text is drawn char by char, so work on chars: a row label is 'U','D','U',digit left of the first column
    chars = page.chars
    rows = {}
    for d in chars:
        if re.fullmatch(r"\d", d["text"]) and d["x1"] <= edges[0]:
            label = "".join(c["text"].strip() for c in sorted(chars, key=lambda c: c["x0"])
                            if abs(c["top"] - d["top"]) < 2 and d["x0"] - 25 < c["x0"] < d["x0"])
            if label.endswith("UDU"):
                rows[int(d["text"])] = (d["top"] + d["bottom"]) / 2
    if sorted(rows) != [1, 2, 3, 4, 5, 6]:
        sys.exit(f"Tabla 61: rows found {sorted(rows)}")
    stars = [c for c in chars if c["text"] == "*" and c["x0"] > edges[0]]
    out = {u: {} for u in rows}
    for c in curves:
        col = c.get("non_stroking_color")
        if not c.get("fill") or col in (0, 1, 0.0, 1.0, None) or c["x1"] - c["x0"] < 10 or c["bottom"] - c["top"] < 8:
            continue
        if isinstance(col, (list, tuple)) and len(col) == 3 and abs(col[0] - 0.816) < 0.01:
            continue                                   # page border tint
        mid = (c["top"] + c["bottom"]) / 2
        udu = next((u for u, y in rows.items() if abs(y - mid) < 5), None)
        if udu is None:
            continue
        for k in range(len(T61_COLUMNS)):
            centre = (edges[k] + edges[k + 1]) / 2
            if c["x0"] < centre < c["x1"]:
                partial = any(edges[k] < (s["x0"] + s["x1"]) / 2 < edges[k + 1] and abs((s["top"] + s["bottom"]) / 2 - mid) < 5
                              for s in stars)
                out[udu][k] = partial
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/segura"
    src = os.path.join(out_dir, "source")
    os.makedirs(src, exist_ok=True)
    anejo = download(ANEJO_URL, os.path.join(src, "ANEJO_03_Usos_demandas.pdf"))
    fichas = download(FICHAS_URL, os.path.join(src, "Anexo_I_Unidades_de_demanda_urbana.pdf"))
    t62, t61, anejo_text, fichas_text = read_texts(anejo, fichas)

    # check the transcriptions against the PDFs
    t62, anejo_text, fichas_text = tokens(t62), tokens(anejo_text), tokens(fichas_text)
    missing = []
    for _, uname, groups in TABLE_62:
        for prov, names in groups:
            for n in names:
                n = n.rstrip("*")
                if n == "Lorca" and uname == "MCT-Taibilla":
                    n = "las Pedanías Altas de Lorca"
                if not contains(t62, n):
                    missing.append(n)
    for *_, phrase, intake in EXTRA_SOURCES:
        if not contains(anejo_text, phrase) and not contains(fichas_text, phrase):
            missing.append(phrase)
        if intake and not contains(fichas_text, intake) and not contains(anejo_text, intake):
            missing.append(intake)
    if missing:
        sys.exit(f"not found in the plan: {missing}")

    ref = list(csv.DictReader(open(REFERENCE, encoding="utf-8")))
    index = {}
    for r in ref:
        if r["province_code"] in PROVINCES.values():
            for v in variants(r["official_name"]):
                index.setdefault((r["province_code"], v), set()).add(r["municipality_code"])

    def match(name, prov):
        target = variants(ALIASES.get(name, name))
        hits = set().union(*(index.get((PROVINCES[prov], v), set()) for v in target))
        if not hits:                                    # e.g. Santiago-Pontones (Jaén) in a ficha that says Albacete
            hits = set().union(*(index.get((p, v), set()) for p in PROVINCES.values() for v in target))
        return hits

    units, ms_rows, unmatched, code_of = [], [], [], {}
    intake = {(e[0], e[1]): e[7] for e in EXTRA_SOURCES if e[1]}    # the ficha's wording for that municipality
    for code, uname, groups in TABLE_62:
        units.append((code, uname))
        for prov, names in groups:
            for raw in names:
                name = raw.rstrip("*")
                hits = match(name, prov)
                if len(hits) != 1:
                    unmatched.append((name, PROVINCES[prov], "no INE match" if not hits else f"ambiguous: {sorted(hits)}"))
                    continue
                mc = hits.pop()
                code_of[name] = mc
                ms_rows.append((mc, code, "", intake.get((code, name), ""), ""))
    unmatched.append(("otros municipios de la provincia de Almería no pertenecientes a la DHS", "04",
                      "UDU13 GALASA: the plan does not name them"))

    ss_rows = []
    rank = {}

    def add(unit, muni, kind, name, role, notes):
        key = (unit, muni or "")
        rank[key] = rank.get(key, 0) + 1
        ss_rows.append((unit, muni or "", rank[key], kind, name, role, "", "", notes))

    for code, _, _ in TABLE_62[:6]:                     # MCT units: network, then Tabla 61 resources in column order
        cols = t61[int(code[3:])]
        add(code, None, "network", "Mancomunidad de los Canales del Taibilla", "main", "")
        for k, partial in sorted(cols.items()):
            _, kind, name = T61_COLUMNS[k]
            if kind:
                add(code, None, kind, name, "minor" if partial else "main",
                    "serves only part of the unit" if partial else "")
    for unit, muni, kind, name, role, notes, _, _ in EXTRA_SOURCES:
        add(unit, code_of.get(muni) if muni else None, kind, name, role, notes)

    def write_csv(name, header, rows):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write_csv("supply_units.csv", ["unit_code", "unit_name"], units)
    write_csv("municipality_supply.csv", ["municipality_code", "unit_code", "share_pct", "intake_description",
                                          "additional_intakes"], ms_rows)
    write_csv("supply_sources.csv", ["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                                     "water_body_code", "share_pct", "notes"], ss_rows)
    write_csv("unmatched.csv", ["plan_name", "province_hint", "reason"], unmatched)

    t61_text = "; ".join(f"UDU{u}: " + ", ".join(T61_COLUMNS[k][0] + ("***" if p else "") for k, p in sorted(c.items()))
                         for u, c in sorted(t61.items()))
    meta = {
        "plan": "segura", "basin_id": "ES070", "source": "ph-segura-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("Plan Hidrológico de la D.H. del Segura 2022–2027, Anejo 3 Usos y demandas (Tablas 61 and 62, "
                            "section 4.1.1) and its Anexo I, Fichas de caracterización de las unidades de demanda urbana"),
        "source_url": ANEJO_URL,
        "notes": ("The plan has no unit codes: UDU01-UDU13 follow its numbering (UDU 1 ... UDU 13). Municipalities from "
                  "Tabla 62, matched to INE by name. Lorca is in UDU01 (only its 'Pedanías Altas') and UDU05; Los Alcázares, "
                  "Cartagena, San Javier, San Pedro del Pinatar, Torre-Pacheco and La Unión are split between UDU03 and UDU06; "
                  "the plan gives no split, so share_pct is empty for these. UDU13 GALASA also serves Almería municipalities "
                  "outside the Segura district that the plan does not name (only Pulpí is listed). UDUs 9-12 list their "
                  "'principales municipios' in the text but the same names in Tabla 62 and the fichas, which are used. "
                  "MCT units (UDU01-06): the MCT network plus the resources ticked in Tabla 61 (" + t61_text + "; '***' = "
                  "serves only part of the unit, role minor). Municipality-level rows are the plan's own exceptions "
                  "(own intakes from the río Segura, own groundwater, Férez, San Vicente del Raspeig). The ficha of UDU04 "
                  "omits the río Taibilla that Tabla 61 and the text give; Tabla 61 is used. No water body codes or % "
                  "splits are given per unit."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len({r[0] for r in ms_rows})} municipalities, {len(units)} units, {len(ss_rows)} source rows, "
          f"{len(unmatched)} unmatched -> {out_dir}")
    print("Tabla 61:", t61_text)


if __name__ == "__main__":
    main()
