# Phase 10: Frictionless & Correct Ingest - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Two halves, one theme: **stop asking for what the tool can derive, stop guessing what it cannot.**

The product currently carries two competing notions of "the target fields" — a *field-set template* (Define Fields → a picker on Upload) and a governed *Schema* (Phase 07). They overlap almost entirely: `CanonicalField` already composes `fields.models.Field` (name + every constraint) with its vendor `aliases`. This phase collapses them into one. Schema wins; "field set" survives only as an internal code concept and leaves the UI completely.

Consequently the Upload screen reduces to exactly three controls (Schema, optional map file, headers-only), and the Define Fields and Registry pages merge into a single editable **Schemas** page.

Underneath, two correctness changes: mapping escalates Python → Claude → human (a cheap deterministic pass before an LLM call is ever spent), and every date lands as ISO 8601, its format detected in pure server-side Python and its ambiguity asked once per column rather than guessed.

**NOT in this phase:** the mapping logic itself is not restructured beyond the escalation order. Column splitting (`Age / Sex` → two fields) was explicitly pulled out by the builder — see Deferred.

</domain>

<decisions>
## Implementation Decisions

### Upload screen surface (INGEST-01)

- **D-10-01:** The Upload screen shows **exactly three things**: the target Schema, an optional map file (merged into the master map), and the headers-only toggle. Everything else is removed from the visual. The builder was explicit: "Остальное из визуала убери. Остальное — это внутренняя логика."
- **D-10-02:** The target fields **are** the selected Schema's canonical fields. There is no field-set picker, no field-set proposal UI, and no field-set concept anywhere the user can see. `FieldSet` remains an internal type; it is not a user-facing noun.

### Mapping escalation (INGEST-02)

- **D-10-03:** Mapping resolves in a fixed order, and each stage only sees what the previous could not resolve:
  1. **Python** — match the file's headers against the Schema's crosswalk aliases (deterministic, free, no LLM).
  2. **Claude** — only the columns Python could not resolve.
  3. **Human** — only what Claude could not resolve confidently (the existing amber/confirm gate).
  This is a re-ordering, not a rewrite: the cheap deterministic pass must always run before an LLM call is spent.

### Date normalization (INGEST-04)

- **D-10-04:** Date-format detection is **pure Python, server-side, no LLM** — it lives where `validation/validator.py` and `canonical.assemble()` already read values. Deterministic, testable without an API key.
- **D-10-05:** `headers_only` is therefore **unaffected**: it restricts what *Claude* sees, not what the server reads. Date detection behaves identically in both modes. This preserves the privacy story (values never leave the server) while still detecting ambiguity.
- **D-10-06:** The detector **always runs**, even when the field declares a `date_format`. A declared format is a *human claim*, checked against the data — if the column contradicts it (declared `%d/%m/%Y`, but a value reads `13/25/2025`), the field is flagged and the human is asked. **This supersedes D-13**, under which a declared `date_format` was unconditional permission to convert. Rationale: a typo in a YAML file must not silently flip every date in the file.
- **D-10-07:** An ambiguous format (`03/04/2025` — DD/MM or MM/DD?) **fails closed**: ask the human **once per column**, then apply that answer to every row of that column. Never infer the order silently. A flipped date is a correctness defect, not a cosmetic one.
- **D-10-08:** Excel **numeric date serials** (`45678` → a date) are **in scope** — without them INGEST-04 does not work on real `.xlsx` at all. "Excel corrupted *other* data into dates" (gene names → dates, `wild/10_genelab_date_disaster.xlsx`) stays **out of scope**, in the `parser-excel-hazards` todo.

### Schemas page (INGEST-05)

