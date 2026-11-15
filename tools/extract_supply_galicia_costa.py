"""Galicia-Costa river-basin plan 2021-2027: which supply unit serves each concello, and where it takes its water.

Source: Plan Hidrolóxico da Demarcación Hidrográfica de Galicia-Costa (ciclo 2021-2027), Anexo III "Usos e demandas
da auga" (version V.00.02, approved by Real Decreto 48/2023 of 24 January), Apéndice 3.1 "Unidades de demanda urbana
(UDU)", table 2 "Infraestruturas do ciclo da auga das UDU":
  https://augasdegalicia.xunta.gal/c/document_library/get_file?file_path=/portal-augas-de-galicia/plans/planHidroloxicoGC/2021_2027/Anexo_03_Usos_DD_gal.pdf
One row per concello: name, INE code, UDU code (one UDU per concello), exploitation system, 2019 demand and
"Fonte de abastecemento" in Galician free text ("Río Ulla e MAS Santiago-Sar", "Río de Arcos, Trasvase Muros SE6 e
Encoro Santa Uxía"). The text is split into sources with the rules below (Encoro = reservoir, Río/Rego = river,
MAS = groundwater body, Trasvase = transfer, e = and).

Writes, into OUT_DIR (default data/raw/plans/galicia_costa): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv (format: tools/supply_plans_format.md).

Usage: uv run --with pdfplumber python tools/extract_supply_galicia_costa.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import urllib.request

import pdfplumber

URL = ("https://augasdegalicia.xunta.gal/c/document_library/get_file?file_path=/portal-augas-de-galicia/plans/"
       "planHidroloxicoGC/2021_2027/Anexo_03_Usos_DD_gal.pdf")
PDF_NAME = "Anexo_03_Usos_DD_gal.pdf"
REFERENCE = "data/raw/ine/municipalities_reference.csv"
UNIT_CODE = re.compile(r"ES014UDU\d{4}")


def download(out_dir):
    path = os.path.join(out_dir, PDF_NAME)
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def tidy(s):
    return re.sub(r"\s+", " ", s or "").strip(" ,.;")


def read_table(pdf_path):
    """Rows of the Apéndice 3.1 table 2 (pages whose header has 'Fonte de abastecemento' and 'Código UDU')."""
    rows, seen = [], set()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "Fonte de abastecemento" not in text or "Código UDU" not in text:
                continue
            for table in page.extract_tables():
                for raw in table:
                    cells = [c or "" for c in raw]
                    if len(cells) < 9 or not re.fullmatch(r"\d{5}", tidy(cells[1])):
                        continue
                    code = re.sub(r"\s+", "", cells[2])            # 'ES014UDU050\n2' -> 'ES014UDU0502'
                    if not UNIT_CODE.fullmatch(code):
                        raise ValueError(f"page {i + 1}: unexpected unit code {cells[2]!r}")
                    ine = tidy(cells[1])
                    if ine in seen:
                        continue
                    seen.add(ine)
                    # Wrapped lines inside a name ('Coruña-\nBetanzos') join without a space.
                    source = re.sub(r"-\s*\n\s*", "-", cells[6])
                    rows.append(dict(name=tidy(cells[0]), ine=ine, unit_code=code, system=tidy(cells[3]),
                                     demand=tidy(cells[5]), source=tidy(source), page=i + 1))
    return rows


# Galician source texts the rules below would misread, written out by hand: text -> [(type, name, role, notes)].
OVERRIDES = {
    "Trasvase SE 7 e ETAP de Mazarillos": [
        ("transfer", "SE7", "main", "water from exploitation system 7 of Galicia-Costa, treated at ETAP de Mazarillos")],
    "Río Umia, Toma del Ulla Padrón e MAS Caldas-O Salnes": [
        ("river", "río Umia", "main", None), ("river", "río Ulla", "main", "intake at Padrón"),
        ("aquifer", "Caldas-O Salnes", "main", None)],
    "Encoro de Zamans, Trasvase Cuenca Miño-Sil e MAS O Morrazo Pontevedra": [
        ("reservoir", "Zamáns", "main", None),
        ("transfer", "Miño-Sil", "main", "water brought from the Miño-Sil river basin district"),
        ("aquifer", "O Morrazo Pontevedra", "main", None)],
    "MAS Río Arllons o Costa de A Coruña ata o límite con Arteixo": [
        ("aquifer", "Río Anillons o Costa de A Coruña ata o límite con Arteixo", "main", "plan prints 'Arllons'")],
}

SE = re.compile(r"\b(?:SE|Sistema Explotación)\s*-?\s*(\d+)", re.I)


def transfer(body):
    """'SE 11' / 'Muros SE6' / 'Cuenca Miño-Sil' / 'del río Anos' / 'del Río Sor SE16' -> (name, notes)."""
    body = re.sub(r"^del?\s+", "", body)
    se = SE.search(body)
    if re.search(r"Miño-Sil", body):
        return "Miño-Sil", "water brought from the Miño-Sil river basin district"
    river = re.match(r"[Rr]ío\s+(.+?)(?:\s+SE-?\s*\d+)?$", body)
    if river:
        name = "río " + river.group(1)
        return name, (f"transfer from exploitation system {se.group(1)} of Galicia-Costa" if se else "transfer from another catchment")
    if se:
        place = tidy(SE.sub("", body))
        return f"SE{se.group(1)}", (f"water from exploitation system {se.group(1)} of Galicia-Costa"
                                    + (f" ({place})" if place else ""))
    return tidy(body), None


def parse_sources(text):
    """Galician 'Fonte de abastecemento' -> list of (source_type, source_name, role, notes)."""
    text = tidy(text)
    if not text:
        return []
    if text in OVERRIDES:
        return OVERRIDES[text]
    out = []
    for part in re.split(r",\s*|\s+e\s+", text):
        p = tidy(part)
        if not p:
            continue
        m = re.match(r"(?:MAS|MA subterránea|Masa de agua subterránea)\s+(.*)$", p)
        if m:
            body = tidy(m.group(1))
            if body.endswith("…"):
                out.append(("aquifer", None, "main", f"groundwater body name truncated in the plan ('MAS {body}')"))
            elif re.match(r"Sist\.? Expl\.? (\d+)", body):
                out.append(("aquifer", None, "main",
                            f"groundwater in exploitation system {re.search(r'(\d+)', body).group(1)} (no body named)"))
            else:
                out.append(("aquifer", re.sub(r"\s*-\s*", "-", body) if " - " in body else body, "main", None))
            continue
        m = re.match(r"Encoro\s+(?:(de|do|da|das|dos)\s+)?(.+)$", p)
        if m:
            art = {"das": "As ", "dos": "Os ", "da": "A ", "do": "O "}.get(m.group(1) or "", "")
            name = m.group(2)
            if name.startswith("Río "):                 # 'Encoro do Río Cobo'
                art = ""
            out.append(("reservoir", art + name, "main", None))
            continue
        m = re.match(r"Trasvase\s+(.+)$", p)
        if m:
            name, notes = transfer(m.group(1))
            out.append(("transfer", name, "main", notes))
            continue
        m = re.match(r"(Río|Rego)\s+(.+)$", p, re.I)
        if m:
            body, notes = m.group(2), None
            alt = re.match(r"(.+?)\s+ou\s+(.+)$", body)          # 'Río Lieiro ou Cobo'
            if alt:
                body, notes = alt.group(1), f"also called {alt.group(2)}"
            out.append(("river", m.group(1).lower() + " " + body, "main", notes))
            continue
        raise ValueError(f"unparsed source {p!r} in {text!r}")
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/galicia_costa"
    os.makedirs(out_dir, exist_ok=True)
    rows = read_table(download(out_dir))
    with open(REFERENCE, newline="") as f:
        known = {r["municipality_code"] for r in csv.DictReader(f)}

    unmatched = [r for r in rows if r["ine"] not in known]
    rows = [r for r in rows if r["ine"] in known]
    units = {}
    for r in rows:
        units.setdefault(r["unit_code"], r["name"])

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for code in sorted(units):
            w.writerow([code, units[code]])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for r in sorted(rows, key=lambda r: r["ine"]):
            w.writerow([r["ine"], r["unit_code"], "", r["source"], ""])
    counts = {}
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        for r in sorted(rows, key=lambda r: r["ine"]):
            for rank, (kind, name, role, notes) in enumerate(parse_sources(r["source"]), 1):
                counts[kind] = counts.get(kind, 0) + 1
                # One UDU per concello, so the sources are the unit's; municipality_code stays empty.
                w.writerow([r["unit_code"], "", rank, kind, name or "", role, "", "", notes or ""])
    with open(os.path.join(out_dir, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_name", "province_hint", "reason"])
        for r in unmatched:
            w.writerow([r["name"], r["ine"][:2], f"INE code {r['ine']} not in municipalities_reference.csv"])

    no_source = [r["name"] for r in rows if not r["source"]]
    meta = {
        "plan": "galicia_costa", "basin_id": "ES014", "source": "ph-galicia-costa-2021-2027",
        "plan_cycle": "2021-2027",
        "source_document": "Plan Hidrolóxico da Demarcación Hidrográfica de Galicia-Costa (ciclo 2021-2027), Anexo III "
                           "Usos e demandas da auga (V.00.02, aprobado por Real Decreto 48/2023), Apéndice 3.1 Unidades "
                           "de demanda urbana, táboa 2 Infraestruturas do ciclo da auga das UDU",
        "source_url": URL,
        "notes": ("Galicia-Costa calls its third-cycle plan 2021-2027 (the national cycle is 2022-2027). The plan defines "
                  "one urban supply unit (UDU) per concello, so every source applies to the whole unit and unit_name is "
                  "the concello name as printed. 'Fonte de abastecemento' is in Galician and kept verbatim in "
                  "intake_description; 'MAS' = groundwater body (masa de auga subterránea), 'Trasvase SEn' = water "
                  "brought from exploitation system n of the same district (typed transfer), 'Trasvase Cuenca Miño-Sil' "
                  "= water from the Miño-Sil district. Groundwater-body names are kept as printed (spellings vary). "
                  f"{len(no_source)} concellos have no source in the table ({', '.join(no_source)}); they keep their "
                  "unit but get no source rows. Anexo V (balances) splits each UDU's take into surface/groundwater "
                  "percentages by model node; that split is not used here."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    demand = sum(float(r["demand"].replace(".", "").replace(",", ".")) for r in rows if r["demand"])
    print(f"{len(rows)} concellos, {len(units)} supply units, {sum(counts.values())} sources {counts}, "
          f"{len(unmatched)} unmatched, 2019 demand {demand:.2f} hm3 -> {out_dir}")


if __name__ == "__main__":
    main()
