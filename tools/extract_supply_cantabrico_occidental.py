"""Cantábrico Occidental river-basin plan 2022-2027: which supply unit serves each municipality, and where it takes
its water.

Source: Plan Hidrológico de la Demarcación Hidrográfica del Cantábrico Occidental, revisión de tercer ciclo 2022-2027
(Real Decreto 35/2023), Apéndice III.1 "Fichas de Unidades de Demanda", section 1 "Fichas de unidades de demanda
urbana" (one ficha per page):
  https://www.chcantabrico.es/documents/d/guest/apendice-iii-1-fichas-de-unidades-de-demandas
Each ficha gives the UDU code(s) and name, the exploitation system, the municipality or municipalities served (names
only, INE register style "Astillero, El", comma-separated), "Tomas masa de agua" (the water bodies the unit takes
from, with their codes: "ES018MSPFES171MAL000030 Embalse de Alfilorios", "ES018MSBT012-017 Puerto del Escudo"),
the allocated volume and the 2021 population.

Writes, into OUT_DIR (default data/raw/plans/cantabrico_occidental): meta.json, supply_units.csv,
municipality_supply.csv, supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md).

Usage: uv run --with pdfplumber python tools/extract_supply_cantabrico_occidental.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

URL = "https://www.chcantabrico.es/documents/d/guest/apendice-iii-1-fichas-de-unidades-de-demandas"
PDF_NAME = "apendice-iii-1-fichas-de-unidades-de-demandas.pdf"
REFERENCE = "data/raw/ine/municipalities_reference.csv"
# Provinces the district covers: Asturias, Cantabria, Lugo, León, Bizkaia, Burgos, Palencia.
PROVINCES = ("33", "39", "27", "24", "48", "09", "34")
WATER_BODY = re.compile(r"^(ES018MS(?:PF|BT)[A-Z0-9-]+)\s+(.*)$")
TRAILING_NUMBERS = re.compile(r"\s+\d+(?:,\d+)?\s+\d+(?:,\d+)?\s+(?:\d+%|-)\s*$")

# 'Municipio' fields the comma rule cannot split: verbatim text -> plan names.
MUNICIPIO_OVERRIDES = {
    "Karrantza Harana/Valle de Carranza Y Lanestosa": ["Karrantza Harana/Valle de Carranza", "Lanestosa"],
}


def download(out_dir):
    path = os.path.join(out_dir, PDF_NAME)
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def tidy(s):
    return re.sub(r"\s+", " ", s or "").strip(" ,.;")


def read_fichas(pdf_path):
    fichas = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "UNIDADES DE DEMANDA URBANA" not in text or "Código UDU" not in text:
                continue
            head, rest = text.split("2. TOMAS ASOCIADAS")
            head = head.split("1. IDENTIFICACIÓN")[-1]
            body = rest.split("3. DEMANDAS")[0]
            codes = re.findall(r"\bUDU\d{4}\b", head)
            system = re.search(r"Sistema de explotación\s+(.+?)\s+UTE\s+(\d+)", head)
            municipio = re.search(r"Municipio\s+(.+)", head).group(1)
            name = head.split("Sistema de explotación")[0]
            name = tidy(re.sub(r"Código UDU|Nombre UDU|\bUDU\d{4}\b", " ", name))
            intakes, volume = [], None
            for line in body.splitlines():
                line = line.strip()
                m = re.search(r"(\d+,\d+|\d+)\s+(\d+,\d+|\d+)\s+(\d+%|-)\s*$", line)
                if m:
                    volume = float(m.group(1).replace(",", "."))
                    line = TRAILING_NUMBERS.sub("", line).strip()
                if not line or re.match(r"(Volumen|Tomas masa|asignado|\(hm3)", line):
                    continue
                wb = WATER_BODY.match(line)
                if wb:
                    intakes.append([wb.group(1), tidy(re.sub(r"(\w)- ", r"\1-", wb.group(2)))])
                elif intakes and not re.match(r"^[\d,% -]+$", line):
                    intakes[-1][1] = tidy(intakes[-1][1] + " " + line)   # wrapped name ('Lago de' / 'La Ercina')
            pop = re.search(r"Población estimada 2021\s+([\d.]+)", text)
            monthly = re.search(r"^\s*(?:\d+,\d+\s+){12}(\d+,\d+)\s*$", text.split("3. DEMANDAS")[-1], re.M)
            fichas.append(dict(page=i + 1, codes=codes, name=name, system=system.group(1) if system else "",
                               municipio=tidy(municipio), intakes=intakes, volume=volume,
                               demand=float(monthly.group(1).replace(",", ".")) if monthly else 0.0,
                               population=int(pop.group(1).replace(".", "")) if pop else None))
    return fichas


def fold(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


ARTICLES = ("el", "la", "los", "las", "a", "o", "as", "os")


def name_keys(name):
    """'Rozas de Madrid, Las' -> {'rozas de madrid las', 'las rozas de madrid', 'rozas de madrid'};
    bilingual names give keys for each form and for the whole."""
    keys = set()
    for form in [name] + name.split("/"):
        form = form.strip()
        m = re.match(r"(.+),\s*(\w+)$", form)
        if m and m.group(2).lower() in ARTICLES:
            keys |= {fold(m.group(1)), fold(m.group(2) + " " + m.group(1))}
        else:
            keys.add(fold(form))
            m = re.match(r"(\w+)\s+(.+)$", form)
            if m and m.group(1).lower() in ARTICLES:
                keys.add(fold(m.group(2)))
    return keys


def load_reference():
    index = {}
    with open(REFERENCE, newline="") as f:
        for r in csv.DictReader(f):
            if r["province_code"] in PROVINCES:
                for k in name_keys(r["official_name"]):
                    index.setdefault(k, set()).add(r["municipality_code"])
    return index


def split_municipios(text):
    """'Santander, Astillero, El, Camargo' -> ['Santander', 'Astillero, El', 'Camargo']."""
    if text in MUNICIPIO_OVERRIDES:
        return MUNICIPIO_OVERRIDES[text]
    out = []
    for part in [p.strip() for p in text.split(",") if p.strip()]:
        if out and part.lower() in ARTICLES:
            out[-1] = f"{out[-1]}, {part}"
        else:
            out.append(part)
    return out


def source_of(code, name):
    """Water body code + name -> (source_type, source_name, notes), or None for coastal waters."""
    kind = re.search(r"ES\d{3}(MA[A-Z])", code)
    kind = kind.group(1) if kind else None
    if "MSBT" in code:
        return "aquifer", name, None
    if kind == "MAC":
        return None                                    # coastal water body: no supply type fits; see meta notes
    m = re.match(r"Embalse de (.+)$", name)
    if m:
        return "reservoir", m.group(1)[0].upper() + m.group(1)[1:], None
    if kind == "MAL":                                  # lake water body that is not a reservoir
        return "reservoir", name, "natural lake water body"
    if kind == "MAT":
        return "river", name, "transitional water body (estuary)"
    river = re.sub(r"\s+[IVX]+$", "", name)            # water-body stretch numbering: 'Río Negro II' -> 'Río Negro'
    river = re.sub(r"^(Río|Arroyo|Ría)\b", lambda g: g.group(1).lower(), river)
    return "river", river, None


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/cantabrico_occidental"
    os.makedirs(out_dir, exist_ok=True)
    fichas = read_fichas(download(out_dir))
    index = load_reference()

    units, links, sources, unmatched, skipped_coastal = {}, [], [], [], {}
    for fi in fichas:
        unit = "+".join(fi["codes"])
        if unit in units:
            raise ValueError(f"duplicate unit {unit} on page {fi['page']}")
        units[unit] = fi
        for plan_name in split_municipios(fi["municipio"]):
            codes = set()
            for k in name_keys(plan_name):
                codes |= index.get(k, set())
            if len(codes) == 1:
                links.append(dict(municipality_code=codes.pop(), unit_code=unit, plan_name=plan_name))
            else:
                unmatched.append([plan_name, "/".join(PROVINCES), f"{len(codes)} matches in the district's provinces "
                                  f"(ficha {unit}, page {fi['page']})"])
        rank, seen = 0, set()
        for code, name in fi["intakes"]:
            if code in seen:
                continue
            seen.add(code)
            src = source_of(code, name)
            if src is None:
                skipped_coastal.setdefault(name, set()).add(unit)
                continue
            rank += 1
            sources.append([unit, "", rank, src[0], src[1], "main", code, "", src[2] or ""])

    # A municipality split between several single-municipality units: share from the units' 2021 populations.
    by_muni = {}
    for link in links:
        by_muni.setdefault(link["municipality_code"], []).append(link)
    for code, ls in by_muni.items():
        if len(ls) > 1:
            if any(len(split_municipios(units[l["unit_code"]]["municipio"])) > 1 for l in ls):
                raise ValueError(f"{code} split between units that also serve other municipalities")
            total = sum(units[l["unit_code"]]["population"] for l in ls)
            for l in ls:
                l["share_pct"] = round(100 * units[l["unit_code"]]["population"] / total, 1)

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for code in sorted(units):
            w.writerow([code, units[code]["name"]])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for l in sorted(links, key=lambda l: (l["municipality_code"], l["unit_code"])):
            w.writerow([l["municipality_code"], l["unit_code"], l.get("share_pct", ""), "", ""])
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        w.writerows(sources)
    with open(os.path.join(out_dir, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_name", "province_hint", "reason"])
        w.writerows(unmatched)

    multi = [u for u in units if "+" in u]
    coastal = "; ".join(f"{n} ({', '.join(sorted(us))})" for n, us in sorted(skipped_coastal.items()))
    meta = {
        "plan": "cantabrico_occidental", "basin_id": "ES018", "source": "ph-cantabrico-occidental-2022-2027",
        "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Cantábrico Occidental, revisión de "
                           "tercer ciclo 2022-2027 (Real Decreto 35/2023), Apéndice III.1 Fichas de Unidades de "
                           "Demanda, 1. Fichas de unidades de demanda urbana",
        "source_url": URL,
        "notes": ("One ficha per urban supply unit. Municipalities are given by name only and were matched to INE codes "
                  "within Asturias, Cantabria, Lugo, León, Bizkaia, Burgos and Palencia. "
                  f"{len(multi)} fichas carry two or three UDU codes for one unit ({', '.join(multi)}); they are kept "
                  "as one unit whose code joins the printed codes with '+'. Where one municipality is split between "
                  "several units (Oviedo, Gijón, Villaviciosa, Laviana…), share_pct is each unit's 2021 population "
                  "(ficha) over the sum of those units' populations, i.e. derived from the plan's figures. Sources are "
                  "the ficha's 'Tomas masa de agua': water bodies with their codes, all role main (the fichas do not "
                  "rank them); river stretches lose their stretch numbering in source_name ('Río Nalón V' -> 'río "
                  "Nalón') but keep the stretch code; 'Embalse de …' water bodies are reservoirs; estuaries are typed "
                  "river with a note. Coastal water bodies listed as intakes are left out because no supply type fits: "
                  f"{coastal}. Apéndice III.1 lists the municipalities the plan models; municipalities in the district "
                  "without a ficha (small systems, or supplied from another district) have no row. Ficha UDU0560 gives "
                  "'Villoria' as its municipality, which is not an INE municipality (it is a parish of Laviana); it is "
                  "listed in unmatched.csv rather than guessed."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    counts = {}
    for s in sources:
        counts[s[3]] = counts.get(s[3], 0) + 1
    volume = sum(fi["volume"] or 0 for fi in fichas)
    demand = sum(fi["demand"] for fi in fichas)
    print(f"{len(fichas)} fichas, {len(units)} units, {len(by_muni)} municipalities ({len(links)} links), "
          f"{len(sources)} sources {counts}, {len(unmatched)} unmatched, allocated {volume:.2f} hm3, "
          f"demand {demand:.2f} hm3 (Anejo III tabla 82: 205.24) -> {out_dir}")


if __name__ == "__main__":
    main()
