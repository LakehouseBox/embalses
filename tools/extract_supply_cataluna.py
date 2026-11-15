"""Cuencas Internas de Cataluña (Districte de conca fluvial de Catalunya, ES100): which supply unit serves each
municipality, and where that unit takes its water.

Sources (Agència Catalana de l'Aigua, ACA):
  Open data, dataset i5n8-43cw "Estat de sequera per unitats d'explotació i municipis a les Conques Internes de
  Catalunya" (municipality -> one of the 18 unitats d'explotació, as a time series of drought-state changes):
    https://analisi.transparenciacatalunya.cat/resource/i5n8-43cw.csv
  Pla especial d'actuació en situació d'alerta i eventual sequera (PES), approved by Acord GOV/1/2020, consolidated
  text of April 2024 (section 3.3-3.6: the 18 units and the resources each depends on; section 4: desalination,
  reuse and the coordinated use of aquifers):
    https://aca.gencat.cat/web/.content/30_Plans_i_programes/30_Pla_sequera/documents-PES/PES-consolidat-abril-2024.pdf
  Pla de gestió del districte de conca fluvial de Catalunya 2022-2027, Memòria, section 3.4 (management systems Muga,
  Fluvià, Ter-Llobregat, Sud; the Ebre transfer of the Consorci d'Aigües de Tarragona, the Siurana-Riudecanyes transfer):
    https://info.aca.gencat.cat/ca/aca/informacio/geco/plans-programes/PDG/CA/01-00-Pla-de-gestio-2022-27.pdf

The PdG uses the same 18 units as its demand units ("Unitats de Demanda (adoptant els àmbits de les Unitats
d'Explotació del vigent Pla de Sequera)", Taula 16). The units are defined by their source, so the sources per unit are
transcribed by hand below from the PES and PdG text (no table to parse); each row cites its section in notes.

Writes, into OUT_DIR (default data/raw/plans/cataluna): meta.json, supply_units.csv, municipality_supply.csv,
supply_sources.csv (format: tools/supply_plans_format.md), plus the downloaded CSV and PDFs.

Usage: python3 tools/extract_supply_cataluna.py [OUT_DIR]
"""
import csv
import json
import os
import sys
import urllib.request

SOCRATA = "https://analisi.transparenciacatalunya.cat/resource/i5n8-43cw.csv?$limit=1000000&$order=data_canvi_estat_sequera"
PES = "https://aca.gencat.cat/web/.content/30_Plans_i_programes/30_Pla_sequera/documents-PES/PES-consolidat-abril-2024.pdf"
PDG = "https://info.aca.gencat.cat/ca/aca/informacio/geco/plans-programes/PDG/CA/01-00-Pla-de-gestio-2022-27.pdf"

# Unit names as the PES writes them (sections 3.4-3.6); the open data spells some differently ("Embassament Ter- Llobregat").
UNITS = {
    "01": "Anoia-Gaià",
    "02": "Aqüífer Carme-Capellades",
    "03": "Aqüífer Fluvià-Muga",
    "04": "Aqüífer Plioquaternari de Tarragona",
    "05": "Aqüífer del Baix Ter",
    "06": "Capçalera del Llobregat",
    "07": "Capçalera del Ter",
    "08": "Consorci d'Aigües de Tarragona",
    "09": "Embassament de Darnius-Boadella",
    "10": "Embassaments del Llobregat",
    "11": "Riudecanyes",
    "12": "Embassaments del Ter",
    "13": "Embassaments Ter-Llobregat",
    "14": "Empordà",
    "15": "Estany de Banyoles",
    "16": "Mig Llobregat",
    "17": "Prades-Llaberia",
    "18": "Serralada Transversal",
}

