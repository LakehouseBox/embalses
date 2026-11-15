"""Júcar river-basin plan 2022-2027: which urban supply unit (UDU) serves each municipality, and where it takes its water.

Sources (Confederación Hidrográfica del Júcar, official open data and the approved plan):
  F2849 "PHJ 2022/2027 Unidades de demanda urbana UDU" (open data, xlsx inside the zip):
    https://aps.chj.es/down/CSV/F2849_PHJ_2022_2027_Unidades_de_demanda_urbana_UDU.zip
    F2849_M0_*.xlsx  UDU code, name, type;  F2849_D0_Municipios.xlsx  UDU code -> INE municipality code
  F2626 "Masas de agua subterránea PHJ 2022/2027" (code -> groundwater body name):
    https://aps.chj.es/down/CSV/F2626_PHJ_2022_2027_Masas_de_agua_subterranea.zip
  F2333 "Masas de agua superficial PHJ 2022/2027" (code -> surface water body name and category):
    https://aps.chj.es/down/CSV/F2333_PHJ_2022_2027_Masas_de_agua_superficial.zip
  Plan Hidrológico del Júcar 2022-2027, Memoria Anejo 3 "Usos y demandas", Apéndice 1.1 "Caracterización de las
  unidades de demanda urbana" (one ficha per UDU; section 3 "Origen del agua actual (hm³)" gives the volume by origin
  -surface, groundwater, desalination, transfer, reuse- and the main supply points with their share: "M. Sup.* 03-02
  67%", "M. Subt.* 080-107 55%", "Desal. Orpesa 100%"):
    https://www.chj.es/es-es/medioambiente/planificacionhidrologica/Documents/Plan-Hidrologico-cuenca-2021-2027/PHC/Version%20Final/PHJ2227_Anejo03_UsosyDemandas_2023_01_24.pdf

The ficha percentages are shares within each origin (the surface column adds up to 100% of the surface volume);
share_pct in supply_sources.csv is the share of the unit's whole supply: pct x origin volume / total volume.

Writes, into OUT_DIR (default data/raw/plans/jucar): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv (format: tools/supply_plans_format.md). The 138 MB PDF is downloaded once and kept there.

Usage: uv run --with pdfplumber python tools/extract_supply_jucar.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import pdfplumber

UDU_ZIP = "https://aps.chj.es/down/CSV/F2849_PHJ_2022_2027_Unidades_de_demanda_urbana_UDU.zip"
GW_ZIP = "https://aps.chj.es/down/CSV/F2626_PHJ_2022_2027_Masas_de_agua_subterranea.zip"
SW_ZIP = "https://aps.chj.es/down/CSV/F2333_PHJ_2022_2027_Masas_de_agua_superficial.zip"
ANEJO3 = ("https://www.chj.es/es-es/medioambiente/planificacionhidrologica/Documents/Plan-Hidrologico-cuenca-2021-2027/"
          "PHC/Version%20Final/PHJ2227_Anejo03_UsosyDemandas_2023_01_24.pdf")


def download(url, out_dir):
    path = os.path.join(out_dir, url.rsplit("/", 1)[1])
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx(zip_path, member_suffix):
    """Rows (list of dicts) of the first sheet of the xlsx inside zip_path whose name ends with member_suffix.
    Standard library only: the xlsx is itself a zip of XML parts."""
    import io
    with zipfile.ZipFile(zip_path) as outer:
        name = next(n for n in outer.namelist() if n.endswith(member_suffix))
        data = io.BytesIO(outer.read(name))
    with zipfile.ZipFile(data) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.iter("{%s}row" % NS["m"]):
            vals = {}
            for c in row.findall("m:c", NS):
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                v = c.find("m:v", NS)
                if c.get("t") == "s":
                    val = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
                else:
                    val = v.text if v is not None else ""
                vals[col] = (val or "").strip()
            rows.append(vals)
    header = rows[0]
    return [{header[k]: r.get(k, "") for k in header} for r in rows[1:] if any(r.values())]


# ---------------------------------------------------------------------------------------------- fichas (Apéndice 1.1)
ORIGINS = ["Superficial", "Subterráneo", "Desalación", "Transferencia", "Reutilización"]
COLUMN_KIND = {"Sup.*": "surface", "Sup": "surface", "Subt.*": "ground", "Desal.": "desal", "Transf.": "transfer",
               "EDAR": "reuse"}
KIND_ORIGIN = {"surface": "Superficial", "ground": "Subterráneo", "desal": "Desalación", "transfer": "Transferencia",
               "reuse": "Reutilización"}


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def lines_of(words, tol=3):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def parse_origin(words):
    """Words of the page holding section 3 'Origen del agua actual' -> (volumes by origin, [(kind, label, pct)])."""
    lines = lines_of(words)
    i = next(k for k, l in enumerate(lines) if " ".join(w["text"] for w in l).startswith("Origen del agua actual"))
    head = lines[i + 1]
    vals = lines[i + 2]
    vols = {}
    for v in vals:
        h = min((w for w in head if w["text"] in ORIGINS), key=lambda w: abs((w["x0"] + w["x1"]) / 2 - (v["x0"] + v["x1"]) / 2))
        vols[h["text"]] = num(v["text"])
    # column headers: 'M. Sup.*  %  M. Subt.*  %  Desal.  %' (the '*' may be detached: 'M. Sup *')
    hl = lines[i + 3]
    cols = []
    for k, w in enumerate(hl):
        t = w["text"]
        if t in COLUMN_KIND and not (t == "Sup" and k + 1 < len(hl) and hl[k + 1]["text"] == "Sup.*"):
            cols.append([COLUMN_KIND[t], (hl[k - 1]["x0"] if t.startswith(("Sup", "Subt")) and k else w["x0"]), None])
        elif t == "%" and cols:
            cols[-1][2] = w["x1"]
    entries = []
    cells = {k: [] for k in range(len(cols))}
    for line in lines[i + 4:]:
        if line[0]["text"].startswith("*"):
            break
        for w in line:
            k = max((k for k, c in enumerate(cols) if w["x0"] >= c[1] - 25), default=0)
            cells[k].append(w)
    for k, (kind, _x, _px) in enumerate(cols):
        label, pending = [], []
        for line in lines_of(cells[k], tol=4):
            for w in line:
                if re.fullmatch(r"\d+(,\d+)?%", w["text"]):
                    pending.append((" ".join(label), num(w["text"][:-1])))
                    label = []
                else:
                    label.append(w["text"])
            if label and pending:          # a wrapped name ('Canales de Taibilla', '(Total)') continues the last entry
                n, p = pending[-1]
                pending[-1] = (n + " " + " ".join(label), p)
                label = []
        for name, pct in pending:
            name = re.sub(r"\s+", " ", name).strip()
            if kind in ("surface", "ground") and not name.startswith("No asig"):
                name = name.replace(" ", "")      # long codes wrap: '18-21-01-04-01-01-01- 01'
            entries.append((kind, name, pct))
    return vols, entries


def read_fichas(pdf_path):
    """Apéndice 1.1: from the first page headed 'CARACTERIZACIÓN DE LAS UNIDADES DE DEMANDA URBANA' up to
    Apéndice 1.2. Each ficha starts on a headed page and runs over the following unheaded pages."""
    fichas, cur = {}, None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            top = page.crop((0, 0, page.width, 80)).extract_text() or ""
            if "UNIDADES DE DEMANDA URBANA" in top:
                words = page.extract_words()
                text = " ".join(w["text"] for w in words)
                code = re.search(r"Código\s+(U\d{4})", text).group(1)
                m = re.search(r"Municipios\s+(.*?)\s+2\. CARACTER", text)
                cur = fichas.setdefault(code, {"municipios": m.group(1).replace(" integrados", "") if m else ""})
            elif cur is not None:
                if "Apéndice 1.2" in top:
                    break
                words = page.extract_words()
            else:
                page.flush_cache()
                continue
            if "origin" not in cur and any(w["text"] == "Origen" for w in words):
                cur["origin"] = parse_origin(words)
            page.flush_cache()
    return fichas


# ---------------------------------------------------------------------------------------------- water bodies
def surface_source(code, sw):
    """Surface water body code -> (source_type, source_name, notes)."""
    b = sw.get(code)
    if not b:
        return "river", None, f"surface water body {code} not in the CHJ list"
    name, cat = b["Masa Superficial"], b["Categoría"]
    m = re.match(r"Embalse (?:de |del )?(.+)", name)
    if m:
        return "reservoir", m.group(1).strip(), None
    if cat == "Río":
        main, _, stretch = name.partition(":")
        main = main.strip()
        main = main[0].lower() + main[1:]
        return "river", main, (f"stretch: {stretch.strip()}" if stretch.strip() else None)
    return "river", name, f"surface water body category {cat}"


def build_sources(fichas, gw, sw):
    rows = []
    for code, f in sorted(fichas.items()):
        vols, entries = f.get("origin", ({}, []))
        total = sum(vols.values())
        rank = 0
        for kind, label, pct in entries:
            if pct == 0:
                continue
            rank += 1
            origin_vol = vols.get(KIND_ORIGIN[kind], 0.0)
            share = round(pct * origin_vol / total, 1) if total else None
            origin_note = f"{pct:g}% of the unit's {KIND_ORIGIN[kind].lower()} volume"
            wb, notes = "", None
            if label.startswith("No asig"):
                stype = "river" if kind == "surface" else "aquifer"
                name, notes = None, ("surface intake outside any water body" if kind == "surface"
                                     else "groundwater outside any groundwater body")
            elif kind == "surface":
                wb = label
                stype, name, notes = surface_source(label, sw)
            elif kind == "ground":
                wb = label
                stype, name = "aquifer", gw.get(label)
                if not name:
                    notes = f"groundwater body {label} not in the CHJ list"
            elif kind == "desal":
                stype, name, notes = "desalination", label, "desalination plant"
            elif kind == "transfer":
                if "Taibilla" in label:
                    stype, name = "network", "Mancomunidad de los Canales del Taibilla"
                else:
                    stype, name = "transfer", label
            else:
                stype, name, notes = "reclaimed", label, "reclaimed water from this wastewater plant (EDAR)"
            notes = "; ".join(n for n in (notes, origin_note) if n)
            rows.append(dict(unit_code=code, municipality_code="", source_rank=rank, source_type=stype,
                             source_name=name or "", role="main", water_body_code=wb,
                             share_pct="" if share is None else share, notes=notes))
    return rows


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/jucar"
    os.makedirs(out_dir, exist_ok=True)
    udu_zip, gw_zip, sw_zip = (download(u, out_dir) for u in (UDU_ZIP, GW_ZIP, SW_ZIP))
    units = read_xlsx(udu_zip, "_M0_PHJ_2022_2027_Unidades_de_demanda_urbana_UDU.xlsx")
    munis = read_xlsx(udu_zip, "_D0_Municipios.xlsx")
    gw = {r["Cód. Masa"]: r["Masa Subterránea"] for r in read_xlsx(gw_zip, "_M0_PHJ_2022_2027_Masas_de_agua_subterranea.xlsx")}
    sw = {r["Cód. Masa"]: r for r in read_xlsx(sw_zip, "_M0_Todas.xlsx")}
    fichas = read_fichas(download(ANEJO3, out_dir))

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for u in units:
            w.writerow([u["Cód. UDU"], u["UDU"]])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for m in sorted(munis, key=lambda m: (m["CodUDU"], m["Cód. Municipio"])):
            w.writerow([m["Cód. Municipio"].zfill(5), m["CodUDU"], "", "", ""])
    sources = build_sources(fichas, gw, sw)
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_code", "municipality_code", "source_rank", "source_type", "source_name",
                                          "role", "water_body_code", "share_pct", "notes"])
        w.writeheader()
        w.writerows(sources)

    missing = sorted({u["Cód. UDU"] for u in units} - {c for c, f in fichas.items() if f.get("origin")})
    meta = {
        "plan": "jucar", "basin_id": "ES080", "source": "ph-jucar-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("Plan Hidrológico de la Demarcación Hidrográfica del Júcar 2022-2027: open data F2849 "
                            "'Unidades de demanda urbana UDU' (unit and municipality lists); Memoria Anejo 3 'Usos y "
                            "demandas', Apéndice 1.1 fichas of the urban demand units, section 3 'Origen del agua "
                            "actual' (sources); water body names from open data F2333 and F2626"),
        "source_url": UDU_ZIP,
        "notes": ("Municipality -> UDU from the CHJ open data (each municipality in exactly one UDU, so share_pct is "
                  "empty). Sources are the 'principales puntos de abastecimiento' of each ficha, at unit level "
                  "(municipality_code empty), with the plan's water body codes; names come from the CHJ water body "
                  "lists (surface bodies named 'Embalse de X' -> reservoir X; river bodies -> the river, the stretch "
                  "in notes). The ficha percentages are within each origin (surface, groundwater, desalination, "
                  "transfer, reuse); share_pct here is the share of the unit's total current supply "
                  "(pct x origin volume / total volume), the within-origin figure is kept in notes. The fichas list only the main supply points, so the shares of a "
                  "unit add up to less than 100 in some units (lowest about 74%). 'No asig. MA' "
                  "(supply point not assigned to a water body) gives a source without name or code. The fichas do "
                  "not name the Júcar-Turia canal or the Tajo-Segura transfer, so those are not listed as such: "
                  "they appear as the surface water bodies where the water is taken. The plan's municipality list "
                  "covers the municipalities with population inside the district (including 3 in Tarragona)."
                  + (f" UDUs without a parsed ficha: {', '.join(missing)}." if missing else "")),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(munis)} municipalities, {len(units)} units, {len(fichas)} fichas, {len(sources)} sources -> {out_dir}")
    if missing:
        print("no sources parsed for:", ", ".join(missing))


if __name__ == "__main__":
    main()
