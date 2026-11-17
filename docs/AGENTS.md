# embalses: rain, rivers and reservoirs in Spain

Where is it raining, and is that rain reaching the reservoirs? This catalog joins Spain's official rain gauges, river gauges and reservoir data so that question is one query.

Every value comes from its publisher: MITECO (weekly reservoir bulletin, dam inventory, SAIH register, basin districts), AEMET OpenData, each river-basin authority's SAIH network, and HydroSHEDS (catchments and rivers). Nothing comes from third-party aggregators.

## Namespaces

- **ref**: places. Slowly changing, with geometry (Iceberg v3 `GEOMETRY`, EPSG:4326).
  - `basins`: the 25 river basin districts.
  - `catchments`: HydroBASINS level-12 drainage units, each linked downstream.
  - `rivers`: HydroRIVERS segments.
  - `reservoirs`: the 375 reservoirs in MITECO's weekly bulletin.
  - `reservoir_catchments`: every catchment unit upstream of each reservoir.
  - `reservoir_links`: how reservoirs connect, one row per direct link (water flows `from_reservoir_id` → `to_reservoir_id`). River links join each reservoir to the next one downstream; canal and transfer links join reservoirs no river connects.
  - `stations`: every AEMET and SAIH station.
  - `municipalities`: every municipality in Spain (INE code, names, province, region, population, boundary).
  - `supply_units`: urban supply units as the river-basin plans define them, plus the bulk networks they draw on (Canal de Isabel II and its treatment plants, the Taibilla, the Tajo-Segura and Negratín-Almanzora transfers).
  - `municipality_supply`: which supply unit serves each municipality, with the plan's own description of the intake.
  - `supply_sources`: where each unit (or one municipality in it) takes its water: reservoirs (with `reservoir_id` when in the bulletin), rivers, aquifers, springs, desalination, transfers, networks.
  - `municipality_outlines`: simplified outline of every municipality as GeoJSON text, partitioned by province, for drawing one province at a time in a browser.
  - `map_outlines`: simplified outlines of basins, comunidades, provinces and main rivers as GeoJSON text, for drawing a map without a spatial extension (for example in a browser).
- **obs**: measurements. Append-only, partitioned by day, timestamps UTC.
  - `precipitation`: rain per explicit interval.
  - `weather`: temperature, humidity, wind, pressure.
  - Coming next: `reservoir_readings`, `river_flow`, `reservoir_weekly` (since 1988), `daily_weather` (since Oct 2023).
- **now**: hourly summaries, rebuilt inside LakehouseBox: `rain_grid`, `upstream_rain`, `reservoir_status`, `basin_summary`, `station_status`, `municipality_water` (for every municipality, the reservoirs behind its tap water and how full they are together, capacity-weighted; empty level where the water is groundwater or desalinated). `reservoir_status` and `station_status` carry names, basin, longitude and latitude, so they can be listed or mapped without joining `ref.*`.

## How the tables join

```
obs.precipitation ─station_id→ ref.stations ─catchment_id→ ref.reservoir_catchments ─reservoir_id→ ref.reservoirs
obs.reservoir_readings ─station_id→ ref.stations (station_type = 'reservoir', reservoir_id set)
ref.reservoirs.basin_id → ref.basins ; ref.rivers.catchment_id → ref.catchments
ref.reservoir_links.from_reservoir_id / to_reservoir_id → ref.reservoirs
ref.municipalities ─municipality_code→ ref.municipality_supply ─supply_unit_id→ ref.supply_sources ─reservoir_id→ ref.reservoirs
ref.supply_sources.network_unit_id → ref.supply_sources (the network's own sources; follow it to reach its reservoirs)
```

- `reservoir_id` is MITECO's bulletin `EMBALSE_ID`, stable since 1988 (Alcántara = 15, Gabriel y Galán = 150).
- `station_id` is `network:native_code`: `aemet:5769X`, `saih-tajo:E_36`, `saih-ebro:E001`.

## Units and conventions

- The unit is in the column name: `_mm` rain depth (1 mm = 1 L/m²), `_hm3` cubic hectometres (1 hm³ = 10⁶ m³), `_m3s` m³/s, `_masl` metres above sea level, `_km2`, `_pct` (0–100), `_gwh`.
- `…_at` columns are `timestamptz` in UTC. `period_end_at` is the end of the interval the rain fell in.
- Real-time values carry `is_provisional = true`: the publisher has not validated them.

## Caveats

- **Areas.** `ref.reservoirs.catchment_area_km2` is computed from HydroRIVERS. Its median error vs the dam inventory is 2% for catchments over 200 km². Prefer it over `inventory_catchment_area_km2`, which is missing for half the reservoirs and wrong for some.
- **Read `quality_flags` before drawing conclusions about a reservoir.**
  - `no_upstream_gauges` (44 reservoirs): upstream rain must be interpolated from outside.
  - `small_catchment`: < 50 km².
  - `inventory_catchment_area_differs`.
  - Some reservoirs (La Loteta, San Salvador) are filled by canals, so rain upstream says little about them.
