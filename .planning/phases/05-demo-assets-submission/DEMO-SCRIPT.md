# Data Ingestor — 3-minute demo shot-list (DEMO-03)

**Goal:** show a judge the full define → propose → validate → confirm → learn loop, plus the human-hint recovery, in under 3 minutes. Lead with the money shot (messy file → clean structure in ~5s).

**Before recording:**
- `cd frontend && npm run build && cd ..`
- `ANTHROPIC_API_KEY=<key-inline> uv run uvicorn assayingest.api.app:app --port 8000`
- Delete any existing `.assayingest/profiles.db` so the learning-loop shot starts clean.
- Browser at `http://127.0.0.1:8000`, window sized so the side-by-side Review table is fully visible.
- Have these files ready: `data/synthetic/crestchem_results.csv`, `novascreen_batch01.csv`, `novascreen_batch02.csv`, `verity_reagents_stock.xlsx`.

Total target: **~2:50**. Narration in *italics*.

---

### Shot 1 — The pitch + define fields (0:00–0:30)

- On **Define Fields**, load the `assay-potency` shape (or add: compound_id/text, assay_type/text, value/number, target/text, n_replicates/integer, assay_date/date with format `%Y-%m-%d`). Name it `demo-v1`, **Save Field Set**.
- *"Every lab formats their assay files differently. A curator normally reformats each one by hand. In Data Ingestor you just declare the fields you want — once."*

### Shot 2 — The money shot: messy file → clean structure (0:30–1:15)

- **Upload** `crestchem_results.csv` with `demo-v1`. Review loads in ~5s.
- *"Claude read a messy file it's never seen and proposed a mapping — with a confidence and a reason for every field."* Point at a green 100% row, then an **amber** row.
- *"It never guesses silently. Anything it's unsure of is flagged yellow, with its reasoning shown — and a no-LLM validator independently re-checks every value against the constraints I declared."*
- Resolve the amber field(s) — click a **chip**, or the manual **dropdown**. Each turns green. Show that **Confirm stays disabled** until the last one clears.
- Click **Confirm & Save Mapping** → export bar appears. *"Nothing is saved until every field is clear — and the server re-checks that gate itself, it never trusts the browser."*

### Shot 3 — The learning loop (1:15–2:00) — the differentiator

- Go to **Upload**, upload `novascreen_batch01.csv` with `demo-v1`. Resolve the few yellow fields, **Confirm & Save**. *"I'll confirm one file from this lab…"*
- Immediately upload `novascreen_batch02.csv` — same lab, same columns — with `demo-v1`.
- Review opens instantly: **zero yellow**, and the banner **"Auto-mapped from a saved profile — 0 Claude calls."**
- *"The second file from the same source maps itself, at full confidence, with no Claude call at all. The more it learns, the less your data ever leaves the machine."* (Optionally point at the **Headers-only** toggle: *"and this sends column names only — never a cell value — to the API."*)

### Shot 4 — Human hint on an unfamiliar file (2:00–2:40)

- Upload `verity_reagents_stock.xlsx` (a completely different domain — reagent inventory — with the header on row 3).
- The tool can't find the table and shows the **inline structural-hint form** instead of failing. Set **header row = 3**, re-parse.
- *"When a file's structure is genuinely unfamiliar, it asks me for one hint instead of crashing or guessing — and this is a totally different domain, proving the tool has no built-in knowledge of assays or anything else."*

### Shot 5 — Close (2:40–2:50)

- *"Claude proposes, a human disposes, and it gets faster and more private every time you use it. That's Data Ingestor."*

---

**Fallback if the UI recording isn't ready:** the entire loop is provable from the CLI (see README Quickstart) — define via a preset YAML, map, `--save-profile`, re-run on the batch02 file to show `0 Claude calls`, and `--hint header-row=3` for the recovery. Phase 3 shipped this CLI loop end-to-end.
