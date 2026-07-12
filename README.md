# Data Ingestor

**Upload any lab's messy CSV/Excel → Claude maps its columns to the fields you asked for, with honest per-field confidence → you review and confirm. Manual reformatting becomes a one-click review.**

Every contract research organisation (CRO) ships assay data in a different shape — different column names, units, date formats, header positions. A data curator spends hours hand-reformatting each file before it can be used. Data Ingestor does the first pass: you declare the target fields you want, Claude proposes a column mapping with a plain-English reason and a confidence score for each field, anything uncertain is flagged yellow, and **nothing is written until a human clears every flag.**

Built for the **Built with Claude: Life Sciences** hackathon (Builder track). Standalone, open-source (MIT), runs entirely on synthetic data.

---

## The three principles

1. **Claude proposes, human disposes.** Claude only returns a *proposed* mapping via structured output, with per-field confidence and a reason. The human confirms; only then is anything saved. *"Trust the numbers"* — the LLM never touches production truth directly.
2. **Never guess silently.** Missing unit → flag it. Ambiguous column → offer ranked alternatives with % confidence, never a bare "I don't know". A blank or out-of-range value is flagged, not quietly accepted.
3. **Nothing saved until every field is clear.** Confirm and export are blocked while any uncertain (yellow) field remains — and the server re-checks that gate independently, never trusting the browser.

---

## Quickstart

