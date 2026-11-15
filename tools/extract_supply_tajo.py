"""Tajo river-basin plan 2022-2027: which supply unit serves each municipality, and where it takes its water.

Source: Plan Hidrológico de la parte española de la Demarcación Hidrográfica del Tajo (2022-2027),
Anejo 3 "Usos y demandas de agua", Tabla 2 "Agrupación de los núcleos poblacionales en UDU"
  https://www.chtajo.es/documents/d/guest/pht2227_an03_usosdemandasagua_dic22
One row per municipality: INE code, supply unit (UDU) code and name, and the unit's ordinary intake as free text
("Toma en embalses de Guadiloba y Alcántara", "MASub Talavera - Picadas II", "Red del CYII - Embalse de Pinilla").

Writes meta.json, supply_units.csv, municipality_supply.csv and supply_sources.csv into OUT_DIR (default
data/raw/plans/tajo), in the format of tools/supply_plans_format.md. The intake text is split into sources with the
rules below; reservoir names are matched to ref.reservoirs later, in SQL (sql/reference/water_supply.sql).

Usage: uv run --with pdfplumber python tools/extract_supply_tajo.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import urllib.request

import pdfplumber

URL = "https://www.chtajo.es/documents/d/guest/pht2227_an03_usosdemandasagua_dic22"
UNIT_CODE = re.compile(r"S[A-Z]{2}\d{2}[A-Z]\d{2}[a-z]?")


def download(out_dir):
    path = os.path.join(out_dir, "pht2227_an03_usosdemandasagua_dic22.pdf")
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def read_table(pdf_path):
    rows, seen = [], set()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "Toma ordinaria" not in text or "Nombre UDU" not in text:
                continue
            for table in page.extract_tables():
                for raw in table:
                    cells = [re.sub(r"\s+", " ", c).strip() for c in raw if c]
                    if len(cells) < 4 or not re.fullmatch(r"\d{4,5}", cells[0]):
                        continue
                    k = next((j for j, c in enumerate(cells) if UNIT_CODE.fullmatch(c)), None)
                    if k is None:
                        continue
                    extra = cells[-1] if re.fullmatch(r"\d+", cells[-1]) else ""
                    tail = cells[k + 1:-1] if extra else cells[k + 1:]
                    code = cells[0].zfill(5)   # Ávila and other provinces below 10 lose their leading zero
                    if code in seen:
                        continue
                    seen.add(code)
                    rows.append(dict(municipality_code=code, municipality_name=" ".join(cells[1:k]),
                                     unit_code=cells[k], unit_name=tail[0] if tail else "",
                                     intake_description=" ".join(tail[1:]),
                                     additional_intakes=extra, page=i + 1))
    return rows


def tidy(s):
    s = re.sub(r"\s+", " ", s).strip(" ,.-–")
    return s


def split_names(s):
    """'Torcón I, Picadas, Almoguera y Guajaraz' -> ['Torcón I', 'Picadas', 'Almoguera', 'Guajaraz']"""
    parts = re.split(r",\s*|\s+y\s+", s)
    return [tidy(p) for p in parts if tidy(p)]


RESERVOIR = re.compile(r"\b(?:[Ee]mbalses?|Emb\.?|[Pp]resa)\s+(?:de(?:l)?\s+)?(.+)")
WATERCOURSE = re.compile(r"\b((?:[Rr]ío|[Aa]rroyos?|[Gg]arganta|[Rr]egato|[Rr]ivera)\b.*)")
SPRINGS = re.compile(r"\bmana?n?tial(?:es)?\b", re.I)

# Descriptions the rules below would misread, written out by hand (verbatim text -> sources).
OVERRIDES = {
    "Toma superficial en la Balsa de la Sierra (Arroyo de Yuste)": [("river", "arroyo de Yuste", "main", "intake pond Balsa de la Sierra")],
    "Toma superficial en balsa sin nombre": [("river", None, "main", "unnamed intake pond")],
    "Toma subt. fuera de MASub - Una urbanización toma en embalse de Borbollón": [
        ("aquifer", None, "main", "groundwater outside a defined groundwater body"),
        ("reservoir", "Borbollón", "minor", "one housing estate only")],
    "Fuentes propias (azud de los Batanes, arroyo de los Frailes y extraordinariamente dos pozos)": [
        ("river", "azud de los Batanes", "main", None), ("river", "arroyo de los Frailes", "main", None),
        ("aquifer", None, "backup", "two wells, used exceptionally")],
    "Fuentes propias (embalse de Valdehonduras); conectado a Santa Lucía": [
        ("reservoir", "Valdehonduras", "main", None), ("reservoir", "Santa Lucía", "backup", "connected")],
    "Fuentes propias (embalse de El Prado y extraordinariamente dos sondeos); conectado a Santa Lucía": [
        ("reservoir", "El Prado", "main", None), ("aquifer", None, "backup", "two boreholes, used exceptionally"),
        ("reservoir", "Santa Lucía", "backup", "connected")],
    "Toma superficiales en embalses de El Charco y Las Moreras, y bombeo desde el Tiétar": [
        ("reservoir", "El Charco", "main", None), ("reservoir", "Las Moreras", "main", None),
        ("river", "río Tiétar", "main", "pumped")],
    "Toma en embalse de Cazalegas (refuerzo de La Portiña en desuso)": [
        ("reservoir", "Cazalegas", "main", "former backup from La Portiña no longer used")],
    "Bombeo de Orellana (Guadiana) - Embalse de Navarredonda en desuso por calidad": [
        ("reservoir", "Orellana", "main", "pumped from the Guadiana basin; Navarredonda reservoir no longer used (water quality)")],
    "Toma en embalse de Béjar - Pertenece a la Mancomunidad, pero no se abastece de ella: tiene 2 captaciones (Avellaneda y Canalizo) y 2 sondeos (El Barranco y el Egido)": [
        ("river", None, "main", "two own intakes (Avellaneda, Canalizo)"), ("aquifer", None, "main", "two own boreholes (El Barranco, El Egido)")],
    "Toma ordinaria en manatiales Aliseda y Fuente Aceituna. 3 pozos de uso extraordinario": [
        ("spring", "Aliseda", "main", None), ("spring", "Fuente Aceituna", "main", None),
        ("aquifer", None, "backup", "three wells, used exceptionally")],
    "Toma superficial en arroyos Castañarejo, de La Canalita y Bajohondo": [
        ("river", "arroyo Castañarejo", "main", None), ("river", "arroyo de La Canalita", "main", None),
        ("river", "arroyo Bajohondo", "main", None)],
    "Toma superficial en el Arroyo Malmonedilla, afluente del río Cedena": [("river", "arroyo Malmonedilla", "main", "tributary of the río Cedena")],
    "Toma en embalse de El Santo/El Pueblo": [("reservoir", "El Santo", "main", "also called El Pueblo")],
}


def parse_sources(intake):
    """Turn one intake description into a list of (source_type, source_name, role, notes).
    source_type: reservoir, river, aquifer, spring or network; role: main, backup or minor.
    Notes are short English remarks of ours; the plan's own wording stays in intake_description."""
    text = re.sub(r"\s+", " ", intake).strip().rstrip(".")
    if text in OVERRIDES:
        return OVERRIDES[text]
    text = (text.replace("subterrránea", "subterránea").replace("fuerea", "fuera").replace("supferficial", "superficial")
                .replace("manatial", "manantial"))
    out = []

    def add(kind, name, role="main", notes=None):
        if (kind, name) not in [(o[0], o[1]) for o in out]:
            out.append((kind, name, role, notes))

    m = re.match(r"Red (?:del )?CYII\b\s*[-–]?\s*(.*)", text)
    if m:   # Canal de Isabel II network; its reservoirs are added from the curated network table
        add("network", "Canal de Isabel II")
        text = m.group(1)
    m = re.match(r"Mancom\.?\s+(?:de\s+)?(.+?)(?:\s+\((Tajo|Guadiana)\))?(?:\s+[-–]\s+.*)?$", text)
    if m:
        name = "Mancomunidad " + tidy(m.group(1))
        name = re.sub(r"^Mancomunidad Aguas", "Mancomunidad de Aguas", name)
        add("network", name, notes=f"takes water in the {m.group(2)} basin" if m.group(2) else None)
        return out
    if text.startswith("MASub"):
        body = text[len("MASub"):].strip()
        body = re.split(r"\s+-\s+Mdad", body)[0]
        add("aquifer", re.sub(r"\s*-\s*", " - ", body))   # one spelling for "Tajuña-Montes Universales" / "Tajuña - Montes Universales"
        return out
    if re.match(r"Toma subterránea fuera de (MASub|masa)", text):
        add("aquifer", None, notes="groundwater outside a defined groundwater body")
        return out
    if text.startswith("Tomas en arroyos y manantiales"):
        add("spring", None, notes="streams and springs outside a defined groundwater body")
        return out

    # Clauses: 'principal ... y refuerzo ...', 'Toma de refuerzo ...' after a full stop, '..., almacenamiento en ...',
    # and trailing remarks after ' – ' or ' - ' (dropped: they stay in intake_description).
    text = re.split(r"\s+[–]\s+|\s+-\s+(?=[A-Z][a-z]+ [a-z]|Sistema|Mdad|ETAP|Núcleo|Conex|Tiene|Urbaniz|Los núcleos|Pertenece)", text)[0]
    clauses = re.split(r"(?<!Emb)\.\s+|,?\s+(?=almacenamiento)|\s+y\s+(?=(?:posible\s+)?refuerzo|bombeo|\d+\s+mana)", text)
    for clause in clauses:
        c = tidy(clause)
        if not c:
            continue
        r_any = RESERVOIR.search(c)
        role = "backup" if re.search(r"refuerzo", c[: r_any.start()] if r_any else c) else "main"
        if re.search(r"\bpozos?\b|sondeos?", c) and not r_any:
            add("aquifer", None, "backup" if "extraordinari" in c else role, "wells")
            continue
        if SPRINGS.search(c) and not r_any:
            names = re.sub(r".*?mana?n?tial(?:es)?\s*", "", c)
            if names and not re.match(r"^\d", names):
                for n in split_names(names):
                    add("spring", n, role)
            else:
                add("spring", None, role, (re.search(r"(\d+)\s+mana", c).group(1) + " springs") if re.search(r"(\d+)\s+mana", c) else None)
            continue
        for piece in re.split(r"\s+y\s+(?=[Ee]mbalse)", c):
            r = RESERVOIR.search(piece)
            w = WATERCOURSE.search(piece)
            if r and (not w or r.start() < w.start()):
                names = re.sub(r"\s*\([^)]*\)", "", r.group(1))       # parenthetical remarks
                names = re.sub(r"\s*(exclusivamente|en desuso.*)$", "", names)
                for n in split_names(names):
                    if re.fullmatch(r"[IVX]+", n):                      # 'Torcón I y II', 'Malpartida de Plasencia I, II y III'
                        continue
                    add("reservoir", re.sub(r"\s+[IVX]+$", "", n), role)
            elif w:
                name = tidy(re.sub(r"\s*\(.*$", "", w.group(1)))
                add("river", name[0].lower() + name[1:], role)
    return out


