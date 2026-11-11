You write the one-paragraph headline at the top of the embalses map: what the rain of the last hours is doing to Spain's reservoirs.

Read the `embalses` catalog guide first (its AGENTS.md). Then run at most four queries:

1. `now.basin_summary` joined to `ref.basins`: fill now vs the same week last year and the 10-year average, and 24 h rain per basin.
2. The 10 reservoirs with the largest `rain_volume_hm3` in `now.upstream_rain` for the 24h window (12h if 24h is empty), joined to `ref.reservoirs` for names.
3. The 10 largest `change_24h_hm3` in `now.reservoir_status` (live stations only; skip if all null).
4. The wettest grid area: the top cells of `now.rain_grid` for 24h, with their basin from `ref.grid_cells`.

Write in Spanish and English, each under 70 words, plain and specific:
- where it rained most, with mm;
- which reservoirs are receiving it, with hm³;
- how the country or the wettest basin compares with normal for this week.

Rules:
- Every number comes from a query you ran in this run. Never estimate, never invent.
- Say "rain that fell upstream", not "water that entered", unless a reservoir's live level actually rose.
- If the newest data is more than 3 hours old, say so in the first sentence.
- If nothing notable happened (no basin above 5 mm in 24 h), write a calm one-line status instead.

Append one row to `embalses.now.headlines`:
- `as_of`: the `as_of` of `now.rain_grid`;
- `headline_es`;
- `headline_en`;
- `figures`: a JSON object with the numbers you used and the query each came from.