Requires **Python 3.13+**, [`uv`](https://docs.astral.sh/uv/), and **Docker** (for PostgreSQL). Set your Anthropic key one of two ways:

- `export ANTHROPIC_API_KEY=…` in your shell, or
- `cp .env.example .env` and put the key in `.env` at the repo root — both the server and the CLI load it automatically at startup, no extra flags needed.

A real environment variable always wins: if `ANTHROPIC_API_KEY` is already exported (or injected by CI/a deployment), the `.env` file's value is never used to override it. `.env` is gitignored and must never be committed.

`.env.example` also carries `DATABASE_URL` (and `DATABASE_URL_TEST` for the suite). The dev defaults match `docker-compose.yml`, so copying the file is all the database setup you need.

### Database (required, first)

Persistence is **PostgreSQL 17**, in Docker Compose, with the schema owned by Alembic. The app **refuses to start** if the schema is missing rather than booting with an empty field-set picker.

```bash
docker compose up -d            # start PostgreSQL 17
uv run alembic upgrade head     # create the six tables
```

### Web app (the demo)

```bash
uv sync                                   # install the backend
cd frontend && npm install && npm run build && cd ..
uv run uvicorn assayingest.api.app:app --port 8000
# open http://127.0.0.1:8000
```

Then: **Define Fields** (declare your targets) → **Upload** a file → resolve any yellow fields → **Confirm & Save** → re-upload a same-source file and watch it auto-map with **zero Claude calls**.

### CLI (no UI, fully scriptable)

```bash
# Map a file against a field set, review the JSON draft:
uv run assayingest data/synthetic/novascreen_batch01.csv --fields presets/assay-potency.yaml

# Save the confirmed mapping as a profile, then re-run on a same-signature file — auto-mapped, no Claude call:
uv run assayingest data/synthetic/novascreen_batch01.csv --fields presets/assay-potency.yaml --save-profile
uv run assayingest data/synthetic/novascreen_batch02.csv --fields presets/assay-potency.yaml    # 0 Claude calls

# Export the confirmed data + a provenance manifest:
uv run assayingest myfile.csv --fields presets/assay-potency.yaml --export -o out/

# Privacy mode — send column headers only, no cell values, to the API:
uv run assayingest myfile.csv --fields presets/assay-potency.yaml --headers-only

# Give a structural hint when the tool can't find the table on its own:
uv run assayingest weird.xlsx --fields presets/assay-potency.yaml --hint header-row=3
```

Useful flags: `--sheet`, `--strictness strict|lenient` (default strict). The learning-loop store is the PostgreSQL database named by `DATABASE_URL` — there is one documented way in, not a flag and an env var disagreeing with each other. Presets under `presets/` (`assay-potency`, `clinical-labs`, `pk-parameters`, `reagent-inventory`) are plain editable YAML — a field set is just data, with no domain knowledge compiled into the tool.

---

## What makes it more than a wrapper

- **Learning loop.** Confirm one file from a lab once; Data Ingestor saves a *profile* keyed by the field set + a normalised, order-independent column signature. The next file with the same signature auto-maps at confidence 1.0 with **no Claude call at all**. One vendor can hold several profiles as its format drifts over time; a signature mismatch never applies a stale profile — it falls back to a fresh Claude proposal. A structural hint you gave once is replayed automatically. *The more it learns, the less your data leaves the building.*
- **No-LLM validator.** A pure-Python validator re-checks every value — and every ranked alternative Claude offered — against the constraints *you* declared (type, allowed values, unit, min/max). Any objection forces the field back to needs-confirmation regardless of Claude's confidence. Zero LLM calls, no built-in vocabulary.
- **Headers-only privacy mode.** `--headers-only` (and a web toggle) sends Claude the column names only — never a cell value. Field values may be unpublished research IP; this keeps them on your machine. Combined with the learning loop (known formats map locally), the amount of data leaving the perimeter shrinks the more you use it.
- **Provenance on every export.** Each export (CSV + `.xlsx` + JSON) ships a manifest recording the field set, column signature, field→source mapping, per-field confidence, and whether the mapping came from a saved profile or a fresh Claude call.

---

## How it works

Clean-architecture layers, dependencies pointing inward to a pure domain:

```
parsing → mapping (Claude structured output) → domain (fields, validator, learning) → service → { CLI · FastAPI }
                                                                                                      ↑
                                                                                    React review UI (Vite + shadcn)
```

- **Parsing** (`parsing/`) reads messy CSV/Excel by *structure* — header position, delimiter, decimal locale, sheet, table shape — never by hardcoded per-vendor rules; when a layout is genuinely unfamiliar it asks the human for a hint instead of crashing or guessing.
- **Mapping** (`mapping/`) calls Claude with a schema built dynamically from your field set (`client.messages.parse` with structured output) and maps the wire response to domain models at the boundary.
- **Domain** (`domain/`, `fields/`, `validation/`, `learning/`) is pure Python — the field model, the confidence gate, the no-LLM validator, the column signature, and the profile store behind a repository interface. No I/O, no API calls, no database driver. That interface is not theoretical: persistence was swapped wholesale for PostgreSQL (`persistence/`, SQLAlchemy + Alembic) and the domain did not change a line.
- **Service** (`service.py`) is the single orchestration seam both the CLI and the API call — so the browser and the terminal run identical logic, and the server-side confirm gate is the same code either way.

---

## Domain-independence & the synthetic corpus

The tool has **no built-in knowledge of any domain**. `data/synthetic/` proves it across three unrelated domains — assay/potency, clinical-lab panels, and reagent inventory — with a full-detail map in [`.planning/phases/05-demo-assets-submission/05-CORPUS-MAP.md`](.planning/phases/05-demo-assets-submission/05-CORPUS-MAP.md). The corpus deliberately exercises the real structural hazards the parser guards against:

| Hazard | Example file |
|---|---|
| Same-source pair, identical column signature (learning loop) | `novascreen_batch01.csv` / `novascreen_batch02.csv` |
| Missing / ambiguous units | `cascade_assays_nounit.xlsx` |
| Ambiguous / serial / locale dates | `castlebio_native_dates.xlsx` |
| Blank and duplicate headers | `turablo_duplicate_headers.csv` |
| Preamble / junk rows above the header | (see corpus map) |
| Delimiter variance (tab / semicolon / decimal-comma) | `lab_corpus/edge/vantage_lipid.tsv` |
| Multi-sheet workbook needing sheet selection | `nimbus_labs_chartsheet.xlsx` |
| Unfamiliar structure needing a human hint | `verity_reagents_stock.xlsx` (header on row 3) |

All data is synthetic. No real, confidential, or proprietary files are used anywhere in this repo.

---

## Testing

The backend suite runs against a **separate** PostgreSQL database, never your dev one. Create it once:

```bash
docker compose exec -T db createdb -U assayingest assayingest_test
```

```bash
uv run pytest -q                          # backend: unit + API + integration
cd frontend && npm run test -- --run      # frontend: state/logic (vitest)
```

Every test runs inside a transaction that is always rolled back, so the suite leaves the database exactly as it found it. If PostgreSQL is not running, the suite aborts in seconds with an actionable message — it never hangs, and it never quietly passes having tested nothing.

A handful of tests make one real, billed Claude API call each; they are skipped by default and only run with an explicit `ASSAYINGEST_LIVE_TESTS=1 uv run pytest -q` (never merely because a key happens to be configured).

The safety-critical surfaces have adversarial tests: the server-side confirm gate is proven to reject a client that weakens a constraint or omits a still-yellow field, `--headers-only` is proven to send no cell values, and the learning-loop money-shot is proven to make zero Claude calls on a repeat file.

---

## Safety & scope

Data Ingestor is designed **fail-closed** because lab data can bear on human decisions: any ambiguity stops and asks a human, the validator runs on every value even under an auto-applied profile, and the tool never writes on its own. This is a hackathon prototype on synthetic data — it is **not** a certified medical device and carries no regulatory clearance (CLIA / IEC 62304 / ISO 13485 / FDA SaMD). Any real clinical use would require that formal path, plus a review of data-handling terms for values sent to the API.

---

## License

MIT — see [`LICENSE`](LICENSE). New work, fresh repo, synthetic data only.