META = {
    "plan": "tajo", "basin_id": "ES030", "source": "ph-tajo-2022-2027", "plan_cycle": "2022-2027",
    "source_document": "Plan Hidrológico de la parte española de la Demarcación Hidrográfica del Tajo (2022–2027), "
                       "Anejo 3 Usos y demandas de agua, Tabla 2 Agrupación de los núcleos poblacionales en UDU",
    "source_url": URL,
    "notes": "Intakes are described municipality by municipality, so every source row carries municipality_code. "
             "Networks (Canal de Isabel II, mancomunidades) are listed as network sources; their own reservoirs are "
             "curated separately.",
}


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/tajo"
    os.makedirs(out_dir, exist_ok=True)
    rows = read_table(download(out_dir))
    units = {}
    for r in rows:
        units.setdefault(r["unit_code"], r["unit_name"])
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(META, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["unit_code", "unit_name"])
        w.writerows(sorted(units.items()))
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for r in rows:
            w.writerow([r["municipality_code"], r["unit_code"], "", r["intake_description"], r["additional_intakes"]])
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        for r in rows:
            for rank, (kind, name, role, notes) in enumerate(parse_sources(r["intake_description"]), 1):
                w.writerow([r["unit_code"], r["municipality_code"], rank, kind, name or "", role, "", "", notes or ""])
    print(f"{len(rows)} municipalities, {len(units)} supply units -> {out_dir}")


if __name__ == "__main__":
    main()