RAIN = "PES 3.3/3.6: unit depends on minor aquifers not monitored continuously or on intakes in unregulated rivers"
# unit -> [(source_type, source_name, role, notes, municipality_codes or None)]
SOURCES = {
    "01": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "02": [("aquifer", "Carme-Capellades", "main", "PES 3.5.2", None)],
    "03": [("aquifer", "Fluvià-Muga", "main", "fluviodeltaic aquifer, extraction zone at Peralada; PES 3.5.1", None),
           ("reservoir", "Darnius-Boadella", "backup",
            "surface water through the Consorci de la Costa Brava network, from the Alerta state; only the Mancomunitat "
            "d'Aigües de Garriguella, Vilajuïga, Pau i Palau-Saverdera is connected; PES 4.2.5",
            ["17077", "17223", "17128", "17120"])],
    "04": [("aquifer", "Plioquaternari de Tarragona", "main",
            "low use since the Consorci d'Aigües de Tarragona network came into service; PES 3.5.4", None)],
    "05": [("aquifer", "Baix Ter", "main", "alluvial aquifers of the Baix Ter, shallow and deep; PES 3.5.3", None),
           ("aquifer", "Daró", "main", "alluvial aquifer of the Daró; PES 3.5.3", None)],
    "06": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "07": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "08": [("network", "Consorci d'Aigües de Tarragona", "main",
            "regional network; supplies about 45 of the area's 64 hm3/year urban demand; PdG 3.4.6.1", None),
           ("transfer", "Minitransvasament de l'Ebre", "main",
            "Ebre water taken at Camp Redó and treated at l'Ampolla, concession 3.856 m3/s (Llei 18/1981); PdG 3.4.6.1", None),
           ("aquifer", None, "main", "numerous dispersed local groundwater sources, e.g. Camp de Tarragona; PdG 3.4.6.1", None),
           ("reservoir", "Riudecanyes", "minor", "part of the flows from Riudecanyes and the Siurana transfer; PdG 3.4.6.1", None),
           ("reservoir", "Siurana", "minor", "Ebro basin, through the Siurana-Riudecanyes transfer; PdG 3.4.6.1", None)],
    "09": [("reservoir", "Darnius-Boadella", "main",
            "Figueres and the networks connected to it, and intakes downstream on the Muga; PES 3.4/3.4.1", None)],
    "10": [("reservoir", "La Baells", "main", "PES 3.4.3", None),
           ("reservoir", "La Llosa del Cavall", "main", "PES 3.4.3", None),
           ("reservoir", "Sant Ponç", "main", "PES 3.4.3", None)],
    "11": [("reservoir", "Riudecanyes", "main", "PES 3.4.4", None),
           ("reservoir", "Siurana", "main", "Ebro basin, through the Siurana-Riudecanyes transfer; PES 3.4.4", None)],
    "12": [("reservoir", "Sau", "main", "directly or through intakes downstream (e.g. Girona); PES 3.4/3.4.3", None),
           ("reservoir", "Susqueda", "main", "PES 3.4.3", None)],
    "13": [("network", "Aigües Ter-Llobregat (ATL)", "main", "Xarxa d'Abastament Ter-Llobregat; PES 3.4, PdG 3.4.5.1", None),
           ("reservoir", "Sau", "main", "Ter reservoirs; PES 3.4.2", None),
           ("reservoir", "Susqueda", "main", "Ter reservoirs; PES 3.4.2", None),
           ("reservoir", "La Baells", "main", "Llobregat reservoirs; PES 3.4.2", None),
           ("reservoir", "La Llosa del Cavall", "main", "Llobregat reservoirs; PES 3.4.2", None),
           ("reservoir", "Sant Ponç", "main", "Llobregat reservoirs; PES 3.4.2", None),
           ("desalination", "ITAM Llobregat", "main", "minimum output while reserves are high, more in drought; PES 4.1.1", None),
           ("desalination", "ITAM Tordera", "main",
            "connected to the Cardedeu treatment plant; serves the Baixa Tordera; PES 3.3, 4.1.1", None),
           ("aquifer", "Vall Baixa i Delta del Llobregat", "main", "wells of the Sant Joan Despí plant; PES 4.2.1", None),
           ("aquifer", "Vall Baixa i Delta de la Tordera", "main", "PES 4.2.2", None),
           ("aquifer", "Cubeta d'Abrera", "minor", "intakes of Abrera, Terrassa, Martorell; PES 4.2.6", None),
           ("aquifer", "Cubeta de la Llagosta", "backup", "wells little used today, recovered for droughts; PES 4.2.7", None),
           ("aquifer", "Vall Baixa i Delta del Besòs", "backup", "wells little used today, recovered for droughts; PES 4.2.7", None),
           ("reclaimed", "ERA del Prat de Llobregat", "backup",
            "reclaimed water returned to the Llobregat upstream of the Sant Joan Despí intake; PES 4.1.2", None)],
    "14": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "15": [("river", "Estany de Banyoles", "main",
            "natural lake (Estany de Banyoles), type 'river' for lack of a lake type; PES 3.5.5", None)],
    "16": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "17": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
    "18": [("aquifer", None, "main", RAIN, None), ("river", None, "main", RAIN, None)],
}


