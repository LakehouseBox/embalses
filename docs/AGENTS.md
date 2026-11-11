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
  - `stations`: every AEMET and SAIH station.
  - `map_outlines`: simplified outlines of basins, comunidades, provinces and main rivers as GeoJSON text, for drawing a map without a spatial extension (for example in a browser).
- **obs**: measurements. Append-only, partitioned by day, timestamps UTC.
  - `precipitation`: rain per explicit interval.
  - `weather`: temperature, humidity, wind, pressure.
  - Coming next: `reservoir_readings`, `river_flow`, `reservoir_weekly` (since 1988), `daily_weather` (since Oct 2023).
- **now**: hourly summaries, rebuilt inside LakehouseBox: `rain_grid`, `upstream_rain`, `reservoir_status`, `basin_summary`, `station_status`. `reservoir_status` and `station_status` carry names, basin, longitude and latitude, so they can be listed or mapped without joining `ref.*`.

## How the tables join

```
obs.precipitation ─station_id→ ref.stations ─catchment_id→ ref.reservoir_catchments ─reservoir_id→ ref.reservoirs
obs.reservoir_readings ─station_id→ ref.stations (station_type = 'reservoir', reservoir_id set)
ref.reservoirs.basin_id → ref.basins ; ref.rivers.catchment_id → ref.catchments
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
- **SAIH links.** Station-to-reservoir links (`ref.stations.reservoir_id`) were made by location (within 1.5 km); 253 of 375 reservoirs have a live station.
- **Missing networks.**
  - Júcar's real-time viewer is behind a bot check, so Júcar reservoirs come only from the weekly bulletin.
  - The Basque internal basins have no open real-time feed.
- **Bulletin areas.** `bulletin_area_name` (MITECO's bulletin "ámbito") is close to, but not the same as, `basin_id`.

## Freshness

| Table | Updated |
|---|---|
| `obs.precipitation`, `obs.weather` (AEMET) | hourly, ~20–50 min after the hour |
| SAIH readings | every 5–60 min, depending on the basin |
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

## Attribution

Show these wherever the data is displayed:

- MITECO, *Boletín Hidrológico* and *Inventario de Presas y Embalses*
- AEMET OpenData
- SAIH of the river-basin authorities (CH Tajo, Ebro, Duero, Guadiana, Guadalquivir, Segura, Miño-Sil, Cantábrico; Junta de Andalucía; ACA)
- HydroSHEDS (Lehner & Grill 2013), CC BY 4.0