- **Averaging rain over an area.** Gauge density varies a lot: median 5 gauges per 1,000 km², and half the catchments have 0–2 gauges inside. A plain average of the gauges inside a catchment is biased; interpolate (IDW onto H3 cells) before averaging.
- **SAIH links.** Station-to-reservoir links (`ref.stations.reservoir_id`) were made by location (within 1.5 km); 253 of 375 reservoirs have a live station. SAIH Cantábrico's reservoirs are not in MITECO's register: its 13 bulletin reservoirs were added by name and capacity (`sql/reference/stations_cantabrico.sql`). Five SAIH Tajo reservoirs further than 1.5 km from the dam point were linked by name (`sql/reference/stations_tajo.sql`). SAIH Ebro's whole-basin map lists only its 12 largest reservoirs, so the sink also reads the viewer's 21 zone maps; eight zone-map reservoirs missing from MITECO's register were added by name (`sql/reference/stations_ebro.sql`). Sixteen SAIH Guadiana stations were linked by name (`sql/reference/stations_guadiana.sql`), among them La Serena and Cijara. Canal de Isabel II's own reservoirs (Pinilla, Riosequillo, Puentes Viejas, El Villar, Pedrezuela, Navacerrada, La Jarosa) are not on the SAIH Tajo viewer and stay on the bulletin.
- **Live feeds running** (`obs.reservoir_readings.source`): saih-ebro, saih-guadalquivir, saih-segura, saih-minosil, saih-cantabrico (every 15 min), saih-guadiana, saih-tajo and saih-hidrosur (Junta de Andalucía: the three Andalusian districts plus Andévalo and Chanza; hourly), and aca (Catalonia's open data, published once a day, so up to ~30 h old; `now.reservoir_status` uses it for 36 h, the SAIH feeds for 6 h). saih-duero comes from the CH Duero's open data (datos.chduero.es, estado_embalses.json, refreshed every 10–30 min), not its SAIH viewer. Hidrosur, ACA and Duero share one sink (`regional_reservoirs`): LakehouseBox takes at most 8 sinks per table. ACA's Siurana is the bulletin's Ciurana (Ebro district; `sql/reference/stations_aca.sql`). Three Duero reservoirs stay on the bulletin on purpose (Santa Teresa, Cernadilla, Irueña): on 2026-11-17 their open-data volume was far above the bulletin with little rain upstream. The bulletin's Guadalhorce-Guadalteba is two dams; Hidrosur's two readings are summed as station `saih-hidrosur:029L02+030E01`. Not yet: Galicia-Costa (weekly PDF only).
- **Missing networks.**
  - Júcar's real-time viewer is behind a bot check, so Júcar reservoirs come only from the weekly bulletin.
  - The Basque internal basins have no open real-time feed.
- **Reservoir links.** River links are computed from HydroRIVERS: each dam's snapped segment, followed downstream to the next dam. Links marked `confidence = 'review'` include pumped-storage pairs and two entries for one reservoir (Santolea). A reservoir upstream drains into the one below, but its water is also used on the way (irrigation, hydropower, environmental flows), so "upstream" is not the same as "available downstream".
- **Water supply.** Built from the 2022–2027 river-basin plans (25 districts), each read with its own tool (`tools/extract_supply_*.py`, common format in `tools/supply_plans_format.md`), plus hand-written network descriptions in `sql/reference/curated/` that cite their documents. The plans differ in detail: some name every intake with its share, others give a source type or the network only. The Ebro uses CHE's register of drinking-water intakes (one unit per municipality); Miño-Sil uses the 2022 consultation draft for the municipality list. A municipality can sit in more than one unit (split towns, or towns supplied from two basins); `share_pct` says how much when the source gives it. A source with `municipality_code` applies to that municipality only. `confidence = 'auto'` rows were read by rule; check `notes` before quoting a single row. Upstream reservoirs are not listed as sources: follow `ref.reservoir_links` from the source reservoir.
- **Bulletin areas.** `bulletin_area_name` (MITECO's bulletin "ámbito") is close to, but not the same as, `basin_id`.

## Freshness

| Table | Updated |
|---|---|
| `obs.precipitation`, `obs.weather` (AEMET) | hourly, ~20–50 min after the hour |
| `obs.precipitation` (SiAR) | daily totals, a day late |
| SAIH readings | every 15–60 min, depending on the basin; ACA (Catalonia) once a day |
| `obs.reservoir_weekly` | Tuesdays (MITECO bulletin) |
| `ref.*` | on demand |

Check `max(period_end_at)` / `max(observed_at)` before reporting "now".

## Ready queries

Rain in the last 24 h at the wettest gauges:

```sql
SELECT s.station_name, s.network, round(sum(p.precipitation_mm), 1) AS rain_24h_mm
FROM embalses.obs.precipitation p JOIN embalses.ref.stations s USING (station_id)
WHERE p.period_end_at > now() - INTERVAL 24 HOUR
GROUP BY ALL ORDER BY rain_24h_mm DESC LIMIT 20;
```

Rain that fell upstream of each reservoir in the last 24 h (gauge mean per catchment unit, area-weighted; a first approximation before interpolation):

```sql
WITH unit_rain AS (
  SELECT s.catchment_id, avg(t.mm) AS mm
  FROM (SELECT station_id, sum(precipitation_mm) AS mm FROM embalses.obs.precipitation
        WHERE period_end_at > now() - INTERVAL 24 HOUR GROUP BY 1) t
  JOIN embalses.ref.stations s USING (station_id) GROUP BY 1)
SELECT r.reservoir_name, r.catchment_area_km2,
       round(sum(u.mm * rc.area_weight) / sum(rc.area_weight), 1) AS upstream_rain_24h_mm,
       round(sum(rc.area_weight), 2) AS share_of_area_with_gauges
FROM embalses.ref.reservoir_catchments rc
JOIN unit_rain u USING (catchment_id)
JOIN embalses.ref.reservoirs r USING (reservoir_id)
GROUP BY ALL ORDER BY upstream_rain_24h_mm DESC LIMIT 20;
```

Every reservoir upstream of Picadas (227) and how full they are together, weighted by size (`UNION` rather than `UNION ALL` stops at loops):

```sql
WITH RECURSIVE up(reservoir_id) AS (
  SELECT 227
  UNION
  SELECT l.from_reservoir_id FROM embalses.ref.reservoir_links l JOIN up ON l.to_reservoir_id = up.reservoir_id
)
SELECT list(s.reservoir_name ORDER BY s.capacity_hm3 DESC) AS reservoirs,
       sum(s.stored_volume_hm3) AS stored_hm3, sum(s.capacity_hm3) AS capacity_hm3,
       round(100 * sum(s.stored_volume_hm3) / sum(s.capacity_hm3), 1) AS fill_pct
FROM up JOIN embalses."now".reservoir_status s USING (reservoir_id);
```

Where a municipality's tap water comes from, through networks, and the reservoirs upstream of each source; with how full they are together (Majadahonda, 28080):

```sql
WITH RECURSIVE
units AS (SELECT supply_unit_id FROM embalses.ref.municipality_supply WHERE municipality_code = '28080'),
src(supply_unit_id, source_type, source_name, reservoir_id, network_unit_id, depth) AS (
  SELECT s.supply_unit_id, s.source_type, s.source_name, s.reservoir_id, s.network_unit_id, 0
  FROM embalses.ref.supply_sources s JOIN units USING (supply_unit_id)
  WHERE s.municipality_code IS NULL OR s.municipality_code = '28080'
  UNION
  SELECT s.supply_unit_id, s.source_type, s.source_name, s.reservoir_id, s.network_unit_id, src.depth + 1
  FROM embalses.ref.supply_sources s JOIN src ON s.supply_unit_id = src.network_unit_id
  WHERE src.depth < 5
),
res(reservoir_id) AS (
  SELECT reservoir_id FROM src WHERE reservoir_id IS NOT NULL
  UNION
  SELECT l.from_reservoir_id FROM embalses.ref.reservoir_links l JOIN res ON l.to_reservoir_id = res.reservoir_id
)
SELECT list(s.reservoir_name ORDER BY s.capacity_hm3 DESC) AS reservoirs,
       sum(s.stored_volume_hm3) AS stored_hm3, sum(s.capacity_hm3) AS capacity_hm3,
       round(100 * sum(s.stored_volume_hm3) / sum(s.capacity_hm3), 1) AS fill_pct
FROM res JOIN embalses."now".reservoir_status s USING (reservoir_id);
```

## Attribution

Show these wherever the data is displayed:

- MITECO, *Boletín Hidrológico* and *Inventario de Presas y Embalses*
- AEMET OpenData
- SAIH of the river-basin authorities (CH Tajo, Ebro, Duero, Guadiana, Guadalquivir, Segura, Miño-Sil, Cantábrico; Junta de Andalucía; ACA)
- HydroSHEDS (Lehner & Grill 2013), CC BY 4.0
- INE (Relación de municipios, Cifras oficiales de población); IGN (Líneas límite municipales), CC BY 4.0
- The river-basin plans 2022–2027 of each district and, for networks, the operators' own documents (cited per row in `ref.supply_units`)
