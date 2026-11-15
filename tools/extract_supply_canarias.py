"""Canary Islands island plans, third cycle 2021-2027: which urban demand unit (UDU) serves each municipality and where
it takes its water. One output folder per island (each island is its own river-basin district).

Sources (all official; each island's Consejo Insular de Aguas, the Gobierno de Canarias BOC, or MITECO):
  Gran Canaria (ES120), Decreto 370/2023. Memoria (March 2023, the version listed under the approval decree),
    section 3.1.2.2.1 "Unidades de Demanda Urbana (UDU)", printed pages 181-192: 12 UDUs described in prose.
    https://aguasgrancanaria.com/pdfs/PlanHidro/ES120_PH_PP-Memoria-completa.pdf
  Fuerteventura (ES122), Decreto 139/2024. Memoria y Anejos, section 3.1.2.2.1, printed pages 196-202: 7 UDUs.
    https://www.aguasfuerteventura.com/documentos/8_MEMORIA_%20Y_%20ANEJOS.pdf
  Lanzarote (ES123), Decreto 110/2024. Memoria y Anejos (Diligencia), section 3.1.2.2.1, printed pages 157-162: 12 UDUs.
    https://aguaslanzarote.com/wps/wp-content/uploads/docs/3-normativa/PHL3/ES123_PH_Memoria-Anejos_Diligencia.pdf
  Tenerife (ES124), Decreto 372/2023. Normativa, Anejo 8 "Unidades de Demanda" (approved September 2023 set), one
    ficha per unit; the UP fichas (urban network, 31 municipal services + 9 independent ones) are parsed.
    https://www.aguastenerife.org/images/pdf/PHT3erCiclo/03%20NORMATIVA_AI_02%20ANEJOS%2008%20UD%20DEMANDA.pdf
  La Palma (ES125), Decreto 6/2025. Memoria (signed, linked from the Consejo Insular's "PHP 3er ciclo (vigente)"
    page, hosted on Dropbox), section 3.1.2.2.1, printed pages 149-152: 10 UDUs.
    https://www.dropbox.com/scl/fi/nkrgd339kv5s471ux483u/1.-ES125_PH-Memoria_Anexos_04_00_signed.pdf?rlkey=lduuie95adfutj20ofdsiyyl9&dl=1
  La Gomera (ES126), Decreto 102/2023. The plan's memoria is not online (aguasgomera.es was rebuilt without it; the BOC
    annex is the scanned Normativa, with no UDU list). MITECO's follow-up report of the plan (Informe de seguimiento
    2023, Apéndice 1.22) names the 6 UDUs (one per municipality) and gives urban supply by origin (100 % groundwater).
    https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/planificacion-hidrologica/22-GOM_2023.pdf
  El Hierro (ES127), Decreto 86/2023. Memoria, section 3.1.2.2.1, printed pages 142-143: 3 UDUs with % by source.
    https://aguaselhierro.org/descarga/8330/

Where the plan is prose, the units, municipalities and sources are written out below by hand from the text, and the
script checks that each UDU heading and each named source is printed in the downloaded document (it stops otherwise).
Tenerife's fichas and La Gomera's report are parsed.

Writes, into data/raw/plans/canarias_<island>/: meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md), plus the downloaded PDF.

Usage: uv run --with pdfplumber python tools/extract_supply_canarias.py [ISLAND ...]
  ISLAND: gran_canaria fuerteventura lanzarote tenerife la_palma la_gomera el_hierro (default: all)
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

REFERENCE = "data/raw/ine/municipalities_reference.csv"
OUT_ROOT = "data/raw/plans"
SOURCE_TYPES = {"reservoir", "river", "aquifer", "spring", "desalination", "transfer", "network", "reclaimed"}
ROLES = {"main", "backup", "minor"}


# ---------------------------------------------------------------- helpers

def download(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=900) as r, open(path + ".part", "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.rename(path + ".part", path)
    return path


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_reference():
    with open(REFERENCE, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["province_code"] in ("35", "38")]


def ine_key(name):
    """'Orotava, La' -> 'la orotava'; 'Palmas de Gran Canaria, Las' -> 'las palmas de gran canaria'."""
    m = re.match(r"(.+), (El|La|Los|Las)$", name)
    return fold(f"{m.group(2)} {m.group(1)}" if m else name)


def match_municipality(name, province, ref):
    """Exact match on the folded name (article first), else a unique INE name that starts with it
    ('Vilaflor' -> 'Vilaflor de Chasna', 'Santa María de Guía' -> '... de Gran Canaria'). None when not unique."""
    m = re.match(r"(.+?) \((EL|LA|LOS|LAS|El|La|Los|Las)\)$", name.strip())   # 'OROTAVA (LA)'
    key = fold(f"{m.group(2)} {m.group(1)}" if m else name)
    rows = [r for r in ref if r["province_code"] == province]
    hits = [r for r in rows if ine_key(r["official_name"]) == key]
    if not hits:
        hits = [r for r in rows if ine_key(r["official_name"]).startswith(key + " ")]
    return hits[0]["municipality_code"] if len(hits) == 1 else None


def pages_text(pdf_path, first, last):
    """Text of PDF pages first..last (1-based, inclusive) -> list of (page_no, text)."""
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(max(first, 1) - 1, min(last, len(pdf.pages))):
            out.append((i + 1, pdf.pages[i].extract_text() or ""))
    return out


def write_outputs(island, meta, units, muni_rows, sources, unmatched, ref):
    out = os.path.join(OUT_ROOT, f"canarias_{island}")
    codes = {r["municipality_code"] for r in ref}
    unit_codes = {u[0] for u in units}
    # validation
    seen = {}
    for r in muni_rows:
        assert r[0] in codes, (island, r)
        assert r[1] in unit_codes, (island, r)
        seen.setdefault(r[0], []).append(r)
    for s in sources:
        assert s[0] in unit_codes and s[3] in SOURCE_TYPES and s[5] in ROLES, (island, s)
        assert not s[1] or s[1] in codes, (island, s)
    assert len({(r[0], r[1]) for r in muni_rows}) == len(muni_rows), island
    split_no_share = sorted(m for m, rs in seen.items() if len(rs) > 1 and any(r[2] == "" for r in rs))

    def write(name, header, rows):
        with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write("supply_units.csv", ["unit_code", "unit_name"], units)
    write("municipality_supply.csv",
          ["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"], muni_rows)
    write("supply_sources.csv", ["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                                 "water_body_code", "share_pct", "notes"], sources)
    write("unmatched.csv", ["plan_name", "province_hint", "reason"], unmatched)
    by_type = {}
    for s in sources:
        by_type[s[3]] = by_type.get(s[3], 0) + 1
    print(f"{island}: {len(seen)} municipalities, {len(units)} units, {len(muni_rows)} municipality rows, "
          f"{len(sources)} sources {by_type}, {len(unmatched)} unmatched"
          + (f"; in several units without share_pct: {split_no_share}" if split_no_share else ""))


# ---------------------------------------------------------------- islands described in prose

def S(stype, name, role="main", wb="", share="", notes="", muni=None, ev=None):
    """One source as the plan states it. ev: text that must appear in the unit's section (default: the name minus
    'EDAM '/'EDAS '); muni: municipality name when the plan ties the source to one municipality of the unit."""
    return dict(type=stype, name=name, role=role, wb=wb, share=share, notes=notes, muni=muni,
                ev=ev if ev is not None else re.sub(r"^(EDAM|EDAS) ", "", name))


# Gran Canaria groundwater bodies, as named in the Memoria
GC = {"009": ("Medianías Norte", "ES70GC009"), "004": ("Este", "ES70GC004"), "007M": ("Suroeste", "ES70GC007M"),
      "010M": ("Medianías Sur", "ES70GC010M")}


def gc_aq(k, role="main", notes="", muni=None, share=""):
    return S("aquifer", GC[k][0], role, GC[k][1], share, notes, muni, ev=GC[k][1][:9])


PROSE = {
    "gran_canaria": dict(
        basin="ES120", province="35", decree="Decreto 370/2023",
        url="https://aguasgrancanaria.com/pdfs/PlanHidro/ES120_PH_PP-Memoria-completa.pdf",
        file="ES120_PH_PP-Memoria-completa.pdf", window=(175, 200), end="Unidades de Demanda Urbana: Turismo",
        document="Plan Hidrológico de la Demarcación Hidrográfica de Gran Canaria, tercer ciclo 2021-2027 (Decreto "
                 "370/2023), Memoria (marzo 2023), apartado 3.1.2.2.1 Unidades de Demanda Urbana (UDU), pp. 181-192",
        units=[
            ("UDU1", "Gáldar - Agaete", ["Gáldar", "Agaete"], [
                S("desalination", "EDAM Bocabarranco"),
                gc_aq("009", notes="wells in the upper parts of both municipalities, part of their water goes to supply"),
                S("reservoir", "El Vaquero", "minor", notes="Risco de Agaete only", muni="Agaete")]),
            ("UDU2", "Santa María de Guía", ["Santa María de Guía"], [
                S("desalination", "EDAM Roque Prieto"),
                gc_aq("009", "minor", "a few inland settlements")]),
            ("UDU3", "Arucas – Firgas – Moya", ["Arucas", "Firgas", "Moya"], [
                S("desalination", "EDAM Arucas-Moya"),
                gc_aq("009", notes="wells and springs feeding the upper areas")]),
            ("UDU4", "Las Palmas de Gran Canaria – Santa Brígida", ["Las Palmas de Gran Canaria", "Santa Brígida"], [
                S("desalination", "EDAM Las Palmas III", notes="Piedra Santa complex, operated by EMALSA"),
                S("desalination", "EDAM Las Palmas – Telde", ev="Las Palmas – Telde"),
                gc_aq("009", notes="wells in Santa Brígida and Vega de San Mateo")]),
            ("UDU5", "Telde – Valsequillo", ["Telde", "Valsequillo"], [
                S("desalination", "EDAM Telde – Salinetas", ev="Telde – Salinetas"),
                gc_aq("004", notes="wells; a small share according to the plan")]),
            ("UDU6", "Sureste (Agüimes – Ingenio – Santa Lucía)", ["Agüimes", "Ingenio", "Santa Lucía de Tirajana"], [
                S("desalination", "EDAM Mancomunidad del Sureste", ev="Mancomunidad del Sureste"),
                gc_aq("009", "minor", "upper settlements such as Santa Lucía town", muni="Santa Lucía de Tirajana")]),
            ("UDU7", "San Bartolomé de Tirajana", ["San Bartolomé de Tirajana"], [
                S("desalination", "EDAM Maspalomas I", notes="Morro Besudo; coastal zone", ev="Maspalomas I"),
                S("desalination", "EDAM Maspalomas II", notes="Las Burras complex; coastal zone", ev="Maspalomas II"),
                S("desalination", "EDAM Maspalomas III", notes="Las Burras complex; coastal zone", ev="II y III"),
                S("desalination", "EDAM Castillo del Romeral"),
                gc_aq("009", "minor", "uplands (Tunte, Fataga, ...)"),
                gc_aq("010M", "minor", "uplands (Tunte, Fataga, ...)")]),
            ("UDU8", "Mogán", ["Mogán"], [
                S("desalination", "EDAM Aguas Arguineguín", notes="zones Barranco de Arguineguín and Anfi/Aquamarina",
                  ev="Aguas Arguineguín"),
                gc_aq("007M", notes="wells along the barrancos (Arguineguín, Tauro, Taurito, Mogán)"),
                S("reservoir", "Soria", notes="Barranco de Arguineguín zone; the plan says 'possibly'"),
                S("reservoir", "Cuevas de las Niñas", notes="Barranco de Arguineguín zone; the plan says 'possibly'"),
                S("desalination", "EDAM Puerto Rico", notes="Puerto Rico zone"),
                S("desalination", "EDAM Anfi Tauro", notes="Tauro zone"),
                gc_aq("010M", notes="Tauro, Taurito and Mogán zones")]),
            ("UDU9", "La Aldea de San Nicolás", ["La Aldea de San Nicolás"], [
                S("desalination", "EDAM La Aldea de San Nicolás", ev="EDAM La Aldea de San Nicolás"),
                S("reservoir", "Caidero de la Niña", "backup", notes="occasional, upper areas; printed 'Cadeiro'",
                  ev="Cadeiro de la Niña"),
                S("reservoir", "Siberio", "backup", notes="occasional, upper areas"),
                S("reservoir", "El Parradillo", "backup", notes="occasional, upper areas", ev="Parradillo"),
                S("aquifer", "Suroeste", "minor", "ES70GC007M",
                  notes="wells for Tasarte, Casas Blancas and Las Rosas (printed ES70CG007M)", ev="007M-Suroeste")]),
            ("UDU10", "Medianías Suroeste (Tejeda)", ["Tejeda"], [
                gc_aq("010M", share="100", notes="wells, galleries and springs; 'íntegramente' per the plan")]),
            ("UDU11", "Medianías occidentales (Artenara)", ["Artenara"], [
                gc_aq("009"),
                S("reservoir", "Lugarejos"),
                S("reservoir", "Los Pérez"),
                S("reservoir", "La Candelaria", notes="the plan says 'possibly'")]),
            ("UDU12", "Medianías Noreste", ["Vega de San Mateo", "Teror", "Valleseco"], [
                gc_aq("009", notes="wells and, in Valleseco, many springs")]),
        ],
        notes="12 UDUs described in prose (municipalities + 'Origen'); every municipality of the island is in one unit. "
              "UDU4 and UDU5 are named after two municipalities each (Santa Brígida, Valsequillo de Gran Canaria) and "
              "the text describes their supply, though their 'Extensión' line names only Las Palmas de Gran Canaria and "
              "Telde; both are included. Sources the text ties to one zone or municipality carry a note; 'posiblemente' "
              "is kept as a note. Tourist self-supply units (UDUT, hotel desalination plants) are not municipal supply "
              "and are left out."),
    "fuerteventura": dict(
        basin="ES122", province="35", decree="Decreto 139/2024",
        url="https://www.aguasfuerteventura.com/documentos/8_MEMORIA_%20Y_%20ANEJOS.pdf",
        file="8_MEMORIA_Y_ANEJOS.pdf", window=(190, 210), end="Unidades de Demanda Urbana: Turismo",
        document="Plan Hidrológico de la Demarcación Hidrográfica de Fuerteventura, tercer ciclo 2021-2027 (Decreto "
                 "139/2024), Memoria y Anejos, apartado 3.1.2.2.1 Unidades de Demanda Urbana (UDU), pp. 196-202",
        units=[
            ("UDU1", "La Oliva", ["La Oliva"], [
                S("desalination", "EDAM Corralejo", notes="Consorcio de Abastecimiento de Aguas a Fuerteventura (CAAF)")]),
            ("UDU2", "Corralejo", ["La Oliva"], [
                S("desalination", "EDAM SALO-Corralejo", notes="Suministros de Agua La Oliva S.A. (SALOSA)",
                  ev="SALO- Corralejo")]),
            ("UDU3", "Puerto del Rosario – Betancuria", ["Puerto del Rosario", "Betancuria"], [
                S("desalination", "EDAM Puerto del Rosario", notes="CAAF")]),
            ("UDU4", "Antigua", ["Antigua"], [
                S("desalination", "EDAM Montaña Blanca", notes="Empresa Mixta de Aguas de Antigua; Caleta de Fuste and "
                  "Costa de Antigua"),
                S("desalination", "EDAM Puerto del Rosario", notes="CAAF")]),
            ("UDU5", "Gran Tarajal – Tuineje – Pájara", ["Tuineje", "Pájara"], [
                S("desalination", "EDAM Gran Tarajal", notes="CAAF"),
                S("desalination", "EDAM Puerto del Rosario", notes="CAAF"),
                S("desalination", "FPA Tuineje captación Tequital", "minor", "ES70FV003",
                  notes="brackish groundwater desalination, self-supply", ev="Tequital"),
                S("desalination", "EDAS Antonio Cabrera Sanabria", "minor", "ES70FV003",
                  notes="brackish groundwater desalination, self-supply", ev="Antonio cabrera Sanabria")]),
            ("UDU6", "Sur de Tuineje – Centro de Pájara", ["Tuineje", "Pájara"], [
                S("desalination", "EDAM Gran Tarajal", notes="CAAF, through the Tuineje network"),
                S("desalination", "EDAM Puerto del Rosario", notes="CAAF")]),
            ("UDU7", "Península de Jandía", ["Pájara"], [
                S("desalination", "EDAM Morro Jable", notes="Ayuntamiento de Pájara; Morro Jable"),
                S("desalination", "EDAM Cañada del Río", notes="private (Fuertcan S.L.); Costa Calma"),
                S("desalination", "EDAS Vinamar", "minor", "ES70FV004",
                  notes="private brackish groundwater plant, Las Gaviotas development")]),
        ],
        notes="7 UDUs described in prose; supply is seawater desalination (CAAF plants plus municipal and private "
              "ones). La Oliva, Pájara and Tuineje are split between units by area ('salvo núcleo de Corralejo', "
              "'franja septentrional', 'parte central') and the plan gives no population share, so their rows have "
              "an empty share_pct although the municipality appears in more than one unit. UDU3 is named "
              "'Puerto del Rosario – Betancuria' and its text describes Betancuria's supply by the CAAF, though the "
              "'Extensión' line names only Puerto del Rosario; Betancuria is included. Tourist self-supply units "
              "(UDUT) are left out."),
    "lanzarote": dict(
        basin="ES123", province="35", decree="Decreto 110/2024",
        url="https://aguaslanzarote.com/wps/wp-content/uploads/docs/3-normativa/PHL3/ES123_PH_Memoria-Anejos_Diligencia.pdf",
        file="ES123_PH_Memoria-Anejos_Diligencia.pdf", window=(155, 170), end="Unidades de Demanda Urbana: Turismo",
        document="Plan Hidrológico de la Demarcación Hidrográfica de Lanzarote, tercer ciclo 2021-2027 (Decreto "
                 "110/2024), Memoria y Anejos, apartado 3.1.2.2.1 Unidades de Demanda Urbana (UDU), pp. 157-162",
        units=[(c, n, m, [S("desalination", "EDAM Janubio", notes="Consorcio del Agua de Lanzarote, Yaiza"),
                          S("desalination", "EDAM Lanzarote", notes="Consorcio del Agua de Lanzarote, Punta Grande (Arrecife)")])
               for c, n, m in [
                   ("UDU1", "Yaiza", ["Yaiza"]),
                   ("UDU2", "Playa Blanca", ["Yaiza"]),
                   ("UDU3", "Montaña Roja", ["Yaiza"]),
                   ("UDU4", "Tías – Puerto del Carmen", ["Tías"]),
                   ("UDU5", "San Bartolomé – Arrecife – Tahiche", ["San Bartolomé", "Arrecife", "Teguise"]),
                   ("UDU6", "Costa Teguise", ["Teguise"]),
                   ("UDU7", "Teguise – Tinajo interior", ["Teguise", "Tinajo"]),
                   ("UDU8", "La Santa", ["Tinajo"]),
                   ("UDU9", "Famara", ["Teguise"]),
                   ("UDU10", "Haría", ["Haría"]),
                   ("UDU11", "Órzola", ["Haría"]),
                   ("UDU12", "La Graciosa", ["Teguise"])]],
        notes="12 UDUs, delimited by sewerage systems because the whole island (and La Graciosa) drinks desalinated "
              "seawater from one network fed by two plants, EDAM Janubio and EDAM Lanzarote; every unit's 'Origen' "
              "is both. Yaiza, Teguise, Tinajo and Haría are split between units by settlement and the plan gives no "
              "population share, so their rows have an empty share_pct although the municipality appears in more "
              "than one unit. UDU5's 'Tahiche (Tegueste)' is read as Tahíche in Teguise (Tegueste is in Tenerife); "
              "La Graciosa belongs to Teguise. Tourist self-supply units (UDUT, hotel desalination plants) are left out."),
    "la_palma": dict(
        basin="ES125", province="38", decree="Decreto 6/2025",
        url="https://www.dropbox.com/scl/fi/nkrgd339kv5s471ux483u/1.-ES125_PH-Memoria_Anexos_04_00_signed.pdf"
            "?rlkey=lduuie95adfutj20ofdsiyyl9&dl=1",
        file="1.-ES125_PH-Memoria_Anexos_04_00_signed.pdf", window=(145, 160), end="Unidades de Demanda Agraria",
        document="Plan Hidrológico de la Demarcación Hidrográfica de La Palma, tercer ciclo 2021-2027 (Decreto 6/2025), "
                 "Memoria, apartado 3.1.2.2.1 Unidades de Demanda Urbana (UDU), pp. 149-152",
        units=[
            ("UDU1", "Santa Cruz de La Palma", ["Santa Cruz de La Palma"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001"),
                S("aquifer", "Costero", wb="ES70LP002", notes="the plan says 'possibly'", ev="ES70LP002")]),
            ("UDU2", "Breña Alta", ["Breña Alta"], [S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001")]),
            ("UDU3", "Breña Baja", ["Breña Baja"], [S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001")]),
            ("UDU4", "Villa de Mazo - Fuencaliente", ["Villa de Mazo", "Fuencaliente"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001",
                  notes="through the Canal Intermunicipal and the Canal Barlovento – Fuencaliente", ev="ES70LP001")]),
            ("UDU5", "El Paso", ["El Paso"], [S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001")]),
            ("UDU6", "Los Llanos de Aridane – Tazacorte", ["Los Llanos de Aridane", "Tazacorte"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001",
                  notes="through the Trasvase Las Breñas – El Paso and the Canal Garafía – Tijarafe", ev="ES70LP001"),
                S("aquifer", "Complejo Basal", wb="ES70LP003",
                  notes="basal-complex water emerging in the Caldera de Taburiente; body code from the section's "
                        "introduction", ev="complejo basal")]),
            ("UDU7", "Tijarafe – Puntagorda – Garafía", ["Tijarafe", "Puntagorda", "Garafía"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001",
                  notes="through the Canal Garafía – Tijarafe and the Minaderos pipeline", ev="ES70LP001")]),
            ("UDU8", "Barlovento", ["Barlovento"], [S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001")]),
            ("UDU9", "San Andrés y Sauces", ["San Andrés y Sauces"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001", notes="largely springs", ev="ES70LP001")]),
            ("UDU10", "Puntallana", ["Puntallana"], [
                S("aquifer", "Insular – Vertientes", wb="ES70LP001", ev="ES70LP001"),
                S("aquifer", "Costero", wb="ES70LP002", notes="the plan says 'possibly'", ev="ES70LP002")]),
        ],
        notes="10 UDUs; urban supply on La Palma is groundwater, almost all from body ES70LP001 Insular – Vertientes, "
              "carried around the island by the Canal General La Palma I and II and the Canal Intermunicipal (the "
              "units are delimited by sewerage). Body names from the Memoria's water-body chapter. 'Posiblemente' is "
              "kept as a note. The document is the signed Memoria linked from the Consejo Insular de Aguas de La "
              "Palma's page for the plan in force (lapalmaaguas.com), hosted on Dropbox."),
    "el_hierro": dict(
        basin="ES127", province="38", decree="Decreto 86/2023",
        url="https://aguaselhierro.org/descarga/8330/", file="PHIEH_3ciclo_Memoria.pdf", window=(138, 150),
        end="Figura 62",
        document="Plan Hidrológico de la Demarcación Hidrográfica de El Hierro, tercer ciclo 2021-2027 (Decreto 86/2023), "
                 "Memoria, apartado 3.1.2.2.1 Unidades de Demanda Urbana (UDU), pp. 142-143",
        units=[
            ("UDU1", "Valverde", ["Valverde"], [
                S("desalination", "EDAM El Cangrejo", share="88", ev="Cangrejo"),
                S("aquifer", "Valle de El Golfo", wb="ES70EH001", share="10", notes="pozo Los Padrones",
                  ev="Los Padrones"),
                S("aquifer", "Valverde Zona Oriental", wb="ES70EH002", share="2", notes="pozo Tamaduste",
                  ev="Tamaduste")]),
            ("UDU2", "Frontera", ["Frontera"], [
                S("aquifer", "Valle de El Golfo", wb="ES70EH001", share="100", notes="wells Tigaday and Los Padrones",
                  ev="ES70EH001")]),
            ("UDU3", "El Pinar de El Hierro", ["El Pinar de El Hierro"], [
                S("desalination", "EDAM La Restinga", share="100", ev="La Restinga")]),
        ],
        notes="3 UDUs, one per municipality, with shares by source as the text gives them (Valverde: EDAM El Cangrejo "
              "88 %, pozo Los Padrones 10 %, pozo Tamaduste 2 %; Frontera 100 % wells; El Pinar 100 % EDAM La "
              "Restinga). Groundwater body names from the Memoria's water-body chapter (ES70EH001 Acuífero Valle de "
              "El Golfo, ES70EH002 Acuífero Valverde Zona Oriental)."),
}


def heading_re(code):
    n = code[3:]
    return re.compile(rf"^\s*UDU ?{n} ?:", re.M)


def run_prose(island, ref):
    cfg = PROSE[island]
    out = os.path.join(OUT_ROOT, f"canarias_{island}")
    os.makedirs(out, exist_ok=True)
    pdf = download(cfg["url"], os.path.join(out, cfg["file"]))
    pages = pages_text(pdf, *cfg["window"])
    text = "\n".join(f"\n<<PAGE {p}>>\n{t}" for p, t in pages)
    starts = []
    for code, *_ in cfg["units"]:
        m = heading_re(code).search(text)
        if not m:
            sys.exit(f"{island}: heading for {code} not found in PDF pages {cfg['window']}")
        starts.append(m.start())
    end = text.find(cfg["end"], starts[-1])
    bounds = starts[1:] + [end if end > 0 else len(text)]
    units, muni_rows, sources, unmatched, page_of = [], [], [], [], {}
    for (code, name, munis, srcs), a, b in zip(cfg["units"], starts, bounds):
        section = re.sub(r"\s+", " ", text[a:b])
        page_of[code] = re.findall(r"<<PAGE (\d+)>>", text[:a])[-1]
        units.append((code, name))
        mcodes = {}
        for mn in munis:
            mc = match_municipality(mn, cfg["province"], ref)
            if mc:
                mcodes[mn] = mc
                muni_rows.append((mc, code, "", "", ""))
            else:
                unmatched.append((mn, cfg["province"], f"no unique INE match ({code})"))
        for rank, s in enumerate(srcs, 1):
            if fold(s["ev"]) not in fold(section):
                sys.exit(f"{island}: '{s['ev']}' not found in the text of {code}")
            mc = mcodes.get(s["muni"], "") if s["muni"] else ""
            sources.append((code, mc, rank, s["type"], s["name"], s["role"], s["wb"], s["share"], s["notes"]))
    meta = {"plan": f"canarias_{island}", "basin_id": cfg["basin"],
            "source": f"ph-{island.replace('_', '-')}-2021-2027", "plan_cycle": "2021-2027",
            "source_document": cfg["document"], "source_url": cfg["url"],
            "notes": cfg["notes"] + " UDU headings on PDF pages "
                     + ", ".join(f"{c} p.{p}" for c, p in page_of.items()) + "."}
    write_outputs(island, meta, units, muni_rows, sources, unmatched, ref)


# ---------------------------------------------------------------- Tenerife: Normativa Anejo 8 fichas

TF_URL = "https://www.aguastenerife.org/images/pdf/PHT3erCiclo/03%20NORMATIVA_AI_02%20ANEJOS%2008%20UD%20DEMANDA.pdf"
PLANT = re.compile(r"(\d{3,5})-(EDA[MS] .+?) \((\d+)-(EDA[MS])\)")   # 3521-EDAM DE SANTA CRUZ (5-EDAM)


def run_tenerife(ref):
    out = os.path.join(OUT_ROOT, "canarias_tenerife")
    os.makedirs(out, exist_ok=True)
    pdf = download(TF_URL, os.path.join(out, "03_NORMATIVA_AI_02_ANEJOS_08_UD_DEMANDA.pdf"))
    fichas = {}                           # unit code -> dict(name, text, first page)
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages):
            t = page.extract_text() or ""
            m = re.search(r"^(UP\d{4}) (.+?) \d+$", t, re.M)
            if not m or "UNIDADES DE DEMANDA" not in t:
                continue
            f = fichas.setdefault(m.group(1), dict(name=m.group(2).strip(), text="", page=i + 1))
            f["text"] += "\n" + t
    units, muni_rows, sources, unmatched, parsed = [], [], [], [], []
    by_muni = {}
    for code, f in sorted(fichas.items()):
        t = f["text"]
        mm = re.search(r"^Municipio (\d{2}) (.+)$", t, re.M)
        pop = re.search(r"^Total: ([\d.]+) ([\d.]+) ([\d.]+)$", t, re.M)
        o = t[t.index("Origen de los recursos"):]
        o = o[:o.index("Aglomeraciones")] if "Aglomeraciones" in o else o
        flat = re.sub(r"\s+", " ", o.replace("agua:", " "))
        plants = PLANT.findall(flat)
        units.append((code, f["name"]))
        mname = mm.group(2).strip()
        island_code = mm.group(1)
        mc = match_municipality(mname, "38", ref)
        if not mc:
            unmatched.append((mname, "38", f"no unique INE match (unit {code}, ficha p.{f['page']})"))
        parsed.append((code, f, island_code, mname, mc, plants, pop))
    # the municipal service unit UPnn01 fixes which INE municipality the CIATF number nn is
    number = {c[2:4]: mc for c, _, _, _, mc, _, _ in parsed if c.endswith("01") and mc}
    for code, f, island_code, mname, mc, plants, pop in parsed:
        if mc and number.get(island_code) != mc:
            unmatched.append((f"{code} {f['name']}", "38",
                              f"ficha p.{f['page']} gives municipality number {island_code} with name {mname}, "
                              f"which disagree (number {island_code} is unit UP{island_code}01's municipality); not placed"))
            mc = None
        if mc:
            by_muni.setdefault(mc, []).append((code, float(pop.group(1).replace(".", "")) if pop else None))
        for rank, (_, pname, _, kind) in enumerate(plants, 1):
            note = "brackish groundwater desalination" if kind == "EDAS" else ""
            sources.append((code, "", rank, "desalination", pname.strip(), "main", "", "", note))
    for mc, rows in sorted(by_muni.items()):
        total = sum(p or 0 for _, p in rows)
        for code, p in rows:
            share = "" if len(rows) == 1 else (f"{100 * p / total:.1f}" if p is not None and total else "")
            muni_rows.append((mc, code, share, "", ""))
    n_src_units = len({s[0] for s in sources})
    meta = {"plan": "canarias_tenerife", "basin_id": "ES124", "source": "ph-tenerife-2021-2027", "plan_cycle": "2021-2027",
            "source_document": "Plan Hidrológico de la Demarcación Hidrográfica de Tenerife, tercer ciclo 2021-2027 "
                               "(Decreto 372/2023), Normativa, Anejo 8 Unidades de Demanda (fichas UP)",
            "source_url": TF_URL,
            "notes": f"{len(units)} urban-network units (UP: 31 municipal services plus independent managers such as "
                     "Golf del Sur or Ten-Bel); tourist self-supply (UT), industrial, golf and farm units are left out. "
                     "Unit codes and municipality numbers are the CIATF's (municipality number = digits 3-4 of the "
                     "code); municipalities are matched to INE by the name on the ficha. Where a municipality has "
                     "several units, share_pct is each unit's share of the 'Población Estimada' totals of the "
                     "fichas' supply zones (SINAC). Sources are the plants each ficha lists under 'Origen de los "
                     f"recursos' (EDAM seawater, EDAS brackish groundwater; {n_src_units} units list one). The ficha's "
                     "groundwater field ('Masa(s) de agua') is blank in every ficha of this approved version, so "
                     "groundwater (galleries and wells, the main source in most of the island) is not listed; "
                     "reclaimed-water plants (ERA/EDRAR) are left out as they do not feed drinking supply."}
    write_outputs("tenerife", meta, units, muni_rows, sources, unmatched, ref)


# ---------------------------------------------------------------- La Gomera: MITECO follow-up report

LG_URL = "https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/planificacion-hidrologica/22-GOM_2023.pdf"


def run_la_gomera(ref):
    out = os.path.join(OUT_ROOT, "canarias_la_gomera")
    os.makedirs(out, exist_ok=True)
    pdf = download(LG_URL, os.path.join(out, "22-GOM_2023.pdf"))
    with pdfplumber.open(pdf) as doc:
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
    flat = re.sub(r"\s+", " ", text)
    udus = re.findall(r"(ES126-UDU-\d) ([^,()]+?)(?:,| y (?=ES126)|\))", flat.replace("- UDU", "-UDU").replace("ES126- ", "ES126-"))
    block = flat[flat.index("Origen del recurso"):]                 # table 3.4; urban use is its first block
    block = block[:block.index("Total") + 40]
    m = re.search(r"Subterránea ([\d,]+ ){4}([\d,]+).*?Desalinización ([\d,]+ ){4}([\d,]+) Total ([\d,]+ ){4}([\d,]+)",
                  block)
    sub, desal, tot = (float(m.group(k).replace(",", ".")) for k in (2, 4, 6))
    assert len(udus) == 6 and sub == tot and desal == 0, (udus, sub, desal, tot)
    units, muni_rows, sources, unmatched = [], [], [], []
    for code, name in udus:
        name = name.strip()
        units.append((code, name))
        mc = match_municipality(name, "38", ref)
        if mc:
            muni_rows.append((mc, code, "", "", ""))
        else:
            unmatched.append((name, "38", f"no unique INE match ({code})"))
        sources.append((code, "", 1, "aquifer", "", "main", "", "100",
                        f"island urban supply 2022/23: {tot:.2f} hm3, all groundwater (report table 3.4); "
                        "the report names no water body or intake per unit"))
    meta = {"plan": "canarias_la_gomera", "basin_id": "ES126", "source": "ph-la-gomera-2021-2027", "plan_cycle": "2021-2027",
            "source_document": "MITECO, Informe de seguimiento de Planes Hidrológicos y Recursos Hídricos 2023, Apéndice "
                               "1.22 La Gomera (on the Plan Hidrológico Insular de La Gomera, tercer ciclo 2021-2027, "
                               "Decreto 102/2023): note (1) of section 3.6 (UDU list) and table 3.4 (urban supply by origin)",
            "source_url": LG_URL,
            "notes": "The plan's own memoria is not online: aguasgomera.es was rebuilt without the plan documents, and the "
                     "BOC publication of Decreto 102/2023 (BOC 122, 23.6.2023, boc-a-2023-122-2035) carries only the "
                     "scanned Normativa, which has no list of demand units. MITECO's follow-up report names the 6 UDUs "
                     "(ES126-UDU-1 to -6), one per municipality, and gives urban supply by origin: 100 % groundwater, "
                     "no desalination, surface water or reuse. No water body, well or gallery is named per unit."}
    write_outputs("la_gomera", meta, units, muni_rows, sources, unmatched, ref)


def main():
    islands = sys.argv[1:] or ["gran_canaria", "fuerteventura", "lanzarote", "tenerife", "la_palma", "la_gomera",
                               "el_hierro"]
    ref = load_reference()
    for island in islands:
        if island == "tenerife":
            run_tenerife(ref)
        elif island == "la_gomera":
            run_la_gomera(ref)
        else:
            run_prose(island, ref)


if __name__ == "__main__":
    main()
