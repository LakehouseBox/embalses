"""Andalusian intra-community river-basin plans 2022-2027: which supply unit serves each municipality, and where it
takes its water. One tool, three plans (three output folders):

  cma                  ES060 Cuencas Mediterráneas Andaluzas, Anejo VI "Sistemas de explotación y balances"
                       (demand table and supply balance of each of the 15 subsystems; UDU codes are INE codes)
  guadalete_barbate    ES063 Guadalete y Barbate, Anejo III Tabla 46 (UDU -> municipalities) + Anejo VI balances
  tinto_odiel_piedras  ES064 Tinto, Odiel y Piedras, Anejo III Tabla 47 (UDU -> municipalities) + Anejo VI balances

The plans give, per unit, hm3/yr by origin (regulated surface water, run-of-river, groundwater, reclaimed, desalinated,
transfers). Each non-zero origin becomes one source with share_pct = origin / total. Names of reservoirs, plants and
transfers come from the plan's prose (regulation infrastructure, "recursos de otras procedencias", urban demand
sections); every named source carries the printed page it comes from in notes. Where the prose does not tie a
source to the unit, the source stays unnamed.

Writes, per plan, into data/raw/plans/<plan>/ (format: tools/supply_plans_format.md):
  meta.json, supply_units.csv, municipality_supply.csv, supply_sources.csv, unmatched.csv (only when needed)

Usage (from the repo root): uv run --with pdfplumber python tools/extract_supply_andalucia.py [cma|guadalete_barbate|tinto_odiel_piedras ...]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

PLANS_DIR = "data/raw/plans"
INE_REF = "data/raw/ine/municipalities_reference.csv"
UA = {"User-Agent": "embalses-open-data/0.1"}
JUNTA = "https://www.juntadeandalucia.es/medioambiente/portal/documents/20151"

CMA_URL = JUNTA + "/107104154/PH-CMA-Anejo-VI.pdf/38962535-3ee4-3673-565f-451db74f991e"
GB_III_URL = JUNTA + "/107000647/anejo-III-usos-demandas.pdf/249860f0-dcfa-7070-89e6-e45e9c4f8e56"
GB_VI_URL = JUNTA + "/107000820/anejo-VI-asignacion-reserva-recursos-usos.pdf/d541bffd-6454-424e-e25c-411906a3bdb1"
TOP_III_URL = JUNTA + "/106994151/anejo-III-usos-demandas.pdf/91c010c8-6fcc-a96e-2d24-e48732f514d0"
TOP_VI_URL = JUNTA + "/106894043/anejo-VI-asignacion-reserva-recursos-usos.pdf/f46bd611-5c8f-82ae-9fe9-f5d331aeca33"

# Balance columns, in the plans' order, and the source type each one becomes.
COLUMNS = ["regulated", "run_of_river", "groundwater", "reclaimed", "desalinated", "transfer"]
COLUMN_TYPE = {"regulated": "reservoir", "run_of_river": "river", "groundwater": "aquifer",
               "reclaimed": "reclaimed", "desalinated": "desalination", "transfer": "transfer"}
COLUMN_EN = {"regulated": "regulated surface water", "run_of_river": "run-of-river surface water",
             "groundwater": "groundwater", "reclaimed": "reclaimed water", "desalinated": "desalinated water",
             "transfer": "transfers"}


# ---------------------------------------------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------------------------------------------

def download(out_dir, name, url):
    path = os.path.join(out_dir, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=600) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    return path


def pdf_pages(path):
    with pdfplumber.open(path) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def printed_page(text):
    m = re.search(r"Pág\.\s*(\d+)\s*de\s*\d+", text)
    return int(m.group(1)) if m else None


def find_page(pages, phrase, start=0):
    """Printed page number ('Pág. N') of the first page (from index start) whose text contains phrase."""
    flat = re.sub(r"\s+", " ", phrase)
    for i in range(start, len(pages)):
        if flat in re.sub(r"\s+", " ", pages[i]):
            return printed_page(pages[i]) or i + 1
    raise SystemExit(f"phrase not found in the plan: {phrase!r}")


def num(s):
    return float(s.replace(".", "").replace(",", ".")) if s else 0.0


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s)


def name_variants(name):
    """'Barrios (Los)' / 'Barrios, Los' / 'Los Barrios' -> the same keys; 'A/B' -> both halves."""
    out = {name}
    m = re.match(r"^(.*?)\s*\((El|La|Los|Las|L')\)$", name) or re.match(r"^(.*?),\s*(El|La|Los|Las|L')$", name)
    if m:
        out |= {f"{m.group(2)} {m.group(1)}", m.group(1)}
    for part in name.split("/"):
        out.add(part.strip())
    return {norm(v) for v in out}


class Ine:
    def __init__(self, path=INE_REF):
        with open(path, newline="", encoding="utf-8") as f:
            self.rows = {r["municipality_code"]: r for r in csv.DictReader(f)}
        self.by_name = {}
        for code, r in self.rows.items():
            for k in name_variants(r["official_name"]):
                self.by_name.setdefault((r["province_code"], k), set()).add(code)

    def match(self, name, provinces):
        hits = set()
        for p in provinces:
            for k in name_variants(name):
                hits |= self.by_name.get((p, k), set())
        return hits.pop() if len(hits) == 1 else None

    def name(self, code):
        return self.rows[code]["official_name"] if code in self.rows else None


def shares_to_sources(unit_code, amounts, named, total=None):
    """amounts: {column: hm3}; named: {column: [(source_type, name, role, water_body_code, note), ...]}.
    Returns source rows for one unit, in the plan's column order."""
    total = total if total is not None else sum(amounts.values())
    rows = []
    for col in COLUMNS:
        v = amounts.get(col, 0.0)
        if v <= 0:
            continue
        pct = round(100 * v / total, 1) if total else None
        srcs = named.get(col) or [(COLUMN_TYPE[col], "", "main", "", "")]
        mains = [s for s in srcs if s[2] == "main"]
        for kind, name, role, wb, note in srcs:
            share = pct if (role == "main" and len(mains) == 1) else None
            extra = ""
            if role == "main" and len(mains) > 1:
                extra = f"{COLUMN_EN[col]} together {pct:g}% of supply (plan balance), not split by source"
            if kind != COLUMN_TYPE[col] and role == "main":
                extra = "; ".join(x for x in [extra, f"booked as {COLUMN_EN[col]} in the plan balance"] if x)
            rows.append(dict(unit_code=unit_code, municipality_code="", source_type=kind, source_name=name,
                             role=role, water_body_code=wb, share_pct="" if share is None else f"{share:g}",
                             notes="; ".join(x for x in [note, extra] if x)))
    return rows