def download(url, path):
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
    return path


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/cataluna"
    os.makedirs(out_dir, exist_ok=True)
    seq = download(SOCRATA, os.path.join(out_dir, "i5n8-43cw.csv"))
    download(PES, os.path.join(out_dir, "PES-consolidat-abril-2024.pdf"))
    download(PDG, os.path.join(out_dir, "01-00-Pla-de-gestio-2022-27.pdf"))

    # Latest record per municipality (Idescat 6-digit code; the first 5 digits are the INE code). Renamed or merged
    # municipalities (Calonge i Sant Antoni, Castell d'Aro, Platja d'Aro i s'Agaró, Bigues i Riells del Fai, Brunyola
    # i Sant Martí Sapresa) keep their code, so the latest record carries the current name.
    latest, names = {}, {}
    with open(seq, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = r["codi_municipi"].zfill(6)[:5]
            key = (r["data_canvi_estat_sequera"], r["codi_unitat_explotaci"])
            if code not in latest or key[0] >= latest[code][0]:
                latest[code] = key
            names[r["codi_unitat_explotaci"]] = r["unitat_explotaci"]
    unknown = sorted(set(names) - set(UNITS))
    if unknown:
        sys.exit(f"units in the open data not described here: {unknown}")

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for code, name in UNITS.items():
            w.writerow([code, name])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for code, (_d, unit) in sorted(latest.items(), key=lambda kv: (kv[1][1], kv[0])):
            w.writerow([code, unit, "", "", ""])
    n = 0
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        for unit, rows in SOURCES.items():
            for rank, (stype, name, role, notes, munis) in enumerate(rows, 1):
                for m in (munis or [""]):
                    assert not m or latest.get(m, ("", ""))[1] == unit, (m, unit)
                    w.writerow([unit, m, rank, stype, name or "", role, "", "", notes])
                    n += 1

    meta = {
        "plan": "cataluna", "basin_id": "ES100", "source": "pg-dcfc-2022-2027", "plan_cycle": "2022-2027",
        "source_document": ("ACA open data i5n8-43cw (municipalities by unitat d'explotació); Pla especial d'actuació "
                            "en situació d'alerta i eventual sequera (PES, Acord GOV/1/2020, consolidated April 2024), "
                            "sections 3.3-3.6 and 4; Pla de gestió del DCFC 2022-2027, Memòria 3.4 and Taula 16"),
        "source_url": "https://analisi.transparenciacatalunya.cat/resource/i5n8-43cw.csv",
        "notes": ("Units are the 18 unitats d'explotació of the drought plan, which the 2022-2027 Pla de gestió also uses "
                  "as its demand units; codes 01-18 are the ACA's own (open data). Each municipality is in exactly "
                  "one unit (latest record of the drought-state series); the PES assigns a municipality to the unit "
                  "of the regional network it is connected to even when that is not its main ordinary source (PES "
                  "3.3). Sources per unit are transcribed from the PES/PdG text (cited in notes); no shares are "
                  "given there. The seven rainfall-index units (Anoia-Gaià, Capçalera del Llobregat, Capçalera del "
                  "Ter, Empordà, Mig Llobregat, Prades-Llaberia, Serralada Transversal) only get generic unnamed "
                  "aquifer and river sources, as the PES describes them. Reservoir names in Catalan as in the PES. "
                  "El Pasteral (Ter diversion dam) and the Foix desalination plant (planned) are not listed: the "
                  "PES does not name them as sources. Coverage: municipalities of the Catalan internal basins in "
                  "the ACA dataset (Catalan municipalities in the Ebro and Júcar basins are not in it)."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{len(latest)} municipalities, {len(UNITS)} units, {n} sources -> {out_dir}")


if __name__ == "__main__":
    main()
