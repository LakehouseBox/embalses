"""Ceuta and Melilla river-basin plans 2022-2027: where each city's tap water comes from.

Both districts are a single municipality (Ceuta 51001, Melilla 52001) with a single supply system, described in prose
in Anejo 3 "Usos y demandas", section 3.1.1 "Sistemas de abastecimiento":
  Ceuta   https://www.chguadalquivir.es/documents/10182/2564324/PHCeuta_ANEJO3.pdf/fea15aba-e5b6-fdd1-b104-64176d25501b
  Melilla https://www.chguadalquivir.es/documents/10182/2565404/PHMelilla_ANEJO3.pdf/bb00b8ce-377e-f2ca-e9cd-fd53de9ac78a
There are no tables to parse, so the rows below are written by hand. Each source carries a verbatim quote from the
plan; the script downloads the PDF, extracts its text and refuses to write anything if a quote is not found, so every
row stays traceable to the document.

The plans give no supply-unit codes; we use CE-UDU01 and ML-UDU01 (said in meta.json).

Writes meta.json, supply_units.csv, municipality_supply.csv and supply_sources.csv into data/raw/plans/ceuta and
data/raw/plans/melilla (or OUT_ROOT/ceuta, OUT_ROOT/melilla), in the format of tools/supply_plans_format.md.

Usage (from the repo root): uv run --with pdfplumber python tools/extract_supply_ceuta_melilla.py [OUT_ROOT]
"""
import csv
import json
import os
import re
import sys
import urllib.request

import pdfplumber

PLANS = {
    "ceuta": dict(
        basin_id="ES150", municipality="51001", unit=("CE-UDU01", "Abastecimiento a la ciudad de Ceuta"),
        url="https://www.chguadalquivir.es/documents/10182/2564324/PHCeuta_ANEJO3.pdf/fea15aba-e5b6-fdd1-b104-64176d25501b",
        file="PHCeuta_ANEJO3.pdf",
        intake="En los últimos años, como término medio, la ciudad de Ceuta se abastece en un 10% desde la ETAP y en "
               "un 90% desde la planta desalinizadora.",
        # (source_type, source_name, role, share_pct, notes, quote that must appear in the plan text)
        sources=[
            ("desalination", "IDAM Playa Benítez", "main", "90", "seawater desalination, 30,000 m3/day; share is the "
             "average of recent years", "Situada en Playa Benítez con una producción de"),
            ("reservoir", "El Renegado", "main", "", "intake of the ETAP (35,000 m3/day); the ETAP supplies about 10% "
             "on average", "La captación está en el embalse de El Renegado"),
            ("reservoir", "El Infierno", "main", "", "feeds El Renegado by a transfer between the two reservoirs",
             "El embalse El Infierno con una capacidad de 0,60 hm3"),
            ("spring", "Belionex", "minor", "", "also called Benzú; outside the district (Bel-lionex), feeds El Renegado; "
             "current use far below the historical 2,000-7,000 m3/day", "Manantiales de Belionex o de Benzú"),
            ("river", "arroyo de las Bombas", "minor", "", "surface-water gallery, volumes reduced in recent years",
             "Galería de captación de aguas superficiales en el arroyo de las Bombas"),
        ],
        notes="Section 3.1.1 of Anejo 3. Shares: the plan's average split (90% desalination, 10% ETAP); the ETAP's "
              "share among El Renegado, El Infierno, the Belionex springs and the arroyo de las Bombas gallery is not "
              "given. Tanker ships ('buque tanque') are an exceptional drought alternative and are not listed as a "
              "source. Unit code CE-UDU01 is ours (the plan has no UDU codes).",
    ),
    "melilla": dict(
        basin_id="ES160", municipality="52001", unit=("ML-UDU01", "Abastecimiento a la ciudad de Melilla"),
        url="https://www.chguadalquivir.es/documents/10182/2565404/PHMelilla_ANEJO3.pdf/bb00b8ce-377e-f2ca-e9cd-fd53de9ac78a",
        file="PHMelilla_ANEJO3.pdf",
        intake="En la demarcación hidrográfica de Melilla las fuentes de suministro son tres: 1. Desalinizadora de "
               "agua de mar. 2. Captación del río de Oro. 3. Captaciones subterráneas. Complementándose la dotación "
               "con los manantiales de Trara y Yasinen",
        sources=[
            ("desalination", "IDAM de Melilla", "main", "", "seawater desalination at the Acantilado de Aguadú, "
             "20,000 m3/day (being enlarged to 29,490 m3/day)", "La producción desde la planta desalinizadora es de"),
            ("river", "río de Oro", "main", "", "intake and two galleries in the riverbed (subálveo), pumped to the "
             "Balsa de Las Adelfas or the ETAP; with the wells about 10,000 m3/day", "Captación del río de Oro"),
            ("aquifer", "Acuífero Calizo", "main", "", "city wells and boreholes, treated in the desalting plant "
             "(desalobradora); the plan lists the district's three groundwater bodies", "Acuífero Calizo"),
            ("aquifer", "Acuífero Volcánico", "main", "", "city wells and boreholes (see Acuífero Calizo)", "Acuífero Volcánico"),
            ("aquifer", "Acuífero Aluvial", "main", "", "city wells and boreholes (see Acuífero Calizo)", "Acuífero Aluvial"),
            ("spring", "Trara", "minor", "", "complements the supply", "manantiales de Trara y Yasinen"),
            ("spring", "Yasinen", "minor", "", "complements the supply", "manantiales de Trara y Yasinen"),
        ],
        notes="Section 3.1.1 of Anejo 3. No percentage split is given: desalination produces 20,000 m3/day and the "
              "río de Oro intakes plus groundwater about 10,000 m3/day. Tanker ships are an emergency option and are "
              "not listed as a source; reclaimed water from the tertiary WWTP serves a golf course and parks, not the "
              "drinking-water network. Unit code ML-UDU01 is ours (the plan has no UDU codes).",
    ),
}


def download(url, out_dir, name):
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    return path


def flat(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans"
    for plan, p in PLANS.items():
        out_dir = os.path.join(root, plan)
        os.makedirs(out_dir, exist_ok=True)
        with pdfplumber.open(download(p["url"], out_dir, p["file"])) as pdf:
            text = flat(" ".join(page.extract_text() or "" for page in pdf.pages))
        missing = [q for q in [p["intake"][:60]] + [s[5] for s in p["sources"]] if flat(q) not in text]
        if missing:
            sys.exit(f"{plan}: quotes not found in {p['file']}: {missing}")
        unit_code, unit_name = p["unit"]
        meta = {"plan": plan, "basin_id": p["basin_id"], "source": f"ph-{plan}-2022-2027", "plan_cycle": "2022-2027",
                "source_document": f"Plan Hidrológico de la Demarcación Hidrográfica de {plan.capitalize()} "
                                   "2022–2027, Anejo 3 Usos y demandas, 3.1.1 Sistemas de abastecimiento",
                "source_url": p["url"], "notes": p["notes"]}
        with open(os.path.join(out_dir, "meta.json"), "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["unit_code", "unit_name"])
            w.writerow([unit_code, unit_name])
        with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
            w.writerow([p["municipality"], unit_code, "", p["intake"], ""])
        with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                        "water_body_code", "share_pct", "notes"])
            for rank, (kind, name, role, share, notes, _quote) in enumerate(p["sources"], 1):
                w.writerow([unit_code, "", rank, kind, name, role, "", share, notes])
        print(f"{plan}: 1 municipality, 1 supply unit, {len(p['sources'])} sources -> {out_dir}")


if __name__ == "__main__":
    main()
