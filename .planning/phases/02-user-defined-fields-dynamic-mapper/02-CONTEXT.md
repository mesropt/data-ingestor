# Phase 2: User-Defined Fields + Dynamic Mapper - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

The user declares the target fields they want extracted — name, optional description, optional constraints — in a file. Claude's structured-output schema is built at runtime from that field set, so the mapper carries zero fields, domains, or vocabularies of its own. A starter library of field-set presets ships as editable data. Applying a proposed mapping yields one canonical tidy table that every later export format derives from.

Covers FIELD-01..05, MAP-01..02, EXPORT-01. Consumes Phase 1's `RawTable` (with `column_locales`). Does **not** validate constraints — that is Phase 3's no-LLM validator. Does **not** persist profiles, export files, or serve HTTP.

</domain>

<decisions>
## Implementation Decisions

### How a user declares fields

- **D-01:** A field set is a file. The CLI takes `--fields <path>`. FIELD-01 says "in the UI", but the UI is Phase 4 — the file *is* the contract the browser will POST later, so it is designed once, here.
- **D-02:** **Both YAML and JSON are accepted**, dispatched on file extension, parsed into one internal model. YAML is what a human writes and what a preset in the repo should look like when a judge opens it; JSON is what Phase 4's API will carry. Cost: a `PyYAML` dependency.
- **D-03:** YAML is loaded with `yaml.safe_load`, never `yaml.load`. `yaml.load` constructs arbitrary Python objects from the document — an obvious remote-code path in a tool whose entire purpose is ingesting files from strangers. This is not optional and belongs in the phase's threat model.
- **D-04:** A field set holds at most **50 fields**. Exceeding it raises a clear error naming the count and the limit. Rationale: an accidental 200-field set silently blows the model's context and surfaces as an opaque SDK error. A hard, named limit is kinder than a mysterious failure. (PROJECT.md's constraint section separately asks that *demo* field sets stay small.)

### What a field may declare

The requirement (FIELD-02) names three. Six ship, chosen by "what actually catches a scientist's mistakes", not by what is cheap:

