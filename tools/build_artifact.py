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
  - the CSV button and "Copiar enlace" are hidden: the frame may not download, copy or change the address.
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

# The page's frame may not download a file, write to the clipboard or change the address LakehouseBox shows, so the
# CSV button and "Copiar enlace" cannot work there: hide them. LakehouseBox's own Share button shares the page.
swap('</style>\n', '#share, #csv { display: none !important; }\n</style>\n')

# The frame has no storage, so the outlines are never "fresh": skip the daily refresh query, it would run on every open.
swap("    if (!stillFresh()) q(SQL.outlines).then(r => saveShapes(r.rows)).catch(() => {});   // refresh the stored outlines once a day\n", "")

# How long the first view takes inside LakehouseBox, in the console, to compare with the site.
swap("const asOf = D.grid.find(c => c.as_of)?.as_of; setStatus(",
     "console.info('[embalses] all data in ' + Math.round(performance.now()) + ' ms'); const asOf = D.grid.find(c => c.as_of)?.as_of; setStatus(")

# Links out: a sandboxed page cannot open them itself.
swap('</script>\n</body>',
     "document.addEventListener('click', e => { const a = e.target.closest('a[href^=\"http\"]'); if (!a) return; e.preventDefault(); lhbox.open(a.href); });\n"
     '</script>\n</body>')

dst = ROOT / 'artifact/page/index.html'
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(out)
print(f'{dst.relative_to(ROOT)}: {len(out):,} bytes')
