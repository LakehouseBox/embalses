# site

The public page, served by GitHub Pages from this folder: <https://lakehousebox.github.io/embalses/>

- `index.html`: the whole site. It loads DuckDB-WASM (DuckDB 2.0), attaches the public `embalses` catalog and reads everything from it: the map outlines (`ref.map_outlines`), reservoirs (`now.reservoir_status`), rain (`now.rain_grid`, `now.station_status`) and history (`obs.reservoir_weekly`). There is no backend, no build step, no data file in this folder and no spatial extension.
- `queries.sql`: queries to export a snapshot for offline work.
- `prototype/`, `prototype-3d/`: earlier design prototypes.

To run it locally: `python3 -m http.server -d site 8000` and open <http://127.0.0.1:8000/>.
