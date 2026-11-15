# Supply data extracted from the river-basin plans: common format

One folder per plan, `data/raw/plans/<plan>/` (e.g. `tajo`, `guadiana`, `jucar`, `galicia_costa`, `canarias_tenerife`),
written by `tools/extract_supply_<plan>.py`. The loader `sql/reference/water_supply.sql` reads every folder with the
same code, so every folder must have exactly these four files, UTF-8, comma-separated, with a header row.

## meta.json
```json
{"plan": "tajo", "basin_id": "ES030", "source": "ph-tajo-2022-2027", "plan_cycle": "2022-2027",
 "source_document": "Plan Hidrológico del Tajo 2022–2027, Anejo 3 Usos y demandas, Tabla 2",
 "source_url": "https://…", "notes": "anything a reviewer should know (coverage, gaps)"}
```
`basin_id` is the district code used in `ref.basins` (ES010 Miño-Sil, ES014 Galicia-Costa, ES017 Cantábrico Oriental,
ES018 Cantábrico Occidental, ES020 Duero, ES030 Tajo, ES040 Guadiana, ES050 Guadalquivir, ES060 Cuencas
Mediterráneas Andaluzas, ES063 Guadalete y Barbate, ES064 Tinto, Odiel y Piedras, ES070 Segura, ES080 Júcar,
ES091 Ebro, ES100 Cuencas Internas de Cataluña, ES110 Islas Baleares, ES120 Gran Canaria, ES122 Fuerteventura,
ES123 Lanzarote, ES124 Tenerife, ES125 La Palma, ES126 La Gomera, ES127 El Hierro, ES150 Ceuta, ES160 Melilla).

## supply_units.csv
`unit_code,unit_name`
- `unit_code`: the plan's own code for the urban supply unit (UDU), exactly as printed. If the plan has no codes, make
  stable ones from the plan's numbering (e.g. `UDU03`) and say so in meta.json notes.
- `unit_name`: the plan's name for it.

## municipality_supply.csv
`municipality_code,unit_code,share_pct,intake_description,additional_intakes`
- `municipality_code`: INE 5-digit code as text, with leading zero. When the plan gives only names, match them to
  `data/raw/ine/municipalities_reference.csv` (official INE names, article last: "Rozas de Madrid, Las"; bilingual
  names with "/"), within the right province. Every code must exist in that file. Unmatched names go to
  `unmatched.csv` (plan_name, province_hint, reason) instead — never guess.
- `share_pct`: 0–100 when the plan splits a municipality between units ("Amurrio (91%)"); empty otherwise.
- `intake_description`: the plan's own wording for where this municipality's water comes from, verbatim (Spanish or the
  plan's language), when the plan gives it per municipality; empty otherwise.
- `additional_intakes`: integer when the plan gives a count; empty otherwise.
- One row per municipality and unit. A municipality may appear in several units only with share_pct.

## supply_sources.csv
`unit_code,municipality_code,source_rank,source_type,source_name,role,water_body_code,share_pct,notes`
- One row per source of water. `municipality_code` empty = applies to the whole unit; filled = this municipality only
  (use it when the plan describes intakes municipality by municipality).
- `source_rank`: 1, 2, … in the order the plan lists them.
- `source_type`, one of: `reservoir`, `river` (any watercourse: río, arroyo, garganta, regato, rivera, azud),
  `aquifer` (groundwater, wells, boreholes, "masa de agua subterránea"), `spring`, `desalination`, `transfer`
  (water brought from another basin by a named transfer, e.g. Trasvase Tajo-Segura), `network` (a supplier's network
  that brings water from its own sources: Canal de Isabel II, Mancomunidad de los Canales del Taibilla, ATL, a
  consorcio or mancomunidad), `reclaimed` (regenerated water used for supply, rare).
- `source_name`: the name as the plan gives it, without the generic word: "Picadas" not "embalse de Picadas";
  rivers keep their generic word in lower case: "río Tiétar", "arroyo del Soto". Aquifers: the groundwater body name
  ("Campo de Montiel"). Desalination: the plant ("IDAM Bocabarranco"). Empty when the plan does not name it.
- `role`: `main` (ordinary source), `backup` (refuerzo, emergency, drought, extraordinary use) or `minor` (serves only a
  small part of the unit, e.g. one housing estate).
- `water_body_code`: the masa de agua code when the plan gives it (ES030MSPF…, 080-107, ES70GC009…); empty otherwise.
- `share_pct`: share of the unit's (or municipality's) water from this source, 0–100, when the plan gives it.
- `notes`: short remark in English, ours, only when needed. The plan's wording belongs in intake_description.

## Rules
- Official documents only (the plans and their annexes, the authorities' own open data). No third-party sites.
- Read every table and ficha the plan has for urban supply; prefer the most specific source information available
  (named reservoirs and aquifers with % over source-type totals).
- Do not invent: a source the plan does not state is left out; a municipality the plan does not place is left out.
- The extractor must be re-runnable: it downloads what it needs into its folder (skip if present) and rewrites the CSVs.
  Use only the Python standard library plus `pdfplumber` (run with `uv run --with pdfplumber python …`). Never disable
  TLS verification; if the system curl fails TLS, Python urllib or `/opt/homebrew/opt/curl/bin/curl` usually work.
