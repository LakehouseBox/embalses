# site

The public page, served by GitHub Pages from this folder: <https://lakehousebox.github.io/embalses/>

- `index.html`: the whole site. It loads DuckDB-WASM, attaches the public `embalses` catalog and queries `now.*`, `ref.*` and `obs.reservoir_weekly` from the browser. There is no backend and no build step.
- `geo/`: static outlines used only to draw the map (basins, comunidades, provinces, main rivers).
- `queries.sql`: the same queries, to export a snapshot for offline work.
- `prototype/`, `prototype-3d/`: earlier design prototypes.

To run it locally: `python3 -m http.server -d site 8000` and open <http://127.0.0.1:8000/>.