- **D-10-09:** **Delete Define Fields. Rename Registry → Schemas.** The Schemas page absorbs both jobs. Tabs become: Schemas, Upload, Review (+ Docs).
- **D-10-10:** The Schemas page is one table per Schema, **one row per canonical field**, carrying *both* layers that already exist on `CanonicalField`:
  - the field's **constraints** (`type`, `unit`, `allowed_values`, `required`, `min`, `max`, `date_format`) — what Define Fields used to edit, and what the no-LLM validator depends on;
  - the field's **vendor aliases** with their (read-only) provenance — what Registry used to show.
  Both are **editable**. This is the "редактировать key value" the builder asked for: the canonical field is the key; constraints and aliases hang off it.
- **D-10-11:** Nothing new needs storing. `Schema` → `CanonicalField` → `Field` **already carries every constraint**, and `Schema.to_master_map()` already serializes them. Deleting Define Fields loses no data — it was editing a duplicate concept.
- **D-10-12:** A new **explicit edit endpoint** is required. `POST /api/schemas/{name}/master-map` **stays augment-only** (D-07-04) — an attached map file may only *add*. Only a human may remove or rewrite, and only through the explicit edit path, gated by `require_verified_user`, with provenance recorded as a manual edit.

### Access model (INGEST-06)

- **D-10-13:** **Sign-in is required to use the tool.** There is no anonymous upload path. Upload requires a Schema; a Schema is a governed object; governed objects require a verified user. The demo must therefore show sign-in.
- **D-10-14:** The four shipped presets (`assay-potency`, `clinical-labs`, `pk-parameters`, `reagent-inventory`) are **seeded as Schemas** at startup, so a fresh sign-in has something to select. This **re-targets** quick task `260712-e0e`, which seeded them as *field sets* into a picker this phase deletes.

### Claude's Discretion

- The exact Python alias-matching strategy in D-10-03 (exact match, normalized match, or crosswalk lookup — and whether a near-miss escalates to Claude or is treated as unresolved).
- The exact shape of the "ask once per column" date question — whether it reuses the existing `StructureQuestion` / `/api/structural-hint/resolve` / `StructuralHintPanel` machinery (strongly preferred: that mechanism exists precisely to ask a human one structural question and re-parse) or needs its own analogous flow.
- The visual layout of the Schemas page (row expansion vs side panel), within the constraint that constraints and aliases are both reachable and editable.
- Migration handling for existing field-set rows in the store, including the empty-named row the builder has not asked to delete.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The concepts being merged
- `src/assayingest/domain/models.py` §`CanonicalField` (line ~140) and §`Schema` (line ~157) — the decisive fact for this phase: `CanonicalField = Field (name + ALL constraints) + aliases`. The Schema already holds everything Define Fields was editing.
- `src/assayingest/fields/models.py` §`Field`, §`FieldSet` — the internal field-set type that must survive in code while leaving the UI.

### Dates
- `src/assayingest/canonical.py` §`convert_date` (line 39), §`_convert_field_date` (line 211) — ISO-8601 conversion ALREADY EXISTS; it is gated on a declared `date_format` (D-13). D-10-06 changes that gate.
- `src/assayingest/validation/validator.py` (line ~112-124) — the current "date field with no `date_format` is ALWAYS flagged" behavior that D-10-04/07 replaces with detection.

### The ask-the-human-once mechanism to reuse
- `src/assayingest/parsing/hint.py` §`StructureQuestion` — the existing "one structural question, then re-parse" contract.
- `src/assayingest/api/routes/` (`structural-hint/resolve`) and `frontend/src/components/StructuralHintPanel.tsx` — the existing inline ask-and-resolve loop. D-10-07's per-column date question should ride this, not invent a parallel one.

### The augment-only invariant that must NOT break
- `src/assayingest/api/routes/upload.py` §`_reconcile_upload` — the verified-user gate and augment-only semantics of the map-file path (D-07-04). D-10-12 adds an edit path beside it, never through it.

### Pages being deleted / merged
- `frontend/src/screens/DefineFields.tsx` — to be deleted.
- `frontend/src/screens/Registry.tsx`, `frontend/src/components/RegistryTable.tsx` — to become Schemas.
- `frontend/src/screens/Upload.tsx`, `frontend/src/components/FieldSetPicker.tsx` — the picker to be removed (note: `FieldSetPicker` and the auto-select added in quick `260712-e0e` are deleted by this phase, not extended).

