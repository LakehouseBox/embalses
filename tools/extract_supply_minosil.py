"""Miño-Sil river-basin plan 2022-2027: which supply unit serves each municipality, and where it takes its water.

chminosil.es is being rebuilt and no longer serves the plan documents, so both are read from the Internet Archive's
copies of CHMS's own files (fetched with the id_ suffix, i.e. the original bytes):
- Anejo 4 of the plan as sent for approval (VMITERD, 2022-2027), "Restricciones al uso, prioridades de usos y
  asignación de recursos", section 6, Tablas 53, 60, 67, 74, 81 and 88 "Asignación de recursos por UDU":
  code, name, "Procedencia del recurso" (río, embalse, MASb) and volume, for the UDUs the system models name.
    https://www.chminosil.es/images/planificacion/proyecto-ph-2022-2027/VMITERD/001.PHC/04._ANEJO_IV---.pdf
- Anejo III of the consultation draft of the same plan (2021-2027), Anexo 3.2 "Unidades de demanda urbana":
  one ficha per UDU (200), each one municipality ("Código UDU2101, Nombre Allariz, Municipio Allariz"), with the
  origin of its water in hm³/year (superficial, subterránea, trasvases). The approved Anejo III is not archived.
    https://www.chminosil.es/images/planificacion/consulta-proyecto-ph-21-27/03.ANEJO_III_DESCRIPCION_USOS_DEMANDAS_Y_PRESIONES.pdf

Writes, into OUT_DIR (default data/raw/plans/minosil): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md).

Usage: uv run --with pdfplumber python tools/extract_supply_minosil.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

WAYBACK = "http://web.archive.org/web/{ts}id_/{url}"
A4 = ("20250909193909", "https://www.chminosil.es/images/planificacion/proyecto-ph-2022-2027/VMITERD/001.PHC/04._ANEJO_IV---.pdf")
A3 = ("20220225051358", "https://www.chminosil.es/images/planificacion/consulta-proyecto-ph-21-27/"
                        "03.ANEJO_III_DESCRIPCION_USOS_DEMANDAS_Y_PRESIONES.pdf")
REFERENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "ine",
                         "municipalities_reference.csv")
PROVINCES = {"15", "24", "27", "32", "33", "36", "49"}   # A Coruña, León, Lugo, Ourense, Asturias, Pontevedra, Zamora
UA = "embalses-open-data/0.1"
RENAMED = {"Candín": "24036"}   # renamed Valle de Ancares in 2023


def download(out_dir, ts_url, name):
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        req = urllib.request.Request(WAYBACK.format(ts=ts_url[0], url=ts_url[1]), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


def num(s):
    return float(s.replace(".", "").replace(",", ".")) if s and re.fullmatch(r"[\d.]+,?\d*", s) else None


def read_fichas(path):
    """UDU code -> dict(name, system, municipality, surface, ground, transfer, page) from Anexo 3.2."""
    out = {}
    with pdfplumber.open(path) as pdf:
        for i in range(600, min(1200, len(pdf.pages))):
            text = pdf.pages[i].extract_text() or ""
            if "UNIDADES DE DEMANDA URBANA" not in text or "IDENTIFICACIÓN" not in text:
                continue
            m = re.search(r"Código\s+(UDU\d{4})\s*\nNombre\s+(.+?)\s*\nSistema de explotación\s+(.+?)\s*\n"
                          r"Municipio\s+(.+?)\s*\n", text)
            if not m:
                continue
            o = {k: num(v) for k, v in re.findall(r"^(Superficial|Subterránea|Trasvases)\s+([\d.,]+)\s*$", text, re.M)}
            out[m.group(1)] = dict(name=m.group(2), system=m.group(3), municipality=m.group(4),
                                   surface=o.get("Superficial"), ground=o.get("Subterránea"),
                                   transfer=o.get("Trasvases"), page=i + 1)
    return out


def read_allocations(path):
    """[(code, name, procedencia, volume, page)] from the 'Asignación de recursos por UDU' tables."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for i in range(70, 100):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            if not re.search(r"UDU \d{4}", text):
                continue
            found = []
            for table in page.extract_tables():
                for r in table:
                    cells = [c for c in r if c is not None]
                    if cells and re.fullmatch(r"UDU \d{4}", (cells[0] or "").strip()) and len(cells) >= 3:
                        found.append((cells[0].strip(), cells[1], cells[2], cells[3] if len(cells) > 3 else ""))
            if not found:   # Sil Superior is printed without ruling lines: one row per text line
                for line in text.splitlines():
                    m = re.match(r"\s*(UDU \d{4})\s+(.+?)\s+((?:R[ií]os?|Arroyo|Embalses?|MASbs?|Tramo|Cabecera)\b.*?)"
                                 r"(?:\s+([\d,]+\*?))?\s*$", line)
                    if m:
                        found.append(m.groups())
            for code, name, proc, vol in found:
                rows.append((code.replace(" ", ""), re.sub(r"\s+", " ", name or "").strip(),
                             re.sub(r"\s*\n\s*", " | ", (proc or "").strip()), (vol or "").strip(), i + 1))
    return rows