def write_plan(out_dir, meta, units, munis, sources, unmatched, ine):
    os.makedirs(out_dir, exist_ok=True)
    # validation
    allowed_types = set(COLUMN_TYPE.values()) | {"spring", "network"}
    unit_codes = [u[0] for u in units]
    assert len(unit_codes) == len(set(unit_codes)), "duplicate unit codes"
    seen = {}
    for m in munis:
        assert m["municipality_code"] in ine.rows, m
        assert m["unit_code"] in unit_codes, m
        seen.setdefault(m["municipality_code"], []).append(m)
    for code, ms in seen.items():
        if len(ms) > 1:
            assert all(x["share_pct"] != "" for x in ms), f"{code} in several units without share_pct"
            assert len({x["unit_code"] for x in ms}) == len(ms), f"{code} twice in one unit"
    rank = {}
    for s in sources:
        assert s["unit_code"] in unit_codes, s
        assert s["source_type"] in allowed_types, s
        assert s["role"] in ("main", "backup", "minor"), s
        assert not s["share_pct"] or 0 <= float(s["share_pct"]) <= 100, s
        key = (s["unit_code"], s["municipality_code"])
        rank[key] = rank.get(key, 0) + 1
        s["source_rank"] = rank[key]
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        w.writerows(units)
    cols = ["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"]
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for m in munis:
            w.writerow({c: m.get(c, "") for c in cols})
    cols = ["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role", "water_body_code",
            "share_pct", "notes"]
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in sources:
            w.writerow({c: s.get(c, "") for c in cols})
    upath = os.path.join(out_dir, "unmatched.csv")
    if unmatched:
        with open(upath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["plan_name", "province_hint", "reason"])
            w.writerows(unmatched)
    elif os.path.exists(upath):
        os.remove(upath)
    by_type = {}
    for s in sources:
        by_type[s["source_type"]] = by_type.get(s["source_type"], 0) + 1
    print(f"{meta['plan']}: {len(seen)} municipalities, {len(units)} units, {len(sources)} sources {by_type}, "
          f"{len(unmatched)} unmatched -> {out_dir}")


# ---------------------------------------------------------------------------------------------------------------
# ES060 Cuencas Mediterráneas Andaluzas
# ---------------------------------------------------------------------------------------------------------------

