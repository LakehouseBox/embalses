"""Illes Balears river-basin plan 2022-2027 (ES110): where each municipality's urban supply takes its water.

Sources (Govern de les Illes Balears, Portal de l'Aigua; plan approved by Real Decreto 49/2023, de 24 de enero; the
documents on this page carry "Aprobado por Real Decreto 49/2023" on every page, i.e. the approved version):
  https://www.caib.es/sites/aigua/es/proposta_projecte/
  Memoria, Anexo 5 "Caracterización económica y social de los usos del agua", Tabla 3 "Población de derecho y plazas
  turísticas con indicación de la masa de agua subterránea que abastece a la población urbana" (municipality ->
  groundwater body codes; '*' = access to the ABAQUA bulk network, fed by desalination and by the groundwater bodies
  1806M2 Sa Costera, 1808M1 Estremera and 1811M2 Llubí):
    https://www.caib.es/sites/aigua/ca/proposta_projecte/archivopub.do?ctrl=MCRST259ZI414959&id=414959
  Memoria, Anexo 3 "Consumos de agua y asignaciones" (code -> name of the 87 groundwater bodies, abastecimiento table):
    https://www.caib.es/sites/aigua/ca/proposta_projecte/archivopub.do?ctrl=MCRST259ZI414958&id=414958
  Memoria (section 5.1, demand units A-J: EMAYA's reservoirs Cúber and Gorg Blau for Palma; IDAM Ciutadella for the
  south of Ciutadella; the three Eivissa plants feeding the island's bulk network; Es Ca Marí for Formentera;
  Puigpunyent and Deià buying ABAQUA water occasionally without a connection):
    https://www.caib.es/sites/aigua/ca/proposta_projecte/archivopub.do?ctrl=MCRST259ZI414955&id=414955

Units: the plan's 10 demand units (UD A-J) group groundwater bodies, and several municipalities draw from more than
one, so one unit per municipality is used here (unit_code = INE code, unit_name = municipality name).

Writes, into OUT_DIR (default data/raw/plans/baleares): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md), plus the downloaded PDFs.

Usage: uv run --with pdfplumber python tools/extract_supply_baleares.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

BASE = "https://www.caib.es/sites/aigua/ca/proposta_projecte/archivopub.do?ctrl=MCRST259ZI{0}&id={0}"
ANEXO5, ANEXO3, MEMORIA = BASE.format(414959), BASE.format(414958), BASE.format(414955)
REFERENCE = "data/raw/ine/municipalities_reference.csv"
MASUB = re.compile(r"\d{4}M\d")

ABAQUA = "ABAQUA (red en alta del Govern de les Illes Balears)"
# Sources the Memoria (section 5.1) ties to particular municipalities, by INE code:
# (source_type, source_name, role, water_body_code, notes)
EXTRA = {
    "07040": [("reservoir", "Cúber", "main", "ES110MSPF11017209M",
               "EMAYA's reservoirs in the Serra de Tramuntana, about 8 hm3/year together; Memoria 5.1 A.5"),
              ("reservoir", "Gorg Blau", "main", "ES110MSPF11010705M",
               "EMAYA's reservoirs in the Serra de Tramuntana, about 8 hm3/year together; Memoria 5.1 A.5")],
    "07015": [("desalination", "IDAM Ciutadella", "minor", "",
               "in service since 2019, serves the south of the municipality; Memoria 5.1 B.1")],
}
EIVISSA_IDAM = [("desalination", n, "main", "", "feeds the island's bulk network, which reaches practically every "
                 "urban area of Eivissa; Memoria 5.1 C.1") for n in ("IDAM Eivissa", "IDAM Sant Antoni", "IDAM Santa Eulària")]
FORMENTERA_IDAM = [("desalination", "IDAM Ca Marí", "main", "",
                    "water distributed to the whole island; Memoria 5.1 D.1")]
NO_CONNECTION = {"07018": "Deià", "07045": "Puigpunyent"}   # marked '*' but 'compran puntualmente agua de esta red'


def download(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


def read_table3(path):
    """[(name as printed, abaqua flag, [masub codes])] from Anexo 5 Tabla 3; continuation rows have no name."""
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if "MASub que" not in (page.extract_text() or ""):
                continue
            for table in page.extract_tables():
                for row in table:
                    if len(row) < 6 or (row[1] or "").startswith("MUNICIPIO"):
                        continue
                    # Formentera, alone in its island block, comes out merged into the island column
                    name = re.sub(r"\s+", " ", row[1] or (row[0] if row[2] else "") or "").strip()
                    codes = MASUB.findall(row[5] or "")
                    if name:
                        out.append([name.rstrip("*").strip(), name.endswith("*"), codes])
                    elif out:
                        out[-1][2].extend(codes)
    return out


def read_masub_names(path):
    """code -> groundwater body name, from the Anexo 3 abastecimiento table ('1801M1  Coll Andritxol  0,00 ...')."""
    names = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                m = re.match(r"\s*(\d{4}M\d)\s+(\D+?)\s+\d+,\d+", line)
                if m and m.group(1) not in names:
                    names[m.group(1)] = m.group(2).strip()
    return names


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = s.replace("’", "'")
    return re.sub(r"[^A-Z]", "", s)


def ine_keys(name):
    """INE official names put the article last ('Pobla, Sa'); bilingual names use '/'."""
    keys = set()
    for part in name.split("/"):
        keys.add(norm(part))
        m = re.match(r"(.+), (\w+'?)$", part.strip())
        if m:
            keys.add(norm(m.group(2) + " " + m.group(1)))
    return keys


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/baleares"
    os.makedirs(out_dir, exist_ok=True)
    a5 = download(ANEXO5, os.path.join(out_dir, "PHIB2227_Memoria_Anexo5.pdf"))
    a3 = download(ANEXO3, os.path.join(out_dir, "PHIB2227_Memoria_Anexo3.pdf"))
    download(MEMORIA, os.path.join(out_dir, "PHIB2227_Memoria.pdf"))
    rows = read_table3(a5)
    masub = read_masub_names(a3)

    ref = {}
    with open(REFERENCE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["province_code"] == "07":
                for k in ine_keys(r["official_name"]):
                    ref[k] = (r["municipality_code"], r["official_name"])
    # spellings in Tabla 3 that differ from the INE name (one candidate each in the province, checked by hand)
    alias = {"LLORETDEVISTAALEGRE": "LLORETDEVISTALEGRE", "SANTLLORENCDESCARDESSAR": "SANTLLORENCDESCARDASSAR",
             "VILLAFRANCADEBONANY": "VILAFRANCADEBONANY", "CIUTADELLA": "CIUTADELLADEMENORCA"}

    matched, unmatched = [], []
    for name, abaqua, codes in rows:
        k = alias.get(norm(name), norm(name))
        if k in ref:
            matched.append((ref[k][0], ref[k][1], name, abaqua, codes))
        else:
            unmatched.append((name, "07", "no INE name match in province 07"))

    units, munis, sources = [], [], []
    for code, official, printed, abaqua, codes in sorted(matched):
        units.append((code, official))
        munis.append((code, code, "", ("MASub que abastece: " + ", ".join(codes)) + (" (*)" if abaqua else ""), ""))
        rank = 0

        def add(stype, sname, role, wb, notes):
            nonlocal rank
            rank += 1
            sources.append((code, "", rank, stype, sname, role, wb, "", notes))

        for c in dict.fromkeys(codes):
            add("aquifer", masub.get(c, ""), "main", c, "" if c in masub else "groundwater body name not found in Anexo 3")
        if abaqua:
            if code in NO_CONNECTION:
                add("network", ABAQUA, "backup", "", "buys water from the network occasionally, no connection; Memoria 5.1 A.7")
            else:
                add("network", ABAQUA, "main", "",
                    "bulk network fed by desalination and, in Mallorca, by groundwater bodies 1806M2, 1808M1, 1811M2; "
                    "Anexo 5 Tabla 3")
        extra = EXTRA.get(code, [])
        if any(c.startswith("20") for c in codes) and abaqua:
            extra = extra + EIVISSA_IDAM
        if any(c.startswith("21") for c in codes) and abaqua:
            extra = extra + FORMENTERA_IDAM
        for e in extra:
            add(*e)

    def write(name, header, data):
        with open(os.path.join(out_dir, name), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(data)

    write("supply_units.csv", ["unit_code", "unit_name"], units)
    write("municipality_supply.csv", ["municipality_code", "unit_code", "share_pct", "intake_description",
                                      "additional_intakes"], munis)
    write("supply_sources.csv", ["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                                 "water_body_code", "share_pct", "notes"], sources)
    write("unmatched.csv", ["plan_name", "province_hint", "reason"], unmatched)

    missing_names = sorted({c for _, _, cs in rows for c in cs} - set(masub))
    meta = {
        "plan": "baleares", "basin_id": "ES110", "source": "ph-illes-balears-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("Plan Hidrológico de la Demarcación Hidrográfica de las Illes Balears 2022-2027 (Real "
                            "Decreto 49/2023), Memoria Anexo 5 Tabla 3 (municipality -> groundwater bodies, ABAQUA "
                            "access); groundwater body names from Memoria Anexo 3; reservoirs and desalination plants "
                            "from Memoria section 5.1"),
        "source_url": ANEXO5,
        "notes": ("One supply unit per municipality (unit_code = INE code, unit_name = INE name): the plan's 10 demand "
                  "units (UD A Menorca ... J Formentera) are groupings of groundwater bodies, and many municipalities "
                  "draw from bodies in two of them, so they cannot be used as a municipality -> unit key. Sources are "
                  "the groundwater bodies of Tabla 3 (water_body_code = the plan's short code, e.g. 1811M2) in the "
                  "plan's order; '*' municipalities also get the ABAQUA bulk network (desalination plus three "
                  "Mallorca groundwater bodies), as backup for Deià and Puigpunyent, which the Memoria says buy its "
                  "water occasionally without a connection. Desalination plants are listed per municipality only "
                  "where the Memoria ties them: IDAM Ciutadella (south of Ciutadella), the three Eivissa plants "
                  "(island-wide bulk network, for the '*' Eivissa municipalities), IDAM Ca Marí (Formentera). The "
                  "Mallorca plants (Bahía de Palma, Andratx, Alcúdia) feed the ABAQUA network as a whole and are not "
                  "attributed to municipalities. Palma also gets EMAYA's reservoirs Cúber and Gorg Blau. No shares are "
                  "given in the plan."
                  + (f" Groundwater codes without a name: {', '.join(missing_names)}." if missing_names else "")),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(rows)} rows in Tabla 3, {len(matched)} matched, {len(unmatched)} unmatched, {len(sources)} sources,"
          f" {len(masub)} groundwater body names -> {out_dir}")


if __name__ == "__main__":
    main()