- **D-05:** `name` (required) and `description` (optional free text, fed to Claude as the field's meaning).
- **D-06:** `type` — one of `number | integer | date | text`. This is what makes Phase 1's `column_locales` actionable: a `decimal_comma` column declared `number` is the one thing safe to convert.
- **D-07:** `allowed_values` — a list. Comparison is **case-insensitive**; the declared spelling is the canonical one written to the output. This generalises `reference.py`'s `ASSAY_TYPES` + `aliases` without any built-in vocabulary.
- **D-08:** `unit` — an expected unit, as a bare string. The tool ascribes no physics to it (see D-11).
- **D-09:** `required` — defaults to `true`. Without it, an optional field that no column supplies would stay permanently yellow and block export forever. Today's seven fields are all implicitly required; making that explicit is the fix.
- **D-10:** `min` / `max` — a numeric range. **Not in the requirement; added deliberately.** `reference.py`'s `UNIT_VALUE_RANGES` exists precisely to catch the 1000× error where nM is read as µM — the headline hazard of this domain. Dropping it while generalising would trade a real safety net for tidiness. Generalised, it is just two numbers per field and works for any domain (a reagent quantity is never negative either).
- **D-11:** `date_format` — a `strptime` pattern. **Not in the requirement; added deliberately.** The live run showed `assay_date` going yellow on `01/01/2025` because DD/MM and MM/DD are indistinguishable. A scientist who knows their source writes `date_format: "%d/%m/%Y"` once and the field is green forever.

Constraints are **declared** in Phase 2 and **enforced** by Phase 3's validator. The two exceptions are `type` + `date_format`, which the canonical form (EXPORT-01) needs immediately in order to normalise anything at all.

### What "normalised" means (EXPORT-01)

- **D-12: The tool never converts units.** If the file says `µM` and the field declares `nM`, the field goes yellow and the human decides. Converting would require the tool to know that `n` is 10⁻⁹ and `µ` is 10⁻⁶ — that is domain knowledge, and the project forbids domain knowledge. Ship a prefix table today and someone asks for pounds→kilograms tomorrow. Worse, it silently multiplies a stranger's numbers by a thousand, which is the exact failure "trust the numbers" exists to prevent. The unit is recorded and checked, never rewritten.
- **D-13: Dates are converted only when the human said how to read them.** With `date_format` declared, the value is parsed and written as ISO-8601. Without it, the value passes through exactly as written and the field is flagged. Guessing `01/01/2025` is the same silent inference as guessing a unit — only about the calendar.
- **D-14: Decimal commas are converted here.** A column Phase 1 annotated `decimal_comma`, in a field declared `number` or `integer`, becomes a real number. This is the conversion D-15 of Phase 1 deferred to this phase. An `ambiguous` column never reaches this point — Phase 1 already asked.
- **D-15:** The canonical form is one row per record, columns = the user's field names, produced once. CSV, Excel, and JSON exports (Phase 3) all derive from it; none re-implements normalisation.

### The dynamic schema

- **D-16:** The wire model is built at request time with `pydantic.create_model`, using `Literal[tuple(field_names)]` for `target_field`. This constrains Claude at the schema level, so it structurally cannot return a field that is not in the user's set. The alternative — a free `str` validated afterwards — lets the model invent names and turns a schema guarantee into a runtime check.
- **D-17:** The existing wire→domain shape survives: a list of per-field mappings, each with `source_column`, `confidence`, `reasoning`, `needs_confirmation`, `inferred_value`, `alternatives`. Only `target_field`'s type changes from a compile-time `Literal` to a runtime one.
- **D-18:** The system prompt is assembled from the field set — names, descriptions, and constraints rendered as text. Nothing about assays, units, or targets survives in the prompt's literal text.
- **D-19:** These four sites hold the domain today and must all be emptied: `domain/models.py`'s `TargetField` enum; `mapping/schema.py`'s `TargetFieldName = Literal[...]`; `mapping/mapper.py`'s `_SYSTEM_PROMPT` (which names IC50/EC50/Ki/Kd) and `_render_request` (which injects `ASSAY_TYPES`/`UNIT_VALUE_RANGES`); and `domain/reference.py` in its entirety. `reference.py`'s content survives only as data, inside the shipped assay preset.

### Presets (FIELD-05)

- **D-20:** Presets are YAML files under a top-level data directory, loaded by path like any other field set. There is no preset registry, no import, no code branch per preset — that is what makes them provably data. Three ship: an assay-potency set, a PK-parameters set, and a **reagent-inventory** set (catalogue number, name, quantity, unit, expiry date, shelf).
- **D-21:** The reagent-inventory preset exists to be *demonstrated*, not used: it proves to a judge that no biology is compiled in. A field set from a neighbouring world with entirely different fields makes the point more legibly at a Life Sciences hackathon than, say, bank transactions would.

### Defects to fix here (found during the Phase 1 live run, not by tests)

- **D-22:** The mapper must receive `RawTable.column_locales`. Today Claude re-asks about `11,076` vs `446,2` — a field the deterministic parser already resolved confidently as `decimal_comma`. A false yellow makes a curator confirm what the machine knows for certain, and it directly damages the learning-loop demo ("second file, zero yellow").
- **D-23:** Exit codes must distinguish "blocked" from "clear". A structural question exits 4; "two fields need confirmation, export disabled" currently exits **0**. For a tool whose whole thesis is that nothing is saved until every yellow clears, a script cannot tell success from a blocked gate. Add a dedicated code (e.g. 5) for "mapping proposed but not ready"; leave 1/2/3/4 as they are.

### Claude's Discretion

- Where the canonical-record assembly lives (a new module vs `domain/`), and its type (`list[dict]` vs a `Record` dataclass).
- How a "named template" (FIELD-03) resolves — a templates directory plus `--fields @name`, or plain paths only. Plain paths are sufficient for the requirement; anything more is convenience.
- Whether `min`/`max` apply to `date` fields as well as numeric ones.
- How the field set is rendered into the system prompt.
- Whether `allowed_values` implies `type: text` or is orthogonal.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` §"Phase 2: User-Defined Fields + Dynamic Mapper" — goal, 6 success criteria
- `.planning/REQUIREMENTS.md` §Fields (FIELD-01..05), §Mapping (MAP-01..02), §Export (EXPORT-01)
- `.planning/REQUIREMENTS.md` §"Out of Scope" — "Any hardcoded field list / domain / controlled vocabulary"; "Confidence-threshold auto-approve"

### Project direction
- `.planning/PROJECT.md` — the domain-independent pivot; supersedes `CLAUDE.md`'s fixed 7-field assay brief. Its Constraints section asks that demo field sets stay small.
- `CLAUDE.md` §"Coding conventions" — Clean Architecture, single level of abstraction, log-or-raise never both, error messages describe the consequence
- `.planning/codebase/CONVENTIONS.md`

### Phase 1's contract (this phase consumes it)
- `.planning/phases/01-robust-file-reading/01-CONTEXT.md` §decisions — especially D-12/D-13/D-15 (parser annotates locale, Phase 2 converts) and D-02 (Claude proposes, never auto-applies)
- `src/assayingest/parsing/table.py` — `RawTable`, now carrying `column_locales`
- `src/assayingest/parsing/hint.py` — `StructuralHint` / `StructureQuestion`; the propose-with-confidence shape a field mapping already mirrors

### Code being generalised (all four are the domain's hiding places — see D-19)
- `src/assayingest/domain/models.py` — `TargetField` enum, `FieldMapping`, `MappingProposal`
- `src/assayingest/mapping/schema.py` — `TargetFieldName = Literal[...]`, the compile-time schema
- `src/assayingest/mapping/mapper.py` — `_SYSTEM_PROMPT`, `_render_request`, `propose_mapping()`, the optional-client injection seam
- `src/assayingest/domain/reference.py` — `ASSAY_TYPES`, `ALLOWED_UNITS`, `UNIT_VALUE_RANGES`; becomes preset data
- `src/assayingest/cli.py` — `run()`, `_map_and_report()`, exit codes (see D-23)

### Test corpus
- `data/synthetic/README.md` — the hazard each file demonstrates
- `data/synthetic/pinnacle_labs_export.csv` — the D-22 reference case: parser says `decimal_comma`, Claude currently re-asks
- `data/synthetic/orion_pk_report.xlsx` — the PK preset's natural target
- `data/synthetic/helix_genomics_DE.xlsx` — German headers; proves `description` carries meaning the header does not

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `propose_mapping(table, client=None)` — keep the signature shape, add the field set. The optional-client seam is how the whole mapping layer stays testable without an API key; do not lose it.
- `FieldMapping` / `ColumnCandidate` / `MappingProposal` and its `is_ready` / `unclear_fields` properties — the gate already works; only `target_field`'s type changes.
- `_to_domain` / `_to_domain_field` — the wire→domain boundary. A runtime-built wire model still maps through here.
- `RawTable.column_locales` and `RawTable.sample(limit)` — everything the prompt needs about the source table.
- `StructureQuestion`'s `answerable_by_hint` precedent: when the tool cannot proceed, it says so plainly instead of offering a useless remedy. A unit mismatch (D-12) should read the same way.

### Established Patterns
- Wire models are Pydantic and live at the boundary; domain models are frozen/plain dataclasses with no SDK import.
- `.messages.parse(..., output_format=Wire...)` with `thinking={"type": "adaptive"}` and `output_config={"effort": "high"}`.
- Module constants in SCREAMING_SNAKE_CASE (`_MODEL`, `_MAX_TOKENS`, `_SAMPLE_ROWS`).
- Structural uncertainty is a returned value, never an exception; exceptions are for broken input. A malformed field-set file **is** broken input — it raises.

### Integration Points
- Phase 1 hands over a `RawTable`; this phase adds a field set and produces a `MappingProposal` plus a canonical tidy table.
- Phase 3 consumes the field set's constraints (validator) and the canonical form (exports + manifest), and keys profiles on `(field set, column signature)` — so a field set needs a stable, order-independent identity. Do not paint that into a corner.
- Phase 4 POSTs the field set as JSON and renders the proposal — hence D-02's dual format.

</code_context>

<specifics>
## Specific Ideas

- The builder asked to see the product before deciding its direction. A state snapshot was published from real tool output (three fixtures, real Claude responses): https://claude.ai/code/artifact/b5f31a03-aced-4114-a3cf-8b38b4897da0 — it is also the source of D-22 and D-23.
- The rule that unifies D-12, D-13, and Phase 1's D-02: *the tool may act on knowledge the human supplied, never on knowledge it inferred about the world.* A declared `date_format` is permission. A unit prefix table would be a belief.
- `min`/`max` (D-10) is the generalised form of `UNIT_VALUE_RANGES`. Losing that safety net while removing hardcoded domain would be a regression dressed as progress.
- TDD is enabled. A field set is a pure data structure and a schema builder is a pure function — both are textbook `type: tdd`.
- Success criterion 3 ("a brand-new field set … with no code change") is provable in a test: load the reagent-inventory preset, map a file, assert the schema contains its field names and no assay names appear anywhere in the prompt.

</specifics>

<deferred>
## Deferred Ideas

- **Unit conversion** (µM → nM) — rejected for v1 on principle (D-12), not merely for time. If ever built, it must be user-declared conversion factors, not a built-in prefix table, and the converted value must be flagged rather than silently written.
- **Date-format inference** — deducing DD/MM vs MM/DD from a column's value distribution (e.g. a value > 12 in the first position settles it). Tempting and cheap, but it is inference about the world; v1 asks. A candidate for v2 as a *proposal* the human confirms, exactly like Phase 1's Claude structural layer.
- **Value aliases per field** (`ic-50` → `IC50`) beyond case-insensitivity — `reference.py` had these. Case-insensitive matching (D-07) covers most of it; a full synonym map is v2.
- **Field-set versioning / migration** — a saved profile in Phase 3 is keyed to a field set; changing the field set invalidates it. Out of scope here.
- **A `--fields` inline form** (`--field name:number`) for quick one-off runs. Convenience, not a requirement.

</deferred>

---

*Phase: 2-user-defined-fields-dynamic-mapper*
*Context gathered: 2026-07-10*
