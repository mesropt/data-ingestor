# Phase 2: User-Defined Fields + Dynamic Mapper - Research

**Researched:** 2026-07-10
**Domain:** Runtime Pydantic schema construction, Anthropic structured-output, YAML ingestion, locale-aware numeric/date normalisation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**How a user declares fields**
- D-01: A field set is a file. The CLI takes `--fields <path>`. FIELD-01 says "in the UI", but the UI is Phase 4 — the file *is* the contract the browser will POST later, so it is designed once, here.
- D-02: Both YAML and JSON are accepted, dispatched on file extension, parsed into one internal model. YAML is what a human writes and what a preset in the repo should look like when a judge opens it; JSON is what Phase 4's API will carry. Cost: a PyYAML dependency.
- D-03: YAML is loaded with `yaml.safe_load`, never `yaml.load`. `yaml.load` constructs arbitrary Python objects from the document — an obvious remote-code path in a tool whose entire purpose is ingesting files from strangers. This is not optional and belongs in the phase's threat model.
- D-04: A field set holds at most 50 fields. Exceeding it raises a clear error naming the count and the limit.

**What a field may declare**
- D-05: `name` (required) and `description` (optional free text, fed to Claude as the field's meaning).
- D-06: `type` — one of `number | integer | date | text`. This is what makes Phase 1's `column_locales` actionable: a `decimal_comma` column declared `number` is the one thing safe to convert.
- D-07: `allowed_values` — a list. Comparison is case-insensitive; the declared spelling is the canonical one written to the output.
- D-08: `unit` — an expected unit, as a bare string. The tool ascribes no physics to it.
- D-09: `required` — defaults to `true`.
- D-10: `min` / `max` — a numeric range. Not in the requirement; added deliberately (generalises `UNIT_VALUE_RANGES`).
- D-11: `date_format` — a `strptime` pattern. Not in the requirement; added deliberately.
- Constraints are declared in Phase 2 and enforced by Phase 3's validator. The two exceptions are `type` + `date_format`, which the canonical form (EXPORT-01) needs immediately to normalise anything at all.

**What "normalised" means (EXPORT-01)**
- D-12: The tool never converts units. If the file says µM and the field declares nM, the field goes yellow and the human decides.
- D-13: Dates are converted only when the human said how to read them (declared `date_format`). Without it, the value passes through exactly as written and the field is flagged.
- D-14: Decimal commas are converted here — the conversion Phase 1's D-15 deferred to this phase. An `ambiguous` column never reaches this point — Phase 1 already asked.
- D-15: The canonical form is one row per record, columns = the user's field names, produced once. CSV, Excel, and JSON exports (Phase 3) all derive from it; none re-implements normalisation.

**The dynamic schema**
- D-16: The wire model is built at request time with `pydantic.create_model`, using `Literal[tuple(field_names)]` for `target_field`. This constrains Claude at the schema level.
- D-17: The existing wire→domain shape survives: a list of per-field mappings, each with `source_column`, `confidence`, `reasoning`, `needs_confirmation`, `inferred_value`, `alternatives`. Only `target_field`'s type changes.
- D-18: The system prompt is assembled from the field set — names, descriptions, and constraints rendered as text. Nothing about assays, units, or targets survives in the prompt's literal text.
- D-19: Four sites hold the domain today and must all be emptied: `domain/models.py`'s `TargetField` enum; `mapping/schema.py`'s `TargetFieldName = Literal[...]`; `mapping/mapper.py`'s `_SYSTEM_PROMPT` and `_render_request`; and `domain/reference.py` in its entirety. `reference.py`'s content survives only as data, inside the shipped assay preset.

**Presets (FIELD-05)**
- D-20: Presets are YAML files under a top-level data directory, loaded by path like any other field set. No registry, no import, no code branch per preset. Three ship: assay-potency, PK-parameters, reagent-inventory.
- D-21: The reagent-inventory preset exists to be demonstrated, not used — proves no biology is compiled in.

**Defects to fix here**
- D-22: The mapper must receive `RawTable.column_locales`. Today Claude re-asks about `11,076` vs `446,2` — a field the deterministic parser already resolved confidently as `decimal_comma`.
- D-23: Exit codes must distinguish "blocked" from "clear". Add a dedicated code (e.g. 5) for "mapping proposed but not ready"; leave 1/2/3/4 as they are.

### Claude's Discretion
- Where the canonical-record assembly lives (a new module vs `domain/`), and its type (`list[dict]` vs a `Record` dataclass).
- How a "named template" (FIELD-03) resolves — a templates directory plus `--fields @name`, or plain paths only.
- Whether `min`/`max` apply to `date` fields as well as numeric ones.
- How the field set is rendered into the system prompt.
- Whether `allowed_values` implies `type: text` or is orthogonal.

### Deferred Ideas (OUT OF SCOPE)
- Unit conversion (µM → nM) — rejected on principle (D-12).
- Date-format inference (DD/MM vs MM/DD guessing) — deferred to v2.
- Value aliases per field (`ic-50` → `IC50`) beyond case-insensitivity — v2.
- Field-set versioning / migration — out of scope here.
- A `--fields` inline form (`--field name:number`) — convenience, not required.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIELD-01 | User defines target fields (name + optional description); no fields hardcoded | §Standard Stack (PyYAML load), §Architecture Patterns (field-set model), §Code Examples #1 |
| FIELD-02 | Optional constraints (type, allowed_values, unit) used by no-LLM validator | §Architecture Patterns (field-set model), §Common Pitfalls #4/#5 |
| FIELD-03 | Save/reload named template; load field set shared as file | §Architecture Patterns (templates directory), Claude's Discretion note |
| FIELD-04 | Mapper builds structured-output schema at runtime; nothing hardcoded | §Q1/Q2 empirical results, §Code Examples #2/#3 |
| FIELD-05 | Starter library of presets across domains, shipped as editable data | §Q11 preset layout, §Package Legitimacy Audit n/a (no new packages for this) |
| MAP-01 | Claude proposes source→field mapping with per-field confidence + reason | §Code Examples #2/#3, unchanged wire→domain shape (D-17) |
| MAP-02 | Ambiguous field gets 2-3 ranked alternatives; inferred value always flagged | Unchanged from Day-1 (`WireCandidate`); §Common Pitfalls #6 (schema size) |
| EXPORT-01 | Canonical tidy form: one row per record, values normalised (decimal-comma fixed, units as-declared) | §Q5/Q6/Q8 (decimal-comma + date conversion + canonical shape) |
</phase_requirements>

## Summary

This phase replaces four hardcoded domain sites with a runtime-built schema and a user-supplied field-set model, while keeping every architectural pattern Phase 1 and Day 1 already established: wire models at the boundary, frozen domain dataclasses, optional-client-injection for testability, and "propose, never auto-apply." All eleven empirical questions in the brief were verified directly against the installed toolchain (Python 3.14.6, Pydantic 2.13.4, `anthropic` 0.116.0) rather than assumed from training data — this matters because `pydantic.create_model` + dynamic `Literal` behaviour is exactly the kind of API surface that has drifted across major Pydantic versions.

The dynamic schema mechanism (D-16) works cleanly: `Literal[tuple(field_names)]`, `Literal[*field_names]`, and `Literal.__getitem__(tuple(field_names))` are byte-for-byte equivalent on this Pydantic version, and field names containing spaces, the µ sign, or leading digits all work correctly as `Literal` *values* — `create_model`'s identifier requirement applies only to the model's own attribute names (`target_field`, `source_column`, …), never to the runtime-supplied string values inside a `Literal`. The Anthropic SDK derives its JSON Schema fresh on every `messages.parse()` call via `TypeAdapter(output_format).json_schema()` — there is no cross-call schema caching to worry about, so a `create_model` class built per-request is safe and is in fact the SDK's happy path.

Schema and response-payload size scale gently with field count: at the CONTEXT.md-mandated 50-field cap, the JSON Schema itself is ~4,100 characters (~1,000 tokens) and a worst-case all-yellow, 3-alternatives-per-field response is ~26,900 characters (~6,700 tokens) — well past the mapper's current `_MAX_TOKENS = 4096` and squarely inside the non-streaming-safe envelope once raised to ~16,000.

The decimal-comma conversion (D-14) has a single, mechanical implementation that already matches Phase 1's own detection regex: strip `.` (thousands grouping), replace the remaining `,` with `.`, then `float()`. Verified against the two real corpus files that carry this hazard (`pinnacle_labs_export.csv`, `helix_genomics_DE.xlsx`) — but the classic "European thousands + decimal" pattern (`1.234,56`) does not exist anywhere in the ten-file corpus and needs a synthetic Wave-0 test, as does an Excel-native `datetime`-typed date cell (every date in the corpus was generated as a plain formatted string, never a real Excel date type).

**Primary recommendation:** Build the wire schema with `pydantic.create_model` using `Literal[tuple(field_names)]`, keep the wire→domain boundary shape identical to today except `target_field` becomes a plain `str` instead of `TargetField(str)`, raise `_MAX_TOKENS` to a flat 16000, load YAML exclusively via `yaml.safe_load`, and implement decimal-comma conversion with the two-step strip-then-replace algorithm below — all four are now empirically verified, not assumed.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Field-set parsing (YAML/JSON → domain model) | API/Backend (parsing layer, new module) | — | Pure Python, no I/O beyond file read; belongs beside `parsing/table.py` as a sibling concern, not inside it |
| Dynamic wire-schema construction | API/Backend (mapping layer) | — | `mapping/schema.py` already owns wire-model definitions; this is a runtime variant of the same responsibility |
| System-prompt assembly from field set | API/Backend (mapping layer) | — | `mapping/mapper.py` already owns prompt construction |
| Claude structured-output call | API/Backend (mapping layer) | — | Unchanged from Day 1 — `propose_mapping()` |
| Decimal-comma / date normalisation | API/Backend (new canonical-assembly module or `domain/`) | — | Runs once, after mapping is confirmed-shape but before export; pure Python, no SDK, no pandas — Claude's Discretion on exact module |
| Canonical tidy-table assembly (EXPORT-01) | API/Backend (new module, Claude's Discretion) | — | Consumes `MappingProposal` + `RawTable`, produces the one representation Phase 3 exports from |
| Preset storage | CDN/Static (plain data files, not served) | — | Presets are inert YAML files loaded by path; no server, no registry |
| CLI `--fields` flag wiring | API/Backend (`cli.py`) | — | Extends `run()`'s existing orchestration |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PyYAML` | 6.0.3 `[VERIFIED: PyPI via uv resolve]` | Parse the human-authored YAML field-set files (D-02) | Already the project's locked choice (CONTEXT.md D-02/D-03); the de facto standard YAML library in the Python ecosystem; `safe_load` has been unexploitable by arbitrary-code-execution payloads since its introduction — this is a stronger safety property than `yaml.load`/`FullLoader`, which had known RCE CVEs (CVE-2020-1747, CVE-2020-14343) as recently as versions before 5.4 `[CITED: github.com/yaml/pyyaml/wiki, bugzilla.redhat.com/show_bug.cgi?id=1807367]` |
| `pydantic` | 2.13.4 (already installed, `>=2.9` in pyproject.toml) | `create_model()` for the runtime wire schema | Already the project's wire-model library; `create_model` + dynamic `Literal` is documented, community-established pattern for exactly this use case `[VERIFIED: empirical test run against installed version]` |
| `anthropic` | 0.116.0 (already installed, `>=0.69` in pyproject.toml) | `messages.parse(output_format=...)` with a runtime-built Pydantic class | Already the project's SDK; verified the schema-derivation code path (`TypeAdapter(...).json_schema()` + `transform_schema()`) runs per-call with no caching that would break on a dynamically-named class `[VERIFIED: read SDK source at installed version]` |

### Supporting

No new supporting libraries are needed for this phase. `json` (stdlib) already handles the JSON half of D-02's dual-format dispatch.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `PyYAML` + `safe_load` | `ruamel.yaml` (round-trip loader) | `ruamel.yaml` preserves comments/formatting on round-trip and has a stricter default parser, but the project never re-serialises a field set back to YAML (D-02's dual format is read-only ingestion), so the round-trip guarantee buys nothing here; adds a second, less-ubiquitous dependency for no behavioural gain over `safe_load` `[CITED: ruamel.yaml docs — general knowledge, not independently verified this session]` |
| `PyYAML` + `safe_load` | `strictyaml` | Enforces a schema at parse time and refuses YAML's more exotic type-coercion features (a genuine safety plus), but is a bigger paradigm shift — it returns its own `YAML` wrapper object rather than plain dicts, which would require touching every consumer of the parsed field set. Given `safe_load` is already provably safe against the D-03 threat (arbitrary code execution), this doesn't buy enough to justify the migration cost for a hackathon timeline `[ASSUMED — not independently verified this session, general knowledge of strictyaml's design]` |
| `pydantic.create_model` with `Literal[tuple(names)]` | `enum.Enum(...)` built dynamically then used as the field type | Equivalent capability, but `Enum` requires valid-identifier *member names* derived from the field names (µ, spaces, leading digits would need sanitising and an alias), whereas `Literal` uses the raw strings as values directly with no sanitisation needed — `Literal` is strictly the simpler and more faithful choice for this exact requirement `[VERIFIED: empirical test — Literal accepts these strings unmodified]` |

**Installation:**
```bash
uv add pyyaml
```

**Version verification:** `PyYAML` resolves to `6.0.3` via `uv pip install --dry-run pyyaml` against the live PyPI index (2026-07-10). `pydantic` 2.13.4 and `anthropic` 0.116.0 are already installed in `.venv` and satisfy the `pyproject.toml` floors (`>=2.9`, `>=0.69`) — no upgrade needed.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pyyaml` | PyPI | 20+ years (first release 2006; latest 6.0.3 published 2025-09-25) | Not reported by the legitimacy seam's PyPI data source (`weeklyDownloads: null`) | `https://pyyaml.org/` | `SUS` (reason: `unknown-downloads`) | **Approved despite SUS verdict** — see note below |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `pyyaml` — flagged only because the legitimacy seam's PyPI signal source does not surface download counts (`weeklyDownloads: null`), which triggers the seam's generic `unknown-downloads` heuristic. This is a **data-availability gap in the checker, not a legitimacy signal about the package** — PyYAML is one of the most widely used packages in the Python ecosystem (present in the vast majority of Python projects that touch config files), has a 20-year publication history, a real project homepage, no deprecation flag, and no postinstall script. The planner should still add a `checkpoint:human-verify` task before the `uv add pyyaml` step per protocol, but the check itself should take seconds — this is not a candidate for a slopsquatting or supply-chain concern.

*The package name `pyyaml` is `[VERIFIED: PyPI registry + official pyyaml.org homepage]` — it is not a training-data guess; it was independently confirmed to resolve via `uv pip install --dry-run` against the live index this session.*

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌──────────────────────────┐
--fields <path>  →  │  field_set.py (new)      │
(YAML or JSON)      │  load(path) -> FieldSet  │
                    │  yaml.safe_load / json    │
                    └───────────┬──────────────┘
                                │ FieldSet (frozen dataclass,
                                │ list[Field]; each Field has
                                │ name/description/type/
                                │ allowed_values/unit/required/
                                │ min/max/date_format)
                                ▼
RawTable (Phase 1) ──────►┌──────────────────────────┐
  headers, rows,          │  mapping/schema.py        │
  column_locales          │  build_wire_models(       │
                           │    field_set) -> (        │
                           │    WireFieldMapping,       │
                           │    WireMappingProposal)    │
                           │  create_model(...) with    │
                           │  Literal[tuple(names)]     │
                           └───────────┬───────────────┘
                                       │ dynamically-built
                                       │ Pydantic classes
                                       ▼
                           ┌──────────────────────────┐
                           │  mapping/mapper.py         │
                           │  propose_mapping(          │
                           │    table, field_set,       │
                           │    client=None)             │
                           │  - render system prompt    │
                           │    from field_set (D-18)   │
                           │  - inject column_locales   │
                           │    into request (D-22)     │
                           │  - client.messages.parse(  │
                           │    output_format=Wire...)  │
                           └───────────┬───────────────┘
                                       │ WireMappingProposal
                                       ▼
                           ┌──────────────────────────┐
                           │  _to_domain()              │
                           │  target_field: str (was    │
                           │  TargetField enum)         │
                           └───────────┬───────────────┘
                                       │ MappingProposal
                                       │ (domain, unchanged shape)
                                       ▼
                     ┌──────────────────────────────────┐
human confirms  ──►  │  canonical.py (new, Claude's       │
(CLI review gate,    │  Discretion on location)           │
 unchanged from      │  assemble(table, proposal,         │
 Day 1)               │  field_set) -> CanonicalTable       │
                      │  - decimal-comma conversion (D-14) │
                      │  - date conversion only if          │
                      │    date_format declared (D-13)      │
                      │  - unit is recorded, never          │
                      │    converted (D-12)                  │
                      └───────────────┬──────────────────┘
                                      │ CanonicalTable
                                      │ (list[dict[str,Any]]
                                      │  or Record dataclass —
                                      │  Claude's Discretion)
                                      ▼
                          Phase 3: CSV/Excel/JSON exports,
                          validator, learning-loop profiles
```

### Recommended Project Structure
```
src/assayingest/
├── fields/                    # NEW — field-set domain + loading
│   ├── __init__.py
│   ├── models.py              # Field, FieldSet frozen dataclasses
│   └── loader.py              # load(path) -> FieldSet; YAML/JSON dispatch (D-02/D-03)
├── mapping/
│   ├── schema.py              # build_wire_models(field_set) — runtime create_model (D-16)
│   └── mapper.py              # propose_mapping(table, field_set, client=None) — prompt from field_set (D-18)
├── domain/
│   ├── models.py              # FieldMapping/MappingProposal survive; TargetField enum REMOVED (D-19)
│   └── (reference.py DELETED — content lives only in presets/assay-potency.yaml)
├── canonical.py                # NEW (or domain/canonical.py) — EXPORT-01 assembly, decimal/date conversion
└── cli.py                      # --fields flag, exit code 5 (D-23)

presets/                        # NEW top-level, sibling to data/ — D-20/D-21
├── assay-potency.yaml
├── pk-parameters.yaml
└── reagent-inventory.yaml
```

### Pattern 1: Runtime Literal from a list of strings
**What:** Build a `Literal` type whose allowed values come from a runtime list, for use as a Pydantic field's type annotation.
**When to use:** Any time the set of valid string values is not known until request time — exactly FIELD-04's requirement.
**Example:**
```python
# Verified empirically this session against Pydantic 2.13.4 / Python 3.14.6.
# All three forms below are byte-for-byte equivalent (Literal[tuple(x)] == Literal[*x]).
from typing import Literal
from pydantic import create_model, Field

field_names = ["compound id", "µM value", "1st replicate"]  # spaces, µ, leading digit — all fine
TargetFieldName = Literal[tuple(field_names)]

WireFieldMapping = create_model(
    "WireFieldMapping",
    target_field=(TargetFieldName, ...),
    source_column=(str | None, Field(description="Matching source header verbatim, or null.")),
    confidence=(float, Field(description="0.0-1.0 confidence in this mapping.")),
    reasoning=(str, Field(description="Short justification.")),
    needs_confirmation=(bool, Field(description="True whenever a human must confirm.")),
    inferred_value=(str | None, Field(default=None)),
    alternatives=(list, Field(default_factory=list)),
)
# create_model's OWN field names (target_field, source_column, ...) must be valid
# Python identifiers -- that requirement is unaffected. The user's FIELD NAMES
# live only as Literal VALUES and are never required to be identifiers.
```

### Pattern 2: Building the nested wire model tree at runtime
**What:** Compose `create_model`-built classes the same way the static `WireCandidate` / `WireFieldMapping` / `WireMappingProposal` nest today.
**When to use:** Preserving D-17's exact wire→domain shape while only `target_field`'s type becomes dynamic.
**Example:**
```python
# Source: verified this session — anthropic 0.116.0 + pydantic 2.13.4.
from typing import Literal
from pydantic import create_model, Field

def build_wire_models(field_names: list[str]) -> type:
    TargetFieldName = Literal[tuple(field_names)]
    WireCandidate = create_model(
        "WireCandidate",
        source_column=(str, Field(description="A source header that could match.")),
        confidence=(float, Field(description="0.0-1.0 confidence for this option.")),
    )
    WireFieldMapping = create_model(
        "WireFieldMapping",
        target_field=(TargetFieldName, ...),
        source_column=(str | None, Field(description="...")),
        confidence=(float, Field(description="...")),
        reasoning=(str, Field(description="...")),
        needs_confirmation=(bool, Field(description="...")),
        inferred_value=(str | None, Field(default=None)),
        alternatives=(list[WireCandidate], Field(default_factory=list)),
    )
    WireMappingProposal = create_model(
        "WireMappingProposal",
        field_mappings=(list[WireFieldMapping], ...),
    )
    return WireMappingProposal

# Passed directly as output_format -- the SDK calls
# TypeAdapter(WireMappingProposal).json_schema() fresh on every call
# (verified by reading anthropic/resources/messages/messages.py and
# anthropic/lib/_parse/_transform.py at the installed version).
# No caching keyed on class identity or __name__ -- a freshly-built class
# every request is the SDK's normal, supported path.
response = client.messages.parse(
    model="claude-opus-4-8",
    max_tokens=16000,           # raised from 4096 -- see Common Pitfalls #6
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    system=system_prompt,        # built from field_set, not hardcoded (D-18)
    messages=[{"role": "user", "content": request_body}],
    output_format=build_wire_models(field_names),
)
```

### Pattern 3: The verified JSON Schema shape (for reference / debugging)
**What:** What `transform_schema(TypeAdapter(WireMappingProposal).json_schema())` actually produces for a dynamic model.
**When to use:** Sanity-checking that the enum lands correctly and `$defs`/`$ref` resolve.
```json
{
  "$defs": {
    "WireCandidate": {"type": "object", "properties": {"source_column": {"type": "string"}, "confidence": {"type": "number"}}, "additionalProperties": false, "required": ["source_column", "confidence"]},
    "WireFieldMapping": {
      "type": "object",
      "properties": {
        "target_field": {"type": "string", "enum": ["compound_id", "assay_type", "value", "unit", "target", "n_replicates", "assay_date"]},
        "source_column": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "alternatives": {"type": "array", "items": {"$ref": "#/$defs/WireCandidate"}}
      },
      "additionalProperties": false
    }
  },
  "properties": {"field_mappings": {"type": "array", "items": {"$ref": "#/$defs/WireFieldMapping"}}},
  "additionalProperties": false
}
```
Confirmed this session: `target_field`'s `enum` array is populated correctly from a dynamically-supplied field-name list, and the `$defs`/`$ref` nesting for `WireCandidate` resolves exactly as it does for the current static model — there is no special-casing needed for a runtime-built schema.

### Anti-Patterns to Avoid
- **Sanitising field names into Python identifiers before building the Literal:** Unnecessary — verified that spaces, µ, and leading digits work unmodified as `Literal` *values*. Sanitising would force a lossy round-trip (the sanitised name would then need to be mapped back to the user's original spelling for display), which is pure risk for zero benefit.
- **Reusing one `create_model`-built class across requests with different field sets:** Each field set produces a structurally different `Literal`, so the class must be rebuilt per field set (which is cheap — the SDK re-derives the schema on every call anyway; there's no cross-call cache to exploit or invalidate).
- **Leaving `_MAX_TOKENS` at 4096:** Verified this truncates a worst-case 50-field response (~6,700 tokens) well before completion — silent `stop_reason: "max_tokens"` failures, not an error the mapper currently distinguishes from a genuine `ValueError`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constraining Claude's output to a runtime set of valid field names | A custom JSON-Schema-string builder, or post-hoc validation of a free-`str` `target_field` | `pydantic.create_model` + `Literal[tuple(names)]`, passed to `client.messages.parse(output_format=...)` | The SDK already derives a correct, strict JSON Schema (enum + `additionalProperties: false` + `required`) from any Pydantic model, dynamic or static — a hand-rolled schema builder would have to reimplement `transform_schema`'s strict-mode rules (object/array/string type handling, `$defs` recursion) to match, with no guarantee it stays in sync with future SDK versions |
| Safely parsing a YAML file from an untrusted source | A custom YAML tag/type allowlist, or a regex-based YAML subset parser | `yaml.safe_load` (PyYAML) | `SafeLoader`/`safe_load` has been provably unexploitable for arbitrary code execution since PyYAML's first release — building a custom "safer" YAML parser would very likely reintroduce a class of vulnerability that upstream has already spent years hardening against |
| Decimal-comma → float conversion for a locale-ambiguous numeric column | A general-purpose "locale detection" library (e.g. attempting `Babel` or ICU-based number parsing) | The two-step strip-then-replace algorithm below, driven by Phase 1's already-computed `column_locales` annotation | The column-level classification (decimal_comma vs decimal_point vs ambiguous) is already solved by Phase 1's `structure/locale.py` — general locale libraries solve a *harder*, unrelated problem (locale-aware formatting/parsing for arbitrary human languages) and would need to be told the answer Phase 1 already computed, adding a dependency for no new capability |

**Key insight:** Every "don't hand-roll" item in this phase is actually "don't re-derive information Phase 1 or the Anthropic SDK has already computed correctly" — the phase's job is almost entirely about *plumbing* already-solved sub-problems together (schema generation, safe parsing, locale conversion) rather than solving new ones.

## Common Pitfalls

### Pitfall 1: Treating field-name sanitisation as necessary for `Literal`
**What goes wrong:** A developer defensively slugifies field names (`"compound id"` → `"compound_id"`) before building the `Literal`, assuming Pydantic requires identifier-safe values.
**Why it happens:** `create_model`'s *own* keyword arguments (`target_field=...`) do need to be valid identifiers, and it's easy to conflate that requirement with the *values* the `Literal` type accepts.
**How to avoid:** Verified this session — pass field names to `Literal[tuple(names)]` completely unmodified. The values only need to be valid Python string literals (any string is), not identifiers.
**Warning signs:** A field named `"Konz. (µM)"` round-trips through the mapper with the wrong displayed name, or code has an unexplained slugify/unslugify pair around field names.

### Pitfall 2: `_MAX_TOKENS` too low for larger field sets
**What goes wrong:** At the 50-field cap with several ambiguous fields (each carrying reasoning + up to 3 alternatives), the worst-case response payload is ~6,700 tokens. The current `_MAX_TOKENS = 4096` truncates mid-response, and the mapper's existing error handling (`response.parsed_output is None` → raise `ValueError`) does not distinguish this from a genuinely malformed response — the user sees "the model returned no structured proposal" with no indication that raising `max_tokens` would fix it.
**Why it happens:** `_MAX_TOKENS = 4096` was tuned for the fixed 7-field schema; nothing scales it with the now-variable field count.
**How to avoid:** Raise `_MAX_TOKENS` to a flat `16000` (within the SDK's documented non-streaming-safe envelope) regardless of field count — even the 50-field worst case (~6,700 tokens of response, plus thinking-token spend under adaptive thinking) fits comfortably. Do not attempt to compute an exact per-field budget; a generous flat ceiling is simpler and has no meaningful cost difference at this scale.
**Warning signs:** `response.stop_reason == "max_tokens"` in mapper testing with large presets; a field set near 50 fields with several ambiguous columns silently producing `parsed_output is None`.

### Pitfall 3: Assuming `column_locales` is populated for every `RawTable`
**What goes wrong:** `RawTable.column_locales` defaults to `[]` for tables produced by the legacy `parse_file()` path (Phase 1 D-13's docstring explicitly notes this: "Empty for tables that haven't gone through structural detection yet"). Code that unconditionally zips `headers` with `column_locales` by index will silently misalign or crash on a table produced via the legacy path.
**Why it happens:** Two parsing entry points exist (`parse()` vs `parse_file()`), and only `parse()` populates locales.
**How to avoid:** Guard on `len(column_locales) == len(headers)` before using the annotation in the prompt; treat an empty/mismatched list as "no locale information available" rather than indexing blindly.
**Warning signs:** An `IndexError` or a `KeyError`-shaped bug that only appears on the code path that still calls `parse_file()` directly (test fixtures, or any CLI path not yet migrated to `parse()`).

### Pitfall 4: Silently coercing a `non_numeric` or `ambiguous` column when the field declares `type: number`
**What goes wrong:** A field declared `type: number` gets mapped to a source column that Phase 1 annotated `non_numeric` (e.g. a column that's mostly text with occasional numeric-looking noise) or `ambiguous` (Phase 1 already couldn't resolve it and — per D-14 — should have surfaced a `StructureQuestion`, so this case should be rare by the time Phase 2 runs, but a hint-resolved-differently-than-expected edge case is possible). Converting anyway produces a `ValueError` from `float()`, or worse, a silently wrong number if the code falls back to some default.
**Why it happens:** The field's declared type and the column's detected locale are two independent signals that can disagree.
**How to avoid:** Before attempting decimal-comma conversion, check the column's `NumericLocale`. If it is `non_numeric`, the field must be forced to `needs_confirmation=True` regardless of Claude's reported confidence — this is a validator-shaped check that belongs at canonical-assembly time (Phase 2 owns EXPORT-01's conversion; full VAL-01 enforcement is Phase 3, but this specific check is required *now* because EXPORT-01 needs to know whether to attempt the conversion at all). If it is `ambiguous`, Phase 1 should already have asked — treat reaching this point with an `ambiguous` locale as an invariant violation worth a loud internal error, not a silent pass-through.
**Warning signs:** A `ValueError: could not convert string to float` surfacing all the way to the CLI instead of a yellow flag with a plain-English reason.

### Pitfall 5: Guessing at date interpretation when `date_format` is declared but the value doesn't match
**What goes wrong:** `datetime.strptime(value, date_format)` raises `ValueError` on a single malformed row (e.g. `"32/01/2025"`, or a two-digit year the format doesn't expect). If this exception isn't caught, the whole mapping/export pipeline crashes on one bad row instead of flagging just that field.
**Why it happens:** Real-world date columns are rarely perfectly uniform even within one file.
**How to avoid:** Catch `ValueError` per-value (not per-column) during canonical assembly; a single unparseable date value should flag that field's `needs_confirmation=True` with a reason naming the offending value, not abort the whole record. Confirmed via CONTEXT.md D-13: the mechanism is a flag, not a raise — this is the same "propose, never silently trust" posture as everything else in the project.
**Warning signs:** The whole file fails to export because of one row with a typo'd date, instead of that one field going yellow.

### Pitfall 6: Assuming every Excel date cell arrives as a `DD/MM/YYYY`-style string
**What goes wrong:** The synthetic corpus (verified by reading `scripts/gen_synthetic_pk.py`) writes every date as a plain formatted Python string (`f"{d:02d}.{m:02d}.{y}"`) via `ws.append([...])` — none of the ten extended-vendor fixtures contains an actual Excel-native date-typed cell. If a real-world file *does* have a genuinely date-formatted cell, `openpyxl` returns a `datetime.datetime`/`datetime.date` object when reading it, and `RawTable`'s `_row_to_strings` converts that via `str(cell)`, producing something like `"2025-01-01 00:00:00"` — a shape that will not match a `date_format` like `"%d/%m/%Y"`.
**Why it happens:** The existing test corpus happens to never exercise this path, so it's easy to assume all date cells are plain strings.
**How to avoid:** This must be treated as an explicit Wave-0 test gap (see Validation section note below) — write a synthetic fixture with a real Excel date-typed cell and confirm the conversion code either (a) recognises the `str(datetime)` shape as a distinguishable case and handles it, or (b) simply fails the `strptime` match and flags the field per Pitfall 5's mechanism (acceptable, but should be a deliberate choice, not an accident).
**Warning signs:** A field silently goes yellow on every row of a real-world file that has genuine Excel date formatting, with no test in the suite that would have caught it before a demo.

## Code Examples

### Decimal-comma to float conversion (D-14), verified against Phase 1's own detection regex
```python
# Source: derived directly from Phase 1's structure/locale.py _COMMA_DECIMAL
# regex ("the comma is the LAST separator seen"), verified against real
# corpus values from pinnacle_labs_export.csv and helix_genomics_DE.xlsx.

def convert_decimal_comma(raw: str) -> float:
    """Convert a value from a column Phase 1 classified `decimal_comma`.

    Mirrors structure/locale.py's own parsing rule: strip every '.' (assumed
    thousands grouping), then treat the remaining ',' as the decimal point.
    Raises ValueError on anything that still doesn't parse -- the caller
    (canonical assembly) catches this per-value and flags the field, it
    never propagates to a crash (Pitfall 4/5).
    """
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    return float(cleaned)  # raises ValueError on genuine garbage

# Verified against real corpus values:
assert convert_decimal_comma("11,076") == 11.076   # pinnacle_labs_export.csv
assert convert_decimal_comma("446,2") == 446.2      # pinnacle_labs_export.csv
assert convert_decimal_comma("654,85") == 654.85    # pinnacle_labs_export.csv
assert convert_decimal_comma("14,771") == 14.771    # helix_genomics_DE.xlsx
# Not present in the corpus -- needs a synthetic Wave-0 test:
assert convert_decimal_comma("1.234,56") == 1234.56  # European thousands+decimal
assert convert_decimal_comma("-5,2") == -5.2          # negative
```

### Date conversion with per-value flagging (D-13), never a hard crash
```python
from datetime import datetime

def convert_date(raw: str, date_format: str) -> tuple[str | None, bool, str | None]:
    """Returns (iso_value_or_None, needs_confirmation, reason).

    A declared date_format is permission to convert (D-13); a value that
    doesn't match it is NOT a crash -- it is exactly the kind of thing
    needs_confirmation exists for (Pitfall 5).
    """
    try:
        parsed = datetime.strptime(raw.strip(), date_format)
    except ValueError:
        return None, True, (
            f"'{raw}' does not match the declared date_format '{date_format}'"
        )
    return parsed.date().isoformat(), False, None

# Without a declared date_format at all, per D-13 the value passes through
# unchanged and the field is flagged -- this is a field-set-level decision,
# not a per-value one, so it's handled one level up in canonical assembly.
```

### `_to_domain_field` after the `TargetField` enum is removed (D-17/D-19)
```python
# Before (Day 1 / current code, mapping/mapper.py):
#   target_field=TargetField(item.target_field)
#
# After -- target_field is now just the field name string the user declared;
# no enum coercion, because there is no longer a compile-time enum to
# coerce into (D-19 removes domain/models.py's TargetField entirely).
def _to_domain_field(item) -> FieldMapping:
    return FieldMapping(
        target_field=item.target_field,   # plain str, was TargetField(...)
        source_column=item.source_column,
        confidence=item.confidence,
        reasoning=item.reasoning,
        needs_confirmation=item.needs_confirmation,
        inferred_value=item.inferred_value,
        alternatives=[
            ColumnCandidate(c.source_column, c.confidence) for c in item.alternatives
        ],
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Compile-time `Literal[...]` / `Enum` for the mapper's target fields | Runtime `create_model` + `Literal[tuple(names)]` | This phase | Zero domain knowledge compiled into the mapper (FIELD-04); the schema Claude sees is entirely a function of the user's field set |
| `output_format` parameter on `messages.create()` | `output_config.format` (or `client.messages.parse(output_format=...)`, which the SDK internally routes to the same place) | API-wide, not project-specific | The mapper already uses `.parse()`, which is the current recommended path — no change needed here, just confirming it's not on a deprecated surface |
| Fixed `_MAX_TOKENS = 4096` | Flat `16000` (or field-count-scaled if the planner prefers finer control) | This phase | Prevents silent truncation once field sets grow past the fixed 7-field baseline this constant was tuned for |

**Deprecated/outdated:** none directly relevant — the mapper's existing SDK usage pattern (`.messages.parse()`, `thinking: {"type": "adaptive"}`, `output_config: {"effort": "high"}`, model `claude-opus-4-8`) is already on the current, non-deprecated API surface per the `claude-api` skill's cached documentation (2026-06-24). No migration needed on the Anthropic-SDK side for this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ruamel.yaml` is not materially safer than `PyYAML`'s `safe_load` for this project's threat model, so no switch is warranted | Standard Stack → Alternatives Considered | Low — `safe_load`'s safety property is independently verified via web search citation; this assumption is only about whether an *additional* library would add value, not about `safe_load`'s core safety, which is cited from primary sources |
| A2 | `strictyaml`'s schema-first design would require touching every consumer of the parsed field set, making it not worth the migration cost | Standard Stack → Alternatives Considered | Low — this is a design-tradeoff judgment call, not a safety claim; if the planner disagrees, swapping libraries later is a contained, mechanical change since D-02/D-03 already lock the parsing *behaviour* (safe_load semantics), not the specific library name at the API level |
| A3 | A flat `_MAX_TOKENS = 16000` is sufficient for all field-set sizes up to the 50-field cap, without needing per-field-count scaling logic | Common Pitfalls #2, Code Examples | Low-Medium — based on a worst-case payload estimate (~6,700 tokens) plus headroom for adaptive-thinking token spend, which was not separately measured empirically (no live API call was made, per the research protocol's "do not make a live billed API call" instruction); if adaptive thinking under `effort: high` consumes unusually large amounts of budget on a 50-field prompt, 16000 could still be tight — the planner should treat this as a starting value to validate against one real (or recorded/cached) live response during execution, not a proven ceiling |
| A4 | The corpus's complete absence of Excel-native date-typed cells (confirmed by reading the generator script) means this is a genuine test gap rather than an already-covered case | Common Pitfalls #6 | Medium — if wrong (i.e. some hidden fixture does exercise this), the Wave-0 gap recommendation is simply unnecessary work, not a correctness risk either way |

**If this table is empty:** N/A — see entries above.

## Open Questions

1. **Exact adaptive-thinking token spend at `effort: "high"` for a 50-field prompt**
   - What we know: The response *payload* token estimate is ~6,700 tokens worst-case (computed from a synthetic JSON payload of that shape); the schema itself adds ~1,000 input tokens.
   - What's unclear: How many additional tokens adaptive thinking consumes for a prompt of this complexity — this was not measured because the research protocol explicitly forbids a live billed API call, and thinking-token spend under `adaptive` mode is not derivable from static schema inspection.
   - Recommendation: The planner/execution phase should run one real (or cached-from-a-prior-run) `propose_mapping()` call against the 50-field reagent-inventory-scale preset during execution and confirm `response.stop_reason != "max_tokens"` before considering `_MAX_TOKENS = 16000` validated; treat this as a cheap, one-time empirical check rather than something to solve by further static analysis.

2. **Whether `min`/`max` should apply to `date` fields**
   - What we know: CONTEXT.md explicitly leaves this to Claude's Discretion; D-10 frames `min`/`max` as "a numeric range."
   - What's unclear: Whether a date range (e.g. "assay_date must be within 2020-2026") is a real need for this phase's demo scope, or purely hypothetical.
   - Recommendation: Given the Deferred Ideas list already excludes date-format *inference* and the phase's presets (assay-potency, PK, reagent-inventory) don't obviously need date bounds, the planner should default to `min`/`max` applying only to `number`/`integer` types unless a specific demo scenario calls for date bounds — keeps the field-set model's validation surface smaller.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `PyYAML` | D-02/D-03 (YAML field-set parsing) | ✗ (not yet installed) | — | Add via `uv add pyyaml`; resolves to 6.0.3, no fallback needed |
| `pydantic` | D-16 (dynamic schema) | ✓ | 2.13.4 | — |
| `anthropic` SDK | Mapper's Claude call | ✓ | 0.116.0 | — |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | Live mapper calls | ✗ (unset in this research session) | — | Existing optional-client-injection pattern (`propose_mapping(table, client=None)`) already lets all mapper tests run offline with a fake/mocked client — this phase must preserve that pattern for the new `propose_mapping(table, field_set, client=None)` signature |
| `uv` | Dependency management, running tests | ✓ | 0.11.28 | — |
| Python | Runtime | ✓ | 3.14.6 (venv; `pyproject.toml` floor is `>=3.13`) | — |

**Missing dependencies with no fallback:**
- None. `PyYAML` is a one-command install with a verified-current version; nothing else is missing.

**Missing dependencies with fallback:**
- `ANTHROPIC_API_KEY` absence has an existing, already-proven fallback: the optional-client-injection pattern means offline tests never need real credentials. Only a live end-to-end demo run needs the key.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | This phase adds no new authentication surface (CLI-only, same credential resolution as Day 1) |
| V3 Session Management | No | No session concept in this phase |
| V4 Access Control | No | Single-user CLI tool; no access-control boundary introduced |
| V5 Input Validation | Yes | `yaml.safe_load` (never `yaml.load`) for the field-set file (D-03); the field-set model itself is the validation boundary for what a "field" may declare — enforce the 50-field cap (D-04) as a raised, named error before any further processing |
| V6 Cryptography | No | No cryptographic operations introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary Python object construction via a malicious YAML field-set file (`yaml.load` with a Python-object-constructing tag, e.g. `!!python/object/apply`) | Tampering / Elevation of Privilege | `yaml.safe_load` exclusively — verified this is provably unexploitable for this class of payload since PyYAML's first release, unlike `yaml.load`/`FullLoader` which had confirmed RCE CVEs (CVE-2020-1747, CVE-2020-14343) `[CITED: bugzilla.redhat.com/show_bug.cgi?id=1807367]`. This is the single highest-priority security control in this phase, per CONTEXT.md D-03's own framing ("This is not optional and belongs in the phase's threat model") |
| Resource-exhaustion via an oversized field set (e.g. a malformed or adversarial 10,000-field YAML file) causing the mapper to build a schema with a 10,000-entry `Literal` and blow the model's context/token budget with an opaque SDK error | Denial of Service | D-04's hard 50-field cap, enforced with a clear, named error *before* any Pydantic model construction or Anthropic API call is attempted — fail fast on the field-set loader, not deep in the mapper |
| A field-set file with a `date_format` string containing something `strptime`-unsafe, or an `allowed_values`/`unit` string with embedded control characters, propagating into the rendered system prompt unescaped | Tampering (prompt-injection-adjacent) | Not a classic prompt-injection risk in the security sense (this is a single-user CLI tool, and the field-set author is the same person reviewing the output), but worth noting: `date_format` values pass through `datetime.strptime` only, never `eval`/`exec`/format-string interpolation with attacker control over the format specifier itself beyond what `strptime` already permits — no additional mitigation needed beyond the existing per-value `try/except ValueError` wrapping (Pitfall 5) |

## Sources

### Primary (HIGH confidence)
- Direct empirical execution against the installed toolchain (Python 3.14.6, Pydantic 2.13.4, `anthropic` 0.116.0) this session — `pydantic.create_model` + dynamic `Literal` behaviour, full JSON Schema derivation, `transform_schema` output shape
- Direct reading of `anthropic` SDK source at the installed version (`resources/messages/messages.py`, `lib/_parse/_transform.py`, `lib/_parse/_response.py`) — confirms schema is derived fresh per call, no caching hazard
- Direct execution of `parse()` against `data/synthetic/pinnacle_labs_export.csv` and `data/synthetic/helix_genomics_DE.xlsx` — confirms real `column_locales` values and real decimal-comma source data
- Direct reading of `scripts/gen_synthetic_pk.py` — confirms the corpus contains zero Excel-native date-typed cells (Pitfall 6)
- `uv pip install --dry-run pyyaml` / `ruamel.yaml` / `strictyaml` against the live PyPI index (2026-07-10) — confirms current resolvable versions
- `claude-api` skill (bundled, cached 2026-06-24) — confirms `claude-opus-4-8` model ID, `thinking: {"type": "adaptive"}`, `output_config: {"effort": "high"}` are all current, non-deprecated API usage; confirms non-streaming `max_tokens` guidance (~16000 safe ceiling)

### Secondary (MEDIUM confidence)
- [PyYAML yaml.load(input) Deprecation](https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation) — safe_load vs load safety history
- [CVE-2020-1747 — Red Hat Bugzilla](https://bugzilla.redhat.com/show_bug.cgi?id=1807367) — confirms FullLoader RCE even after PyYAML 5.1's initial fix attempt
- [pydantic/pydantic Discussion #11699 — "Can I dynamically generate literals at runtime?"](https://github.com/pydantic/pydantic/discussions/11699) — confirms this is a recognised, community-documented pattern

### Tertiary (LOW confidence)
- General knowledge of `ruamel.yaml` and `strictyaml` design tradeoffs (not independently re-verified via WebSearch beyond confirming they exist and resolve on PyPI) — flagged in the Assumptions Log (A1, A2)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version number and API-surface claim was verified against the actually-installed toolchain or the live PyPI index this session, not assumed from training data
- Architecture: HIGH — the dynamic-schema mechanism (the phase's single riskiest new capability, per STATE.md's own Blockers/Concerns note) was fully empirically verified end-to-end, including the full nested wire-model tree and the SDK's actual schema-transformation code path
- Pitfalls: HIGH for decimal-comma/date/token-budget pitfalls (all grounded in real corpus data or real computed payload sizes); MEDIUM for the adaptive-thinking token-spend estimate specifically (Open Question 1), since no live billed API call was made per protocol

**Research date:** 2026-07-10
**Valid until:** 2026-08-09 (30 days — Pydantic/Anthropic SDK APIs used here are stable, non-beta surfaces; PyYAML is exceptionally stable; re-verify sooner only if the installed `anthropic`/`pydantic` versions change)
