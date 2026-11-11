# embalses

**Where is it raining in Spain, and is that rain reaching the reservoirs?**

A live, open dataset joining Spain's official rain gauges, river gauges and reservoirs, kept up to date inside [LakehouseBox](https://lakehousebox.com). It is published as a public Apache Iceberg catalog and read straight from the browser.

- **Site:** <https://lakehousebox.github.io/embalses/>. One static page ([`site/index.html`](site/index.html)) on GitHub Pages: the browser attaches the public catalog with DuckDB-WASM (DuckDB 2.0) and reads everything from it, map outlines included, with no backend, no data files and no spatial extension. It has a live SQL box and CSV download.
- **Data:** the public catalog `embalses`. Attach it from any DuckDB, no account needed:

  ```sql
  INSTALL iceberg; LOAD iceberg; INSTALL httpfs; LOAD httpfs;
  ATTACH 'jatorre/embalses' AS embalses (TYPE iceberg, ENDPOINT 'https://public-catalog.lakehousebox.com', AUTHORIZATION_TYPE 'none');
  SELECT * FROM embalses."now".reservoir_status LIMIT 10;
  ```

- **For AI agents:** [`docs/AGENTS.md`](docs/AGENTS.md) explains every table, how they join, the units and the caveats. LakehouseBox serves it at the catalog root.

## What's in it

| Namespace | What | Tables |
|---|---|---|
| `ref` | places | `basins`, `catchments`, `rivers`, `reservoirs`, `reservoir_catchments`, `stations`, `grid_cells`, `catchment_cells`, `map_outlines` (GeoJSON text for drawing) |
| `obs` | measurements, append-only | `precipitation`, `weather`, `reservoir_readings`, `river_flow`, `reservoir_weekly` (since 1988), `daily_weather` (since Oct 2023) |
| `now` | rebuilt hourly | `rain_grid` (H3), `upstream_rain`, `reservoir_status`, `basin_summary`, `station_status` |

Every column is documented in the catalog itself ([`docs/table_docs.json`](docs/table_docs.json)).

## How it works

```
official sources ──► scheduled SQL in LakehouseBox ──► Iceberg tables (obs.*)
                                                            │
                     scheduled SQL, sql/now/ (hourly) ◄──────┘──► now.*  ──► site (DuckDB-WASM)
                                                                       └──► hosted agent writes the headline
```

- **Ingestion is SQL.** Each source is one query in [`sql/ingest/`](sql/ingest) that LakehouseBox runs on a schedule. It fetches the publisher's own feed, reshapes it and appends it to an Iceberg table.
- **Tables are migrations.** [`sql/migrations/`](sql/migrations) is plain DuckDB DDL with comments, applied in order.
- **Derived tables are SQL too.** One query per table in [`sql/now/`](sql/now), run hourly by LakehouseBox itself:
  - rain is interpolated onto an H3 grid (inverse distance, gauges within 40 km);
  - it's averaged over every catchment upstream of each dam;
  - and compared with live storage and the same week in past years.
- **Everything else is declared** in [`lakehouse.yaml`](lakehouse.yaml): catalog, sinks, connections, the headline agent.
- **Reference geography** (basins, catchments, rivers, stations) is built once by [`sql/reference/`](sql/reference).

All live ingestion runs inside LakehouseBox as scheduled SQL. [`tools/`](tools) only holds the one-off scripts that loaded history (MITECO weekly bulletin since 1988, AEMET daily values since 2023) and fetched the reference layers.

## Sources

Official sources only, credited as their publishers ask:

- **MITECO**: weekly reservoir bulletin (*Boletín Hidrológico*), dam inventory (*Inventario de Presas y Embalses*), SAIH station register, river basin districts.
- **AEMET OpenData**: hourly and daily weather observations.
- **SAIH real-time networks** of the river-basin authorities: Ebro, Guadalquivir, Guadiana, Segura, Miño-Sil and Cantábrico (more to come).
- **HydroSHEDS** ([Lehner & Grill 2013](https://www.hydrosheds.org)): HydroBASINS and HydroRIVERS, CC BY 4.0.

Real-time values are provisional: the publishers haven't validated them.

## Run it yourself

```sh
lhbox catalog create embalses
lhbox migrate --catalog embalses      # creates the 20 tables from sql/migrations/, with partitioning and descriptions
lhbox plan -f lakehouse.yaml          # shows what apply would create or change
lhbox apply -f lakehouse.yaml         # connections, POST prefixes, the 13 scheduled sinks, table descriptions
```