NUM = r"(\d+,\d{2})"
CMA_UDU = re.compile(r"^UDU\s+(\d{5}(?:-[a-z])?)\s+(.*?)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + "$")
CMA_BAL = re.compile(r"^(.*?)\s*" + r"\s+".join([NUM] * 7) + "$")
CMA_SUB = re.compile(r"^4\.\d+\.\d+\s+SUBSISTEMA\s+([IV]+-\d)")


def cma_read(pages):
    """UDUs (code, name, current demand, subsystem) and the current-situation supply balance row of each."""
    lines = []
    for i, t in enumerate(pages):
        if i < 15:                                   # table of contents
            continue
        lines += [(i, l.strip()) for l in t.split("\n")]
    udus, order, balances, sub_totals = {}, {}, {}, {}
    sub, buf = None, None
    for k, (i, l) in enumerate(lines):
        m = CMA_SUB.match(l)
        if m:
            sub = m.group(1)
        m = CMA_UDU.match(l)
        if m and sub not in balances:
            udus[m.group(1)] = dict(code=m.group(1), name=m.group(2), demand=num(m.group(3)), sub=sub,
                                    page=printed_page(pages[i]))
            order.setdefault(sub, []).append(m.group(1))
        m = re.match(r"^Total Ss[ -]([IV]+-\d)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + "$", l)
        if m and m.group(1) not in sub_totals and sub not in balances:
            sub_totals[m.group(1)] = num(m.group(2))
        if re.match(r"^4\.\d+\.\d+\.6\.1\s+DEMANDA DE ABASTECIMIENTO", l):
            buf = []
        if buf is not None:
            m = CMA_BAL.match(l)
            if m:
                buf.append(dict(prefix=m.group(1), prev=lines[k - 1][1], next=lines[k + 1][1],
                                nums=[num(x) for x in m.groups()[1:]], page=printed_page(pages[i])))
            if l.startswith("Balance del abastecimiento en situación actual"):
                balances[sub] = [r for r in buf if not r["prefix"].startswith("Total ")]
                buf = None
    # Balance rows carry names only (sometimes wrapped over three lines): match them to the subsystem's UDUs.
    for s, codes in order.items():
        left = list(codes)
        for r in balances.get(s, []):
            cands = [r["prefix"], f"{r['prev']} {r['prefix']} {r['next']}", f"{r['prev']} {r['prefix']}",
                     f"{r['prefix']} {r['next']}"]
            hit = next((u for c in cands for u in left if norm(udus[u]["name"]) == norm(c)), None)
            if hit is None:
                same = [u for u in left if abs(udus[u]["demand"] - r["nums"][0]) < 0.005]
                hit = same[0] if len(same) == 1 else None
            if hit is None:
                raise SystemExit(f"balance row not matched in {s}: {r}")
            left.remove(hit)
            udus[hit]["balance"] = r
        if left:
            raise SystemExit(f"UDUs without a balance row in {s}: {left}")
    return udus, order, sub_totals


def cma_named_sources(pages, udus):
    """Named sources per UDU code and balance column, from the subsystem prose. Returns {code: {column: [...]}}."""
    def pg(phrase):
        return find_page(pages, phrase, 15)

    def src(kind, name, role="main", wb="", why=""):
        return (kind, name, role, wb, why)

    p_i1 = pg("En el subsistema I-1 se localizan los Embalses de Charco Redondo y Guadarranque")
    p_bujeo = pg("manantial de El Bujeo")
    p_i2 = pg("Este subsistema recibe recursos hídricos procedentes del vecino subsistema I-1 para")
    p_conc = pg("En el sistema I-3 se localiza el Embalse de La Concepción")
    p_marb = pg("Instalación Desaladora de Agua Marina (IDAM) de Marbella")
    p_gh = pg("este embalse se utiliza para el abastecimiento a la ciudad de Málaga")
    p_cas = pg("utilizado como fuente de abastecimiento de refuerzo a la ciudad de Málaga")
    p_vin_mal = pg("complementaria de suministro del abastecimiento de la ciudad de Málaga")
    p_tot = pg("para el abastecimiento de Totalán")
    p_mol = pg("recibe 2,52 hm3 para el abastecimiento de Mollina")
    p_vin = pg("abastecimiento a la Mancomunidad de municipios de la Costa del Sol Oriental")
    p_rules = pg("que corresponden al abastecimiento de Almuñécar")
    p_bez = pg("Abastecimiento a la Mancomunidad de municipios de la Costa Tropical (junto a Rules)")
    p_gual = pg("0,36 hm³ para abastecimiento de Gualchos")
    p_cont = pg("captación del Portichuelo de Cástaras, procedente del río Trevélez")
    p_murt = pg("0,07 hm³ para abastecimiento de Murtas y Turón")
    p_dal = pg("recursos desalados en la IDAM del Campo de Dalías")
    p_alm = pg("4,91 hm3 de agua proveniente de la IDAM de Almería")
    p_nij = pg("de recursos desalados de la desaladora de Carboneras para regadío y")
    p_car = pg("El subsistema dispone de los recursos desalados en la IDAM de Carboneras")
    p_gal = pg("abastecimientos del sistema GALASA (Antas, Arboleas, Cuevas del Almanzora, Huércal-Overa,")
    p_neg = pg("El trasvase Negratín-Almanzora, que fue autorizado")
    p_ts = pg("para regadíos en el Valle del Almanzora y hasta 10 hm3 para abastecimiento de poblaciones")

    by_sub = {
        "I-1": {"regulated": [src("reservoir", "Charco Redondo", why=f"Anejo VI p. {p_i1}: supplies the Mancomunidad del Campo de Gibraltar"),
                              src("reservoir", "Guadarranque", why=f"Anejo VI p. {p_i1}: supplies the Mancomunidad del Campo de Gibraltar")]},
        "I-3": {"regulated": [src("reservoir", "La Concepción", why=f"Anejo VI p. {p_conc}: supplies the Mancomunidad de la Costa del Sol Occidental; fed by diversions from the Guadaiza, Guadalmina and Guadalmansa")],
                "desalinated": [src("desalination", "IDAM de Marbella", why=f"Anejo VI p. {p_marb}")]},
        "II-1": {"regulated": [src("reservoir", "La Viñuela", why=f"Anejo VI p. {p_vin}: supplies the Mancomunidad de la Costa del Sol Oriental-Axarquía")]},
        "III-2": {"regulated": [src("reservoir", "Béznar", why=f"Anejo VI p. {p_bez}: Béznar-Rules system, the subsystem's only regulation"),
                                src("reservoir", "Rules", why=f"Anejo VI p. {p_bez}: Béznar-Rules system, the subsystem's only regulation")]},
        "III-3": {"regulated": [src("river", "río Trevélez", why=f"Anejo VI p. {p_cont}: Contraviesa supply, intake at the Portichuelo de Cástaras (azud de Cástaras), stored in the depósito de la Contraviesa")]},
        "III-4": {"desalinated": [src("desalination", "IDAM del Campo de Dalías", why=f"Anejo VI p. {p_dal}")]},
        "IV-1": {"desalinated": [src("desalination", "IDAM de Almería", why=f"Anejo VI p. {p_alm}")]},
        "IV-2": {"desalinated": [src("desalination", "IDAM de Carboneras", why=f"Anejo VI p. {p_nij}")]},
        "V-1": {"desalinated": [src("desalination", "IDAM de Carboneras", why=f"Anejo VI p. {p_car}")]},
        "V-2": {"desalinated": [src("desalination", "IDAM de Carboneras", why=f"Anejo VI p. {p_gal}: GALASA system and Albox")],
                "transfer": [src("transfer", "Trasvase Negratín-Almanzora", why=f"Anejo VI p. {p_neg}: for urban supply incl. the middle and upper Almanzora"),
                             src("transfer", "Trasvase Tajo-Segura", why=f"Anejo VI p. {p_ts}: up to 10 hm3/yr for urban supply in the Almanzora")]},
    }
    by_udu = {
        # Algeciras' transfer is the El Bujeo spring in the neighbouring Barbate basin.
        "11004": {"transfer": [src("spring", "El Bujeo", why=f"Anejo VI p. {p_bujeo}: temporary diversion from the El Bujeo spring in the Barbate basin (Guadalete-Barbate district)")]},
        # 'recibe recursos ... del vecino subsistema I-1 para abastecimiento de [Jimena de] la Frontera'
        "11021": {"regulated": [src("reservoir", "Charco Redondo", why=f"Anejo VI p. {p_i2}: subsystem I-2 receives water from subsystem I-1 'para abastecimiento de la Frontera' (sentence truncated in the plan; Jimena is the only I-2 unit with regulated water)"),
                                src("reservoir", "Guadarranque", why=f"Anejo VI p. {p_i2}: as above")]},
        "29067": {"regulated": [src("reservoir", "Guadalhorce", why=f"Anejo VI p. {p_gh}"),
                                src("reservoir", "Guadalteba", why=f"Anejo VI p. {p_gh}: same functions as Guadalhorce"),
                                src("reservoir", "Conde de Guadalhorce", why=f"Anejo VI p. {p_gh}"),
                                src("reservoir", "Casasola", "backup", why=f"Anejo VI p. {p_cas}: 'abastecimiento de refuerzo'"),
                                src("reservoir", "El Limonero", "backup", why=f"Anejo VI p. {p_cas}: 'abastecimiento de refuerzo'"),
                                src("reservoir", "La Viñuela", "backup", why=f"Anejo VI p. {p_vin_mal}: complementary source through a reversible pipe")]},
        "29092": {"regulated": [src("reservoir", "La Viñuela", why=f"Anejo VI p. {p_tot}: 0.01 hm3 from La Viñuela (subsystem II-1)")]},
        "29072": {"groundwater": [src("aquifer", "Fuente de Piedra", wb="ES060MSBT060.034", why=f"Anejo VI p. {p_mol}: from the Fuente de Piedra groundwater body in subsystem I-5")]},
        "18093": {"regulated": [src("reservoir", "Béznar", why=f"Anejo VI p. {p_gual}: 0.36 hm3 from the Béznar-Rules system for Gualchos"),
                                src("reservoir", "Rules", why=f"Anejo VI p. {p_gual}: as above")]},
        "18141": {"regulated": [src("river", "río Trevélez", why=f"Anejo VI p. {p_murt}: 0.07 hm3 derived at the azud de Cástaras for Murtas and Turón")]},
        "18181": {"regulated": [src("river", "río Trevélez", why=f"Anejo VI p. {p_murt}: 0.07 hm3 derived at the azud de Cástaras for Murtas and Turón")]},
        "18017": {"regulated": [src("reservoir", "Rules", why=f"Anejo VI p. {p_rules}: 3.29 hm3 regulated in Rules for Almuñécar")]},
    }
    out = {}
    for code, u in udus.items():
        named = dict(by_sub.get(u["sub"], {}))
        named.update(by_udu.get(code[:5], {}))
        out[code] = named
    return out


def run_cma(ine):
    out_dir = os.path.join(PLANS_DIR, "cma")
    os.makedirs(out_dir, exist_ok=True)
    pages = pdf_pages(download(out_dir, "PH-CMA-Anejo-VI.pdf", CMA_URL))
    udus, order, sub_totals = cma_read(pages)
    named = cma_named_sources(pages, udus)
    units, munis, sources, unmatched, notes = [], [], [], [], []
    split = {}
    for code in udus:
        split.setdefault(code[:5], []).append(code)
    for sub, codes in order.items():
        for code in codes:
            u = udus[code]
            unit_code = f"UDU {code}"
            units.append((unit_code, u["name"]))
            ine_code = code[:5]
            plan_name = re.sub(r"\s*\(inc\..*\)$", "", u["name"])
            if ine_code not in ine.rows or (ine.match(plan_name, [ine_code[:2]]) not in (ine_code, None)
                                             and len(split[ine_code]) == 1):
                found = ine.match(plan_name, [ine_code[:2]])
                if not found:
                    unmatched.append((u["name"], ine_code[:2], f"UDU code {code} is not an INE code and the name does not match"))
                    continue
                notes.append(f"UDU {code} {u['name']} is INE {found}")
                ine_code = found
            share = ""
            if len(split[code[:5]]) > 1:   # San Roque: split between UDU 11033-a and 11033-b, shared by demand
                tot = sum(udus[c]["demand"] for c in split[code[:5]])
                share = f"{round(100 * u['demand'] / tot, 1):g}"
            munis.append(dict(municipality_code=ine_code, unit_code=unit_code, share_pct=share))
            b = u["balance"]["nums"]
            amounts = dict(zip(COLUMNS, b[1:]))
            # share over the sum of the origins: the plan rounds to 0.01 hm3, so 'Total' and the parts disagree
            # slightly in small units (e.g. 0.03 = 0.01 + 0.03), and units with a deficit sum below 'Total'
            sources += shares_to_sources(unit_code, amounts, named[code])
    # Compare with the plan's subsystem totals.
    for sub, codes in order.items():
        s = sum(udus[c]["demand"] for c in codes)
        if abs(s - sub_totals.get(sub, -1)) > 0.05:
            print(f"  warning: subsystem {sub} UDU demand sum {s:.2f} vs plan total {sub_totals.get(sub)}")
    total = sum(u["demand"] for u in udus.values())
    meta = {
        "plan": "cma", "basin_id": "ES060", "source": "ph-cma-2022-2027", "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica de las Cuencas Mediterráneas Andaluzas "
                           "2022–2027, Anejo VI Sistemas de explotación y balances: demand tables ('Demanda urbana "
                           "para el horizonte actual, 2027 y 2039') and 'Balance del abastecimiento en situación "
                           "actual' of each subsystem",
        "source_url": CMA_URL,
        "notes": (f"{len(udus)} UDUs in 15 subsystems, current demand {total:.2f} hm3/yr. Each UDU is one municipality "
                  "and its code is the INE code (exceptions: " + "; ".join(notes) + "; San Roque is split into UDU "
                  "11033-a San Roque and 11033-b Sotogrande, share_pct from their current demand; 'Zafarraya (inc. "
                  "Ventas)' also covers Ventas de Zafarraya, a locality of Alhama de Granada, which is not added). "
                  "Sources: one row per non-zero origin in the current-situation balance, share_pct = origin / "
                  "sum of origins (the plan rounds to 0.01 hm3, so shares in very small units are coarse). Reservoirs, desalination plants and transfers are named from the subsystem prose "
                  "(page cited in notes); groundwater and run-of-river water stay unnamed except where the text "
                  "names them for a unit. Where several named reservoirs share the regulated volume, share_pct is "
                  "left empty and the note gives the combined share. 'Desalobradora El Atabal' (Málaga) is listed "
                  "in Anejo III but Anejo VI's balance shows no desalinated water for Málaga, so it is not added. "
                  "Groundwater/run-of-river shares in subsystems with deficits may not add to 100.")
    }
    write_plan(out_dir, meta, units, munis, sources, unmatched, ine)


# ---------------------------------------------------------------------------------------------------------------
# ES063 Guadalete y Barbate
# ---------------------------------------------------------------------------------------------------------------

# Anejo III Tabla 46 (pp. 106-107): code, UDU, municipalities [(plan name, province, share_pct)].
GB_UDUS = [
    ("1", "ZG Cuartillos", [("Chipiona", "11", ""), ("Jerez de la Frontera", "11", "93"),
                            ("El Puerto de Santa María", "11", "20"), ("Rota", "11", ""),
                            ("Sanlúcar de Barrameda", "11", ""), ("Trebujena", "11", "")]),
    ("2", "ZG Montañés", [("Cádiz", "11", ""), ("Conil de la Frontera", "11", ""), ("Chiclana de la Frontera", "11", ""),
                          ("El Puerto de Santa María", "11", "80"), ("Puerto Real", "11", ""), ("San Fernando", "11", "")]),
    ("3", "ZG Vejer-Barbate", [("Vejer de la Frontera", "11", ""), ("Barbate", "11", "")]),
    ("4", "Alcalá de los Gazules", [("Alcalá de los Gazules", "11", "")]),
    ("5", "Algar", [("Algar", "11", "")]),
    ("6", "San José del Valle", [("San José del Valle", "11", "")]),
    ("7", "Medina-Paterna", [("Medina-Sidonia", "11", ""), ("Paterna de Rivera", "11", "")]),
    ("8.a", "Tarifa", [("Tarifa", "11", "T")]),
    ("8.b", "Atlanterra", [("Tarifa", "11", "A")]),
    ("9", "Benalup", [("Benalup-Casas Viejas", "11", "")]),
    ("10", "Setenil-Alcalá del Valle", [("Alcalá del Valle", "11", ""), ("Setenil de las Bodegas", "11", "")]),
    ("11", "Olvera-Torre Alháquime", [("Olvera", "11", ""), ("Torre Alháquime", "11", "")]),
    ("12", "Algodonales-Coripe", [("Algodonales", "11", ""), ("Coripe", "41", "")]),
    ("13", "Grazalema-Prado del Rey", [("Grazalema", "11", ""), ("Prado del Rey", "11", ""), ("Zahara de la Sierra", "11", ""),
                                       ("El Gastor", "11", ""), ("Villaluenga del Rosario", "11", ""), ("Ubrique", "11", ""),
                                       ("Benaocaz", "11", ""), ("El Bosque", "11", "")]),
    ("14", "Arcos-Espera-Bornos", [("Villamartín", "11", ""), ("Espera", "11", ""), ("Bornos", "11", ""),
                                   ("Arcos de la Frontera", "11", "")]),
    ("15", "Puerto Serrano", [("Puerto Serrano", "11", "")]),
    ("16", "Pruna", [("Pruna", "41", "")]),
    ("17", "Jerez desde Tempul", [("Jerez de la Frontera", "11", "7")]),
]
GB_ALIASES = {"Zahara de la Sierra": "Zahara", "Torre Alháquime": "Torre Alháquime"}

# Anejo VI Tabla 15 (SEG) and Tabla 47 (SEB), current situation: total, regulated, run-of-river, groundwater, reclaimed.
GB_BALANCE = {
    "1": (38.66, 37.66, 0, 0, 1.00), "2": (43.39, 43.39, 0, 0, 0), "3": (3.37, 3.22, 0, 0.15, 0),
    "4": (0.50, 0.50, 0, 0, 0), "5": (0.17, 0.17, 0, 0, 0), "6": (0.40, 0, 0, 0.40, 0), "7": (1.56, 1.56, 0, 0, 0),
    "8.a": (2.45, 1.92, 0, 0.53, 0), "8.b": (0.70, 0, 0, 0.70, 0), "9": (0.63, 0.63, 0, 0, 0),
    "10": (0.72, 0, 0, 0.72, 0), "11": (0.69, 0, 0, 0.69, 0), "12": (0.89, 0, 0, 0.89, 0), "13": (3.69, 0, 0, 3.69, 0),
    "14": (4.83, 0, 0, 4.83, 0), "15": (0.61, 0, 0, 0.61, 0), "16": (0.25, 0, 0.25, 0, 0), "17": (1.35, 0, 0, 1.35, 0),
}
GB_BALANCE_ROWS = {   # how each row is printed in the balance tables (checked against the PDF text)
    "1": "ZG Cuartillo 38,66 37,66", "2": "ZG Montañés 43,39 43,39", "3": "Vejer-Barbate 3,37 3,22 0,15",
    "4": "Alcalá Gazules 0,50 0,50", "5": "Algar 0,17 0,17", "6": "S. José del Valle 0,40 0,40",
    "7": "Medina-Paterna 1,56 1,56", "8.a": "Tarifa 2,45 1,92 0,53", "8.b": "Atlanterra 0,70 0,70",
    "9": "Benalup 0,63 0,63", "10": "0,72 0,72", "11": "0,69 0,69", "12": "0,89 0,89", "13": "3,69 3,69",
    "14": "4,83 4,83", "15": "Puerto Serrano 0,61 0,61", "16": "Pruna 0,25 0,25", "17": "1,35 1,35",
}


def gb_named(p):
    zg = [("reservoir", "Los Hurones", "main", "", f"Anejo VI p. {p['zg']}: Zona Gaditana supplied from Guadalcacín and Hurones; Hurones is taken first (p. {p['rules']})"),
          ("reservoir", "Guadalcacín", "main", "", f"Anejo VI p. {p['zg']}")]
    guadiaro = ("transfer", "Trasvase Guadiaro-Majaceite", "main", "", f"Anejo III p. {p['infra']}: reaches Los Hurones through the Buitreras tunnel; urban supply only (Anejo VI p. {p['rules']})")
    zone = [("reservoir", "Los Hurones", "main", "", f"Anejo III p. {p['zones']}: Zona Gaditana (Tabla 6) is supplied from Hurones and Guadalcacín"),
            ("reservoir", "Guadalcacín", "main", "", f"Anejo III p. {p['zones']}: as above")]
    aq = lambda name, wb, role="main", why="": ("aquifer", name, role, wb, why)
    return {
        "1": {"regulated": zg + [guadiaro], "reclaimed": [("reclaimed", "", "main", "", f"Anejo VI p. {p['zg_dem']}: parks and gardens irrigation, not in the model")]},
        "2": {"regulated": zg + [guadiaro]},
        "3": {"regulated": [("network", "Consorcio de Aguas de la Zona Gaditana", "main", "", f"Anejo VI p. {p['vejer']}: 'recursos regulados de la zona gaditana (SEG)'")],
              "groundwater": [aq("", "", why=f"Anejo VI p. {p['vejer']}: local groundwater")]},
        "5": {"regulated": zone},
        "6": {"groundwater": [aq("Sierra de las Cabras", "ES063MSBT000620070", why=f"Anejo III p. {p['infra']}: bombeo de Sierra de Cabras")]},
        "7": {"regulated": zone},
        "8.a": {"regulated": [("reservoir", "Almodóvar", "main", "", f"Anejo VI p. {p['tarifa']}")],
                "groundwater": [("aquifer", "", "main", "", f"Anejo VI p. {p['tarifa']}: own groundwater and local springs")]},
        "8.b": {"groundwater": [aq("", "", why=f"Anejo VI p. {p['tarifa']}: local groundwater; joins the Consorcio de Aguas de la Zona Gaditana in 2027")]},
        "10": {"groundwater": [aq("Setenil", "ES063MSBT000620010", why=f"Anejo III p. {p['infra']}: bombeo de Setenil")]},
        "11": {"groundwater": [aq("Setenil", "ES063MSBT000620010", why=f"Anejo VI p. {p['rules']}: takes first from Setenil, then Sierra de Líjar"),
                               aq("Sierra de Líjar", "ES063MSBT000620030", "backup", f"Anejo VI p. {p['rules']}")]},
        "12": {"groundwater": [aq("Sierra de Líjar", "ES063MSBT000620030", why=f"Anejo III p. {p['infra']}: bombeo de Líjar")]},
        "13": {"groundwater": [aq("Sierra de Grazalema-Prado del Rey", "ES063MSBT000620040", why=f"Anejo III p. {p['infra2']}: bombeos de Grazalema")]},
        "14": {"groundwater": [aq("Arcos de la Frontera-Villamartín", "ES063MSBT000620050", why=f"Anejo III p. {p['infra2']}: bombeo de Arcos de la Frontera; moves to the Consorcio de Aguas de la Zona Gaditana by 2027")]},
        "15": {"groundwater": [aq("Sierra de Grazalema-Prado del Rey", "ES063MSBT000620040", why=f"Anejo VI p. {p['rules']}: as a general rule"),
                               aq("Arcos de la Frontera-Villamartín", "ES063MSBT000620050", "backup", f"Anejo VI p. {p['rules']}: possible alternative")]},
        "16": {"run_of_river": [aq("Setenil", "ES063MSBT000620010", why=f"Anejo III p. {p['infra']}: bombeo de Setenil supplies Pruna")]},
        "17": {"groundwater": [("spring", "Tempul", "main", "ES063MSBT000620070", f"Anejo VI p. {p['zg']}: manantial del Tempul in the Sierra de las Cabras aquifer")]},
    }


def run_gb(ine):
    out_dir = os.path.join(PLANS_DIR, "guadalete_barbate")
    os.makedirs(out_dir, exist_ok=True)
    p3 = pdf_pages(download(out_dir, "anejo-III-usos-demandas.pdf", GB_III_URL))
    p6 = pdf_pages(download(out_dir, "anejo-VI-asignacion-reserva-recursos-usos.pdf", GB_VI_URL))
    t46 = find_page(p3, "se ha considerado que el 7% del T.M. de Jerez de la")
    flat6 = re.sub(r"\s+", " ", "\n".join(p6))
    for code, row in GB_BALANCE_ROWS.items():   # the hand-copied balances must be in the PDF
        assert row in flat6, f"balance row not found: {row}"
    p = dict(infra=find_page(p3, "Hay que destacar, el bombeo de Setenil"),
             infra2=find_page(p3, "los bombeos de Grazalema"),
             zones=find_page(p3, "Guadalcacín y trasvase"),
             zg=find_page(p6, "manantial del Tempul, localizado en el acuífero de Sierra de las Cabras"),
             zg_dem=find_page(p6, "corresponde a recursos regenerados utilizados en el riego de parques"),
             rules=find_page(p6, "La Unidad de demanda Olvera-Torre-Alhaquime toma prioritariamente"),
             vejer=find_page(p6, "La otra demanda es la UDU Vejer-Barbate"),
             tarifa=find_page(p6, "abastece en los tres horizontes considerados del embalse de Almodóvar"))
    named = gb_named(p)
    units, munis, sources, unmatched = [], [], [], []
    tarifa = {"T": GB_BALANCE["8.a"][0], "A": GB_BALANCE["8.b"][0]}
    for code, uname, members in GB_UDUS:
        units.append((code, uname))
        for name, prov, share in members:
            mcode = ine.match(GB_ALIASES.get(name, name), [prov])
            if not mcode:
                unmatched.append((name, prov, "no INE match"))
                continue
            if share in tarifa:   # Tarifa town vs the Atlanterra estate: split by current demand
                share = f"{round(100 * tarifa[share] / sum(tarifa.values()), 1):g}"
            munis.append(dict(municipality_code=mcode, unit_code=code, share_pct=share))
        tot, reg, flu, sub, reu = GB_BALANCE[code]
        sources += shares_to_sources(code, dict(regulated=reg, run_of_river=flu, groundwater=sub, reclaimed=reu),
                                     named.get(code, {}))
    meta = {
        "plan": "guadalete_barbate", "basin_id": "ES063", "source": "ph-guadalete-barbate-2022-2027",
        "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Guadalete y Barbate 2022–2027, Anejo III "
                           f"Usos y demandas, Tabla 46 (p. {t46}); Anejo VI Asignación y reserva de recursos, Tabla 5, "
                           "Tabla 15 and Tabla 47 (current-situation supply balances)",
        "source_url": GB_III_URL,
        "source_url_balances": GB_VI_URL,
        "notes": ("18 UDUs as in Anejo III Tabla 46 (codes 1-17 with 8.a/8.b as printed). Splits from the plan: Jerez "
                  "de la Frontera 93% ZG Cuartillos / 7% Jerez desde Tempul, El Puerto de Santa María 20% Cuartillos / "
                  "80% Montañés; Tarifa town (8.a) vs the Atlanterra estate (8.b) split by current demand (2.45 / 0.70 "
                  "hm3). Sanlúcar de Barrameda and Trebujena (Guadalquivir district) and Coripe and Pruna (Sevilla) "
                  "are included because the plan places them in these units. Sources from the current-situation "
                  "balance (share_pct = origin / total). Alcalá de los Gazules and Benalup take regulated surface "
                  "water from a reservoir the plan does not name. Algar and Medina-Paterna are named Hurones and "
                  "Guadalcacín from the zone table (Anejo III Tabla 6, Zona Gaditana), not from a unit-level "
                  "statement. Pruna's 0.25 hm3 is booked as run-of-river in the balance but Anejo III says Pruna "
                  "is supplied by the Setenil pumping; the source is recorded as the Setenil aquifer.")
    }
    write_plan(out_dir, meta, units, munis, sources, unmatched, ine)


# ---------------------------------------------------------------------------------------------------------------
# ES064 Tinto, Odiel y Piedras
# ---------------------------------------------------------------------------------------------------------------

# Anejo III Tabla 47 (pp. 104-105): code, UDU, municipalities [(plan name, province)]
TOP_UDUS = [
    ("1", "Mancomunidad Condado TOP", [("La Palma del Condado", "21"), ("Bonares", "21"), ("Lucena del Puerto", "21"),
                                       ("Niebla", "21"), ("Villalba del Alcor", "21"), ("Villarrasa", "21")]),
    ("2", "ETAP Riotinto", [("Berrocal", "21"), ("Campofrío", "21"), ("El Campillo", "21"), ("La Granada de Riotinto", "21"),
                            ("Minas de Riotinto", "21"), ("El Madroño", "41"), ("Zalamea la Real", "21"), ("Nerva", "21")]),
    ("3", "ETAP San Silvestre", [("San Silvestre de Guzmán", "21"), ("Villablanca", "21")]),
    ("4", "ETAP Lepe", [("Lepe", "21"), ("Cartaya", "21"), ("Ayamonte", "21"), ("Isla Cristina", "21")]),
    ("5", "ETAP Aljaraque", [("Aljaraque", "21"), ("Punta Umbría", "21"), ("San Bartolomé de la Torre", "21"), ("Gibraleón", "21")]),
    ("6", "ETAP Tinto-Palos", [("Moguer", "21"), ("San Juan del Puerto", "21"), ("Palos de la Frontera", "21"), ("Beas", "21"),
                               ("Trigueros", "21")]),
    ("7", "ETAP Huelva", [("Huelva", "21")]),
    ("8", "Valverde del Camino", [("Valverde del Camino", "21")]),
    ("9", "Sierra de Huelva", [("Alájar", "21"), ("Almonaster la Real", "21"), ("Aracena", "21"), ("Higuera de la Sierra", "21"),
                               ("Linares de la Sierra", "21"), ("Santa Ana la Real", "21")]),
    ("10", "Pomarao", [("Pomarao", "PT")]),
    ("11", "ETAP Andévalo", [("Alosno", "21"), ("Villanueva de las Cruces", "21"), ("El Almendro", "21"),
                             ("Villanueva de los Castillejos", "21"), ("Calañas", "21"), ("El Cerro del Andévalo", "21"),
                             ("Paymogo", "21"), ("Santa Bárbara de Casa", "21"), ("Puebla de Guzmán", "21"),
                             ("Cabezas Rubias", "21"), ("Sanlúcar de Guadiana", "21"), ("El Granado", "21")]),
]
TOP_ALIASES = {"La Granada de Riotinto": "Granada de Río-Tinto, La", "El Cerro del Andévalo": "Cerro de Andévalo, El"}
# Anejo VI Tabla 21, current situation: demand, regulated, run-of-river, groundwater (deficit not supplied)
TOP_BALANCE = {"1": (3.12, 2.96, 0, 0.16), "2": (2.01, 2.01, 0, 0), "3": (0.39, 0.39, 0, 0), "4": (12.18, 12.18, 0, 0),
               "5": (7.00, 7.00, 0, 0), "6": (5.70, 5.70, 0, 0), "7": (12.38, 12.38, 0, 0), "8": (1.08, 1.08, 0, 0),
               "9": (2.01, 0, 0, 0.83), "10": (0.01, 0.01, 0, 0), "11": (2.39, 2.39, 0, 0)}
TOP_BALANCE_ROWS = {"1": "3,12 2,96 0,16", "2": "ETAP Riotinto 2,01 2,01", "3": "ETAP San Silvestre 0,39 0,39",
                    "4": "ETAP Lepe 12,18 12,18", "5": "ETAP Aljaraque 7,00 7,00", "6": "ETAP Tinto 5,70 5,70",
                    "7": "ETAP Huelva 12,38 12,38", "8": "Valverde Camino 1,08 1,08", "9": "Sierra de Huelva 2,01 0,83",
                    "10": "Pomarao 0,01 0,01", "11": "ETAP Andévalo 2,39 2,39"}


def top_named(p):
    why = f"Anejo VI p. {p['acp']}: Sistema Andévalo-Chanza-Piedras (29 municipalities: 18 in the district, 10 in the Chanza basin, Pomarao)"
    acp = [("reservoir", "Andévalo", "main", "", why), ("reservoir", "Chanza", "main", "", why),
           ("reservoir", "Piedras", "main", "", why), ("reservoir", "Los Machos", "main", "", why),
           ("river", "bombeo de Bocachanza", "backup", "", f"Anejo VI p. {p['acp']}: pumping used only in shortages")]
    return {
        "1": {"regulated": [("reservoir", "Corumbel Bajo", "main", "", f"Anejo VI p. {p['acp']}"),
                            ("network", "Sistema Andévalo-Chanza-Piedras", "backup", "", f"Anejo VI p. {p['acp']}: support")],
              "groundwater": [("aquifer", "Niebla", "main", "ES064MSBT000305930", f"Anejo VI p. {p['condado']}")]},
        "2": {"regulated": [("reservoir", "Jarrama", "main", "", f"Anejo VI p. {p['jarrama']}")]},
        "3": {"regulated": acp}, "4": {"regulated": acp}, "5": {"regulated": acp}, "6": {"regulated": acp},
        "7": {"regulated": acp + [("reservoir", "Beas", "main", "", f"Anejo VI p. {p['acp']}: complements the capital's supply")]},
        "8": {"regulated": [("reservoir", "Silillos", "main", "", f"Anejo VI p. {p['jarrama']}: municipal reservoir, main source"),
                            ("reservoir", "Jarrama", "backup", "", f"Anejo VI p. {p['jarrama']}: through the ETAP Riotinto when Silillos falls short")]},
        "9": {"groundwater": [("aquifer", "Aracena", "main", "ES064MSBT004400010", f"Anejo VI p. {p['aracena']}: only source; 1.18 hm3/yr deficit in the balance")]},
        "10": {"regulated": [("reservoir", "Chanza", "main", "", f"Anejo III p. {p['pomarao']}: takes water directly from the Chanza reservoir")]},
        "11": {"regulated": acp},
    }


def run_top(ine):
    out_dir = os.path.join(PLANS_DIR, "tinto_odiel_piedras")
    os.makedirs(out_dir, exist_ok=True)
    p3 = pdf_pages(download(out_dir, "anejo-III-usos-demandas.pdf", TOP_III_URL))
    p6 = pdf_pages(download(out_dir, "anejo-VI-asignacion-reserva-recursos-usos.pdf", TOP_VI_URL))
    flat6 = re.sub(r"\s+", " ", "\n".join(p6))
    for code, row in TOP_BALANCE_ROWS.items():
        assert row in flat6, f"balance row not found: {row}"
    t47 = find_page(p3, "Población y municipios asociados a la UDU consideradas en el Sistema Huelva")
    p = dict(acp=find_page(p6, "Sistema Andévalo-Chanza-Piedras gestionado por la Junta de Andalucía"),
             jarrama=find_page(p6, "UDU de Valverde del Camino desde el embalse de Silillos"),
             condado=find_page(p6, "Chanza-Piedras-Corumbel y la masa de agua subterránea de Niebla"),
             aracena=find_page(p6, "abastecida únicamente por la masa de agua subterránea de Aracena"),
             pomarao=find_page(p3, "que capta agua directamente del embalse del Chanza"))
    named = top_named(p)
    units, munis, sources, unmatched = [], [], [], []
    for code, uname, members in TOP_UDUS:
        units.append((code, uname))
        for name, prov in members:
            if prov == "PT":
                unmatched.append((name, "Portugal", "Portuguese village (Pomarão), outside the INE register; takes water from the Chanza reservoir"))
                continue
            mcode = ine.match(TOP_ALIASES.get(name, name), [prov])
            if not mcode:
                unmatched.append((name, prov, "no INE match"))
                continue
            munis.append(dict(municipality_code=mcode, unit_code=code, share_pct=""))
        tot, reg, flu, sub = TOP_BALANCE[code]
        # Shares over the water actually supplied (Sierra de Huelva has a deficit).
        sources += shares_to_sources(code, dict(regulated=reg, run_of_river=flu, groundwater=sub), named[code],
                                     total=reg + flu + sub)
    meta = {
        "plan": "tinto_odiel_piedras", "basin_id": "ES064", "source": "ph-tinto-odiel-piedras-2022-2027",
        "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Tinto, Odiel y Piedras 2022–2027, Anejo III "
                           f"Usos y demandas, Tabla 47 (p. {t47}); Anejo VI Asignación y reserva de recursos, "
                           "section 4.1.3.3.1 and Tabla 21 (current-situation supply balance)",
        "source_url": TOP_III_URL,
        "source_url_balances": TOP_VI_URL,
        "notes": ("11 UDUs (Sistema Huelva) as in Anejo III Tabla 47, including municipalities in the Guadiana district "
                  "(Chanza basin) and El Madroño (Sevilla) that the plan places in these units. UDU 10 Pomarao is a "
                  "Portuguese village (unmatched.csv). The 13 Condado municipalities outside the district are served by "
                  "the 19.99 hm3/yr transfer to the Guadalquivir district and are not placed in a UDU by this plan. "
                  "Sources from the current-situation balance; share_pct over the water supplied (Sierra de Huelva "
                  "has a 1.18 hm3/yr deficit). Units 3-7 and 11 are the Sistema Andévalo-Chanza-Piedras: its four "
                  "reservoirs are listed for each, together 100% (not split), plus the Bocachanza pumping as backup.")
    }
    write_plan(out_dir, meta, units, munis, sources, unmatched, ine)


def main():
    which = sys.argv[1:] or ["cma", "guadalete_barbate", "tinto_odiel_piedras"]
    ine = Ine()
    runners = {"cma": run_cma, "guadalete_barbate": run_gb, "tinto_odiel_piedras": run_top}
    for w in which:
        runners[w](ine)


if __name__ == "__main__":
    main()
