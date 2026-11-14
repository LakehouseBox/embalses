#!/usr/bin/env python3
"""Build the LakehouseBox artifact from the public site: one source, two places to open it.

    python3 tools/build_artifact.py        # writes artifact/page/index.html from site/index.html
    lhbox artifact publish artifact --note "..."

The site (GitHub Pages) runs its own DuckDB-WASM and attaches the public catalog anonymously. An artifact runs
inside LakehouseBox: the page loads the runtime from its own host, which attaches the catalogs the artifact names,
and the page may reach no other host. So the build changes only that edge:
  - the data layer: lhbox.query() instead of a DuckDB-WASM connection of our own;
  - the font: shipped as assets (Source Sans 3, SIL Open Font License) instead of Google Fonts;
  - links out: through lhbox.open(), which asks the viewer before a new tab opens;
  - deep links, the CSV button and "Copiar enlace": through lhbox.setState, lhbox.download and lhbox.copy.
Everything else (map, charts, routes, the SQL box) is the same code.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = (ROOT / 'site/index.html').read_text()
out = src


def swap(old, new, count=1):
    global out
    n = out.count(old)
    if n != count:
        sys.exit(f'build_artifact: expected {count} of {old[:70]!r}, found {n}: site/index.html changed, update this script')
    out = out.replace(old, new)


def swap_re(pattern, new):
    global out
    out, n = re.subn(pattern, new, out, flags=re.S)
    if n != 1:
        sys.exit(f'build_artifact: pattern {pattern[:70]!r} matched {n} times')


# Head: no preconnects or Google Fonts (the page reaches no other host); the font comes from the artifact's assets.
swap_re(r'<link rel="preconnect" href="https://cdn\.jsdelivr\.net" crossorigin>.*?family=Source\+Sans\+3[^>]*>\n', '')
faces = ''.join(
    f"@font-face {{ font-family: 'Source Sans 3'; font-style: normal; font-weight: {w}; font-display: swap; "
    f"src: url(../assets/source-sans-3-{w}.woff2) format('woff2'); }}\n" for w in (400, 600, 700, 800))
swap('<style>\n', '<style>\n' + faces)

# Data: the artifact runtime instead of our own DuckDB-WASM. It attaches the catalog as `embalses`, the name the
# site uses, so every query stays as it is.
swap_re(r"const CAT = `ATTACH.*?\nasync function q\(sql\) \{[^\n]*\n",
        "import { lhbox } from '/_lhbox/lhbox.js';\n"
        "let READY;   // resolves at once: the runtime starts its engine on the first query\n"
        "const connect = async () => {}, conn = lhbox;   // the SQL box waits for `conn`: the runtime is ready at once\n"
        "// The runtime hands a 64-bit integer or a wide decimal over as a string (a count(*), a sum); the charts want numbers.\n"
        "const WIDE = /^(BIGINT|HUGEINT|UBIGINT|UHUGEINT|DECIMAL)/i;\n"
        "async function q(sql) { const r = await lhbox.query(sql), cols = r.columns.map(c => c?.name ?? c);\n"
        "  const wide = r.columns.filter(c => WIDE.test(c?.type || '')).map(c => c.name);\n"
        "  const rows = r.rows.map(o => { const x = Array.isArray(o) ? Object.fromEntries(cols.map((c, i) => [c, o[i]])) : o;\n"
        "    for (const c of wide) if (typeof x[c] === 'string') x[c] = Number(x[c]); return x; });\n"
        "  return { cols, rows }; }\n")
swap('// ───────── data: DuckDB-WASM attached to the public LakehouseBox catalog ─────────',
     '// ───────── data: the LakehouseBox artifact runtime, reading the catalog the artifact names ─────────')

# Deep links: inside the frame location.hash is not the address people see. The page's place (#/cuenca/ebro?capa=lluvia)
# is kept with lhbox.setState instead, which LakehouseBox puts in its own address, so a reload, Back and a copied link
# come back to it. PLACE stands in for location.hash.
swap("function remember(push) { const a = address(); if (location.hash !== a && !(a === '#/' && !location.hash.startsWith('#/'))) history[push ? 'pushState' : 'replaceState'](null, '', a);",
     "// lhbox.state is filled in when the runtime is ready (lhbox:init), not when the module loads\n"
     "let PLACE = ''; lhbox.ready().then(() => { if (!PLACE) PLACE = lhbox.state || ''; }, () => {});\n"
     "const SHARE = () => lhbox.link;   // the address of this view, on the public page or the account page\n"
     "function remember(push) { const a = address(); if (PLACE !== a && !(a === '#/' && !PLACE.startsWith('#/'))) { PLACE = a; lhbox.setState(a, { push }); }")
swap("function route() { if (location.hash && !location.hash.startsWith('#/')) return;",
     "function route() { if (PLACE && !PLACE.startsWith('#/')) return;")
swap("const m = (location.hash || '#/').match(", "const m = (PLACE || '#/').match(")
swap("addEventListener('popstate', route); addEventListener('hashchange', route);",
     "lhbox.onState(s => { PLACE = s || ''; route(); });")

# Files and the clipboard go through the runtime, which asks the viewer first.
swap("a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = 'embalses.csv'; a.click(); };",
     "lhbox.download('embalses.csv', csv); };")
swap("await navigator.clipboard.writeText(location.href);", "if (!await lhbox.copy(SHARE())) throw 0;")

# The frame has no storage, so the outlines are never "fresh": skip the daily refresh query, it would run on every open.
swap("    if (!stillFresh()) q(SQL.outlines).then(r => saveShapes(r.rows)).catch(() => {});   // refresh the stored outlines once a day\n", "")

# How long the first view takes inside LakehouseBox, in the console, to compare with the site.
swap("    setStatus(asOf ? `Datos en directo",
     "    console.info('[embalses] all data in ' + Math.round(performance.now()) + ' ms'); setStatus(asOf ? `Datos en directo")

# Links out: a sandboxed page cannot open them itself.
swap('</script>\n</body>',
     "document.addEventListener('click', e => { const a = e.target.closest('a[href^=\"http\"]'); if (!a) return; e.preventDefault(); lhbox.open(a.href); });\n"
     '</script>\n</body>')

dst = ROOT / 'artifact/page/index.html'
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(out)
print(f'{dst.relative_to(ROOT)}: {len(out):,} bytes')