def norm(name):
    s = unicodedata.normalize("NFD", name.upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s*\((?:O|A|OS|AS|EL|LA|LOS|LAS)\)\s*$|,\s*(?:O|A|OS|AS|EL|LA|LOS|LAS)\s*$", "", s)
    s = re.sub(r"^(?:O|A|OS|AS|EL|LA|LOS|LAS)\s+", "", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def lower_first(s):
    return s[:1].lower() + s[1:]


def parse_sources(proc):
    """'Tramo alto Río Ladra | MASb Ladra' -> [(type, name, notes)]."""
    out = []

    def add(kind, name, notes=""):
        if (kind, name) not in [(o[0], o[1]) for o in out]:
            out.append((kind, name, notes))

    parts = []
    for p in proc.split(" | "):   # rejoin cells split inside a parenthesis: 'Eiras (Galicia' + 'Costa)'
        if parts and parts[-1].count("(") > parts[-1].count(")"):
            parts[-1] += " " + p
        else:
            parts.append(p)
    for part in parts:
        part = part.strip()
        notes = ""
        g = re.search(r"\(Galicia\s*Costa\)", part)
        if g:
            notes = "in the Galicia-Costa district (transfer)"
            part = part.replace(g.group(0), "").strip()
        m = re.match(r"MASbs?\s+(.+)$", part, re.I)
        if m:
            for n in re.split(r"\s+y\s+", m.group(1)):
                add("aquifer", n.strip())
            continue
        m = re.search(r"Embalses?\s+(?:de(?:l)?\s+)?(.+?)(?:\s*\((R[ií]o .+?)\))?$", part)
        if m:
            for n in re.split(r"\s+y\s+", m.group(1)):
                add("reservoir", n.strip(), "; ".join(x for x in [notes, f"on the {lower_first(m.group(2))}" if m.group(2) else ""] if x))
            continue
        m = re.search(r"\b(R[ií]os|Arroyos)\s+(.+?)(?:\s+en\s+.*)?$", part, re.I)
        if m:
            generic = "río" if m.group(1).lower().startswith("r") else "arroyo"
            for n in re.split(r"\s+y\s+", m.group(2)):
                add("river", f"{generic} {n.strip()}", notes)
            continue
        m = re.search(r"\b(R[ií]o|Arroyo)\s+(.+?)(?:\s+(?:en|desde|hasta)\s+.*)?$", part, re.I)
        if m:
            generic = "río" if m.group(1).lower().startswith("r") else "arroyo"
            names = re.split(r"\s+y\s+", m.group(2))
            for n in names:
                add("river", f"{generic} {n.strip()}", notes)
            continue
        if part:
            add("river", "", f"unparsed: {part}")
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/minosil"
    os.makedirs(out_dir, exist_ok=True)
    a4 = download(out_dir, A4, "minosil_ph2227_anejo_IV.pdf")
    a3 = download(out_dir, A3, "minosil_ph2127_borrador_anejo_III.pdf")
    fichas = read_fichas(a3)
    allocations = read_allocations(a4)

    with open(REFERENCE, newline="") as f:
        ref = {r["municipality_code"]: r for r in csv.DictReader(f) if r["municipality_code"][:2] in PROVINCES}
    by_name = {}
    for code, r in ref.items():
        for part in r["official_name"].split("/"):
            by_name.setdefault(norm(part), set()).add(code)

    by_ficha_name = {norm(v["name"]): k for k, v in fichas.items()}
    alloc = {}
    remarks = {}
    for code, name, proc, vol, page in allocations:
        if code not in fichas:   # 'UDU 2796 Entrimo' is UDU2706 in the fichas
            fixed = by_ficha_name.get(norm(name))
            if not fixed:
                continue
            remarks[fixed] = f"Anejo 4 prints it as {code}"
            code = fixed
        elif norm(name) != norm(fichas[code]["name"]) and not name.startswith("UDU"):
            remarks[code] = f"Anejo 4 names this UDU '{name}'"
        alloc.setdefault(code, []).append((proc, vol, page, name))

    unmatched, rows = [], []
    cands_of = {c: ({RENAMED[fc["municipality"]]} if fc["municipality"] in RENAMED
                    else set(by_name.get(norm(fc["municipality"]), set()))) for c, fc in fichas.items()}
    system_prov = {}   # the province most UDUs of each system lie in, to tell apart namesakes (Sobrado)
    for c, cands in cands_of.items():
        if len(cands) == 1:
            system_prov.setdefault(fichas[c]["system"], []).append(next(iter(cands))[:2])
    for code, fc in sorted(fichas.items()):
        cands = cands_of[code]
        if len(cands) > 1 and fc["system"] in system_prov:
            p = max(set(system_prov[fc["system"]]), key=system_prov[fc["system"]].count)
            cands = {c for c in cands if c[:2] == p}
        if len(cands) != 1:
            unmatched.append((fc["municipality"], "Miño-Sil provinces",
                              f"{code}: " + ("ambiguous" if cands else "no INE municipality with this name")))
            continue
        rows.append((code, cands.pop(), fc))

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for code, fc in sorted(fichas.items()):
            w.writerow([code, fc["name"]])
    n_src = 0
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f, \
            open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as g:
        w, ws = csv.writer(f), csv.writer(g)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        ws.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                     "water_body_code", "share_pct", "notes"])
        for code, mun, fc in rows:
            descr = []
            for proc, vol, page, _ in alloc.get(code, []):
                descr.append(f"Procedencia del recurso: {proc}" + (f" ({vol} hm³/año)" if vol else "") +
                             f" [Anejo 4, p. {page}]")
            origin = ", ".join(f"{k} {str(v).replace('.', ',')}" for k, v in
                               [("superficial", fc["surface"]), ("subterránea", fc["ground"]), ("trasvases", fc["transfer"])]
                               if v)
            if origin:
                descr.append(f"Origen del agua (hm³/año): {origin} [borrador Anejo III, p. {fc['page']}]")
            w.writerow([mun, code, "", "; ".join(descr), ""])
            rank = 0
            for proc, vol, page, _ in alloc.get(code, []):
                for kind, name, notes in parse_sources(proc):
                    rank += 1
                    notes = "; ".join(x for x in [notes, remarks.get(code, "")] if x)
                    ws.writerow([code, "", rank, kind, name, "main", "", "", notes])
                    n_src += 1
    with open(os.path.join(out_dir, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_name", "province_hint", "reason"])
        w.writerows(unmatched)
    named = sum(1 for c, _, _ in rows if c in alloc)
    meta = {
        "plan": "minosil", "basin_id": "ES010", "source": "ph-minosil-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("Plan Hidrológico de la parte española de la D.H. del Miño-Sil 2022-2027: Anejo 4 "
                            "(Restricciones al uso, prioridades de usos y asignación de recursos), section 6, tables "
                            "'Asignación de recursos por UDU'; UDU -> municipality from the fichas of Anexo 3.2 of the "
                            "consultation draft's Anejo III"),
        "source_url": WAYBACK.format(ts=A4[0], url=A4[1]),
        "notes": (f"{len(rows)} UDUs placed in a municipality (every UDU is one municipality), {named} with named "
                  f"sources, {n_src} source rows. chminosil.es no longer serves the plan; both PDFs are CHMS's own "
                  "files as archived by the Internet Archive (original bytes). The approved Anejo III is not archived, "
                  "so UDU codes, names and municipalities come from the consultation draft (2021-2027) Anexo 3.2, and "
                  "its 'Origen del agua' volumes are quoted in intake_description. Named sources come from the final "
                  "plan's Anejo 4 allocation tables; the plan allocates the remaining UDUs only generic 'recursos "
                  "superficiales y subterráneos del sistema', so they have no source rows. All sources role main "
                  "(the tables give no order of preference); MASb names are groundwater bodies, without codes. "
                  "Spellings are the plan's (e.g. 'Pedrsaivas'). Eiras is in the Galicia-Costa district.")}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(fichas)} UDUs, {len(rows)} municipalities, {named} with named sources, {n_src} sources, "
          f"{len(unmatched)} unmatched -> {out_dir}")


if __name__ == "__main__":
    main()