### Deferred work this phase deliberately does not do
- `.planning/todos/pending/parser-excel-hazards.md` — Excel corrupting non-dates into dates; only the *serial* case (D-10-08) is in scope.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Schema` / `CanonicalField` / `Field`**: already carry canonical fields, every constraint, and vendor aliases with provenance. The Schemas page is a *view and edit* over an existing model, not a new one.
- **`canonical.convert_date()`**: ISO-8601 conversion already implemented and tested. The phase adds *detection* in front of it, not conversion itself.
- **`StructureQuestion` → `/api/structural-hint/resolve` → `StructuralHintPanel`**: a complete, working "ask the human exactly one structural question, then re-parse with the answer" loop. The per-column date question is the same shape.
- **`validation/validator.py`**: already runs pure-Python over values with no LLM — proof that server-side value inspection does not violate the headers-only privacy promise.

### Established Patterns
- **Claude proposes, human disposes**: nothing is written until every amber field is cleared. The date question and any Python-vs-Claude disagreement must land in that same gate, not bypass it.
- **Augment-only for machines**: a map file may only add to the crosswalk (D-07-04). Human edits are the only removals, and must be explicit and attributed.
- **Wire models stay at the boundary**: domain models are frozen dataclasses; Pydantic wire models never leak inward.

### Integration Points
- `api/routes/upload.py::_resolve_field_set` — currently 422s without a field set. It must instead derive the field set from the Schema. The 422 contract changes shape here; existing tests pin it.
- `frontend/src/App.tsx` — the tab list (`define-fields`, `upload`, `review`, `registry`, `docs`) shrinks and renames.
- The learning store keys profiles on `(field set, column signature)`. With the Schema as the target, the key becomes `(Schema, column signature)` in effect — the planner must check whether `FieldSet.signature` still behaves correctly when the field set is derived from a Schema, or existing learned profiles silently stop matching.

</code_context>

<specifics>
## Specific Ideas

- The builder's own words for the Upload screen: *"при Upload file пользователь только выбирают схему, только выбирает (опционально) map file, который вмёрджится в master map file, может включить или отключить headers only и всё."*
- The builder's own words for the internal pipeline: *"есть пайтон код, который мапит ключи, если он не может, то приходит клод и потом отправляется на отправку человеку."*
- The builder's own words for the page merge: *"Убирай страницу Define Fields. Переименуй страницу Registry в Schemas. Пусть на странице Schemas можно будет редактировать key value."*
- Constraints must be preserved — the builder confirmed this explicitly when the deletion of Define Fields threatened them.

</specifics>

<deferred>
## Deferred Ideas

- **Column splitting (was INGEST-03)** — a merged key/value column (`Age / Sex` → `65 / M`) feeding two target fields, proposed by Claude with confidence and confirmed by the human, never split automatically (`/` is not always a separator: `N/A`, `mg/mL`, `Ratio A/B`). Pulled out of this phase by the builder: *"давай это разделение оставим на потом, не будем сейчас менять эту логику."* Moved to Future Requirements in `.planning/REQUIREMENTS.md`.
- **Two source columns → one target field** (`First name` + `Last name` → `name`) — the mirror of splitting; never raised as a need, filed with it.
- **Excel corrupting non-dates into dates** (gene names → dates, scientific notation IDs) — stays in `.planning/todos/pending/parser-excel-hazards.md`.

### Reviewed Todos (not folded)
- `parser-excel-hazards.md` — only its Excel *date serial* aspect is folded (D-10-08); the rest (error values `#REF!`, hidden rows, cell-comment reference ranges, multi-row headers) stays deferred to a parser-hardening phase.
- `parser-encoding-detection.md`, `parser-legacy-xls.md`, `parser-ragged-and-preamble.md` — unrelated to this phase's scope.

</deferred>

---

*Phase: 10-frictionless-correct-ingest*
*Context gathered: 2026-07-12*
