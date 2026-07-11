# Feature Research

**Domain:** Human-in-the-loop AI data-mapping / curation review tool (CRO assay ingest)
**Researched:** 2026-07-09
**Confidence:** MEDIUM

## Feature Landscape

Comparable tools surveyed: OpenRefine reconciliation UI (column-to-entity matching with confidence), document/invoice extraction products (Nanonets, Rossum, Docparser) and their human-review layers, general HITL AI-review design patterns (approve/reject/edit queues), and AI-assisted ETL/data-mapping tools. Data Ingestor's three non-negotiable principles (Claude proposes/human disposes, never guess silently, nothing saved until all-clear) map directly onto table-stakes patterns these tools already converge on — which is reassuring: the project brief is not inventing an unfamiliar UX, it's doing the well-understood pattern well, on a fixed 4-day budget.

### Table Stakes (Users Expect These)

Features a data curator will consider baseline. Missing these makes the tool feel untrustworthy or unfinished — exactly the failure mode the "never guess silently" principle exists to prevent.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Side-by-side source vs. mapped view | Every comparable tool (OpenRefine, document-AI review layers) puts raw/original next to proposed/structured so the reviewer never has to context-switch or trust blindly | LOW | Already scoped for Day 3 React UI; two-column layout, source columns left, target fields right |
| Field-level (not row-level) confidence highlighting | Best practice across document-AI tools is granular: highlight the individual uncertain cell/field, not the whole row — cuts review time sharply | LOW | Already implicit in Day 1 mapper output (per-field confidence); UI just needs to render it as yellow per-cell, not per-row |
| Visible reasoning per flagged field | Comparable tools that flag low-confidence fields show *why* (matched region, alternative candidates) — a bare confidence number without a reason reads as a black box and erodes trust | LOW | Day 1 mapper already returns `reason`/flags per field; UI displays it as hover/inline text next to the yellow cell |
| Accept / edit actions per field (not just accept-all) | HITL review UIs standardize on approve/reject/edit as the three core actions; curators expect to override an individual field without discarding the whole draft | LOW–MEDIUM | Needs an editable cell or a dropdown of Claude's ranked alternatives (2-3 options with confidence) per the "never guess silently" principle |
| Bulk-accept for identical/high-confidence matches | OpenRefine's "double-tick accept all identical" pattern exists because reviewers hate re-confirming the same obvious mapping field by field | LOW | For a single-file-at-a-time demo this is less critical than in OpenRefine (which reconciles many rows); still worth a one-click "confirm all green fields" affordance to keep the review fast on camera |
| Explicit "block until clear" export gate | This is principle #3 verbatim, and it is also standard HITL practice: nothing auto-executes until a human approves; the review UI should show a diff/before-after so the reviewer is never guessing what confirming will do | LOW | Day 1 CLI already implements this gate; Day 3 just needs to surface it visually (disabled/greyed "Confirm & Export" button while any field is yellow, with a tooltip naming which fields block it) |
| Audit trail of what was confirmed/changed | Standard HITL and compliance pattern: every approval/edit/reject logged with timestamp and (here) which fields were touched — also exactly what feeds the learning store | LOW–MEDIUM | Natural byproduct of writing the lab profile row; no separate feature needed, but worth logging curator edits distinctly from Claude's original proposal for the demo narrative ("here's what the curator actually changed") |

### Differentiators (Competitive Advantage)

These are where Data Ingestor should compete — and per the project brief, the learning loop is the stated, non-negotiable differentiator. Everything here should visibly serve the video's "money shot."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Explicit, named lab profile with visible auto-map on repeat file** | Comparable products (Rossum, Nanonets) improve *implicitly and statistically* from corrections over time — invisible in a single before/after demo. An explicit, named "lab profile" object that instantly flips a second file from several-yellow to zero-yellow is a legible, camera-friendly effect that generic template-less AI tools don't showcase this cleanly | MEDIUM | This is the single highest-leverage feature for both "Demo 30%" and "Claude Use 25%" judging criteria — build and rehearse this exact sequence first among Day 2-3 work |
| No-LLM validator enforcing a controlled vocabulary | Differentiates from "just trust the LLM" tools; ground truth (allowed assay_type/unit values, compatible pairs) is deterministic Python, not another model call — directly supports "trust the numbers" and gives the demo a concrete "Claude proposed X, but the validator caught it" moment if you engineer one synthetic file to trigger it | LOW–MEDIUM | Already scoped (reference dictionary exists from Day 1); Day 2 work is wiring validator output to force fields back to yellow even if Claude was confident |
| Ranked alternatives (2-3 options with %) for ambiguous columns, not a bare guess | Directly differentiates from most extraction tools, which show one guess + a confidence number; presenting *ranked candidates* (closer to OpenRefine's multi-candidate reconciliation UI) gives the curator a one-click correct choice instead of free-text editing | LOW–MEDIUM | Day 1 mapper can already return alternatives; Day 3 UI needs a small dropdown/chip-picker per ambiguous field rather than a text box |
| Unit inference from value range, flagged not silent | Small but concrete "smart, not silent" moment — visibly different from tools that either fail on missing units or silently guess | LOW | Already implemented Day 1; make sure the UI narrates *why* (e.g. "value 0.045 in typical µM range for IC50") next to the yellow flag so it reads as reasoning, not magic |
| Column-signature keyed matching (not filename or manual lab-selection) | Differentiates the learning loop from "pick your lab from a dropdown" — the system recognizes the *shape* of the file, which is more impressive and more honest about what's actually being learned | MEDIUM | Needs a stable signature function (e.g. sorted normalized header names, or header set hash) — this is the trickiest Day 2 engineering decision; keep it simple (exact or near-exact header-set match) rather than fuzzy, given the time budget |

### Anti-Features (Commonly Requested, Often Problematic)

Things that look good but would burn the remaining ~3-4 days without moving the judged criteria.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Confidence-threshold auto-approve (no human step) at all | Comparable production HITL systems auto-accept above a threshold to reduce reviewer load at scale | Directly contradicts principle #1 ("Claude proposes, human disposes") and principle #3 (block until *all* clear); also removes the reviewable "yellow → confirm" moment that *is* the demo | Keep a low bar for "green" (auto-checked, not auto-*submitted*) but always require one explicit confirm action before export, even for all-green files |
| Fuzzy/statistical learning that generalizes across labs (train a model on corrections) | "Template-less AI" marketing from Nanonets/Rossum suggests this is more sophisticated | Un-demoable in a 3-minute video (improvement is invisible/statistical, not a clean before/after), far more engineering than 2 remaining days allow, and reintroduces LLM-in-the-loop risk on production truth | Explicit per-lab profile keyed by column signature, applied deterministically (exact match = 1.0 confidence), no LLM involved in the learning step itself |
| Multi-user roles, permissions, review queues/SLAs | Enterprise HITL systems (per general HITL design-pattern research) treat this as core infrastructure | Zero relevance to a solo-curator demo; pure scope creep for a judged 4-day hackathon | Single implicit "curator" role; no auth needed for a local demo |
| General-purpose / any-schema mapping (beyond the 7 fixed target fields) | Feels more "real world capable" | Out of scope per PROJECT.md; expands the reference dictionary, validator, and test surface for no judging benefit | Stay bounded to `compound_id, assay_type, value, unit, target, n_replicates, assay_date` as already decided |
| Editable/configurable reference dictionary in the UI (admin screen for adding assay types/units) | Feels more "production ready" | Extra UI, extra validation, no judging-criteria payoff; the dictionary is meant to be a small fixed YAML/JSON per the brief | Ship the dictionary as a static file in the repo; mention extensibility in the README, don't build it |
| Real persistence/database beyond SQLite lab_profile table (e.g. Postgres, cloud deploy) | Looks more "production" for judges | Adds infra risk with no time to spare; nothing in the judging criteria rewards deployment complexity | SQLite file checked into `.gitignore`'d local state is sufficient; the demo runs locally from the video |
| Undo/versioned mapping history across many past confirmations per lab | Sounds like good data hygiene | Only one profile per column-signature is needed for the demo's "second file, zero yellow" beat; history UI adds surface area with no judged payoff | Overwrite the lab profile on each new confirmation (last-confirmed-wins); mention future versioning as a "next steps" line in the README, don't build it |

## Feature Dependencies

```
No-LLM validator (reference dictionary check)
    └──requires──> Reference dictionary (already shipped Day 1)
    └──enhances──> Confidence/flag correctness shown in review UI
                       (validator can force a field back to yellow even if Claude was confident)

React review UI (side-by-side, yellow highlighting, confirm button)
    └──requires──> Claude mapper output with per-field confidence + reasoning (shipped Day 1)
    └──requires──> No-LLM validator output (Day 2) — UI must reflect validator overrides, not just raw Claude confidence
    └──requires──> Block-until-clear export gate logic (exists in CLI form Day 1; UI must reimplement/reuse it)

Learning loop (lab profile save + auto-map)
    └──requires──> Column-signature function (new, Day 2)
    └──requires──> Curator confirm action from the review UI (or CLI) to know a mapping is "trusted enough to save"
    └──enhances──> Demo money-shot: second same-lab file arrives fully green, zero human work

Demonstrable learning-loop video sequence
    └──requires──> Learning loop (SQLite save + lookup)
    └──requires──> ≥2 synthetic files sharing one column signature (one "first contact," one "repeat")
    └──requires──> React review UI (to visually contrast several-yellow vs. zero-yellow at a glance on camera)
```

### Dependency Notes

- **React UI requires validator output, not just raw Claude confidence:** if the UI only reads Claude's self-reported confidence and ignores the Day 2 validator, an out-of-vocabulary `assay_type` that Claude proposed with high confidence would render falsely green. The validator must be able to downgrade a field to yellow regardless of Claude's own score — build the UI to consume a single merged "final confidence + flags" object, not two separate signals the UI has to reconcile itself.
- **Learning loop requires a confirm action as its trigger:** the profile should only be written after a human has cleared all yellow fields (principle #3), never from a merely-proposed draft. This keeps the learning loop consistent with "Claude proposes, human disposes" — the thing being learned is a *human-confirmed* mapping, not an LLM guess.
- **Demonstrable learning-loop sequence requires ≥2 files with an identical (or near-identical) column signature:** this is a data-authoring dependency, not just a code dependency — the 3-4 synthetic "different-lab" files (Day 4 task) need to be planned so that at least one lab has two files sharing headers. Decide the signature function early (Day 2) so file authoring matches it exactly, or the demo's central beat silently fails.
- **Bulk-accept conflicts with nothing here** — it's additive polish on top of the confirm gate, safe to cut first if time runs short.

## MVP Definition

### Launch With (v1 — must be true for the video to work)

- [ ] No-LLM validator forces out-of-vocabulary / incompatible assay-type-unit pairs back to yellow, even if Claude was confident — proves "trust the numbers," not "trust the LLM"
- [ ] Column-signature function + SQLite `lab_profile` table — the mechanical half of the differentiator
- [ ] Confirm action (CLI or UI) writes the lab profile only when zero fields remain yellow — keeps the learning loop honest to principle #3
- [ ] React side-by-side review screen: source columns left, mapped fields right, yellow highlight + reason text on uncertain fields, ranked-alternative picker for ambiguous columns
- [ ] Export/Confirm button disabled while any field is yellow, with visible reason why
- [ ] At least one pair of synthetic files sharing a column signature, so the second upload auto-maps at confidence 1.0 with zero yellow fields, on camera

### Add After Validation (v1.x — only if Day 3 UI finishes early)

- [ ] Bulk "confirm all green fields" one-click action
- [ ] Inline edit of a mapped value in the UI (vs. re-upload) for a corrected field
- [ ] A visible "auto-mapped from lab profile" badge distinct from "Claude mapped this fresh" — makes the learning loop's effect legible even to someone who didn't watch the first file's review

### Future Consideration (v2+ — explicitly do not build for this deadline)

- [ ] Statistical/fuzzy cross-lab learning (train on corrections instead of exact-signature lookup) — defer until there's a reason to generalize beyond the demo's fixed labs
- [ ] Multi-user roles, review queues, SLAs — defer until there's more than one curator
- [ ] Admin UI for editing the reference dictionary — defer until the vocabulary needs to grow beyond the fixed 7 fields

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| No-LLM validator vs. reference dictionary | HIGH | LOW–MEDIUM | P1 |
| Column-signature + SQLite lab profile (learning loop core) | HIGH | MEDIUM | P1 |
| React side-by-side review UI with yellow highlighting | HIGH | MEDIUM | P1 |
| Block-until-clear export gate (UI surfacing) | HIGH | LOW | P1 |
| Ranked-alternative picker for ambiguous fields | HIGH | LOW–MEDIUM | P1 |
| Synthetic same-lab file pair for the demo | HIGH | LOW (authoring, not code) | P1 |
| "Auto-mapped from profile" visible badge | MEDIUM | LOW | P2 |
| Bulk "confirm all green" action | MEDIUM | LOW | P2 |
| Inline field edit (vs. re-upload) | MEDIUM | LOW–MEDIUM | P2 |
| Fuzzy/statistical cross-lab learning | LOW (for this deadline) | HIGH | P3 |
| Admin UI for reference dictionary | LOW | MEDIUM | P3 |
| Multi-user roles/review queues | LOW (for this deadline) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (i.e., must exist before the demo video is recorded)
- P2: Should have, add when possible (Day 3 stretch if the core UI finishes early)
- P3: Nice to have, future consideration — explicitly deferred past this hackathon

## Competitor Feature Analysis

| Feature | OpenRefine (reconciliation) | Rossum / Nanonets (document AI) | Our Approach |
|---------|------------------------------|----------------------------------|--------------|
| Confidence display | Numeric matching score per candidate + facet to sort/filter by score; confidently-matched cells render distinctly (blue link) so attention goes to unmatched cells | Field-level confidence score with the uncertain region highlighted on the source document | Per-field confidence + reason text, yellow highlight on the uncertain cell only (not row) — same "draw the eye to uncertainty" principle, simpler than OpenRefine's faceting since we review one file at a time |
| Ambiguous-match choice | Multiple candidates per cell with id/name/type/score; single-tick accepts one cell, double-tick bulk-accepts identical matches | Typically single best guess + confidence; correction is free-text edit, not multi-candidate picker | Claude returns 2-3 ranked alternatives with % confidence (already shipped Day 1); UI should render as a small picker, closer to OpenRefine's multi-candidate approach than to Rossum's free-text correction — this is a deliberate differentiator, not an accident |
| Learning / memory | None built-in (reconciliation services are stateless per-call, no "remembers this dataset" concept) | Implicit, statistical improvement from accumulated corrections across a global model — no visible per-account "profile" object, not demoable in one before/after | Explicit named lab profile keyed by column signature, applied deterministically at confidence 1.0 on exact repeat — this is the intentional gap we exploit for a legible, camera-ready demo |
| Block-until-clear gate | No equivalent — OpenRefine lets you export a partially-reconciled dataset at any time | Some platforms gate export behind a review status, but it's workflow configuration, not a hard architectural rule | Hard rule: export/confirm literally cannot proceed while any field is yellow — enforced in code, not just UI convention, consistent with principle #3 |

## Sources

- [10 Data Mapping Tools for Integration and AI](https://www.domo.com/learn/article/data-mapping-platforms)
- [Human in the Loop + AI in Data Engineering — Matillion](https://www.matillion.com/blog/human-in-the-loop-ai-data-engineering)
- [Human-in-the-Loop AI Agents: Implementation Patterns](https://www.buildmvpfast.com/blog/human-in-the-loop-ai-agents-implementation-patterns-2026)
- [Designing Human-in-the-Loop Review for High-Stakes Scraped Data — ScrapingAnt](https://scrapingant.com/blog/designing-human-in-the-loop-review-for-high-stakes-scraped)
- [What is Human-in-the-Loop (HITL)? — Databricks Blog](https://www.databricks.com/blog/human-in-the-loop)
- [Human-in-the-loop in AI workflows: Meaning and patterns — Zapier](https://zapier.com/blog/human-in-the-loop/)
- [Document analysis with confidence, grounding, and labeled samples — Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/document/analyzer-improvement)
- [Interpret and improve model accuracy and confidence scores — Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/accuracy-confidence?view=doc-intel-4.0.0)
- [Introducing Confidence Scores — LandingAI](https://landing.ai/blog/introducing-confidence-scores-surface-parsing-uncertainty-before-it-becomes-a-problem)
- [Confidence Scores — Extend docs](https://docs.extend.ai/product/extraction/confidence-scores)
- [Top 10 Docparser Alternatives for Data Extraction — Nanonets](https://nanonets.com/blog/docparser-alternatives/)
- [Nanonets Review: Pricing & Alternatives — Extend](https://www.extend.ai/resources/nanonets-review-features-pricing-alternatives)
- [Reconciliation | OpenRefine/OpenRefine — DeepWiki](https://deepwiki.com/OpenRefine/OpenRefine/3.3-reconciliation)
- [Reconciling | OpenRefine (official docs)](https://openrefine.org/docs/manual/reconciling)
- [Reconciliation API | OpenRefine](https://openrefine.org/docs/technical-reference/reconciliation-api)
- [A survey of OpenRefine reconciliation services (arXiv)](https://arxiv.org/pdf/1906.08092)
- [Template-Less Invoice Extraction: 2026 Guide for AP Teams — Lido](https://www.lido.app/blog/template-less-invoice-extraction)
- [How to Extract Data From Invoices With Hundreds of Different Vendor Formats — Lido](https://www.lido.app/blog/how-to-extract-data-from-invoices-with-hundreds-of-different-vendor-formats)
- [Template-less Invoice Extraction: AI vs. Template-Based OCR](https://invoicedataextraction.com/blog/template-less-invoice-extraction)
- [Human-in-the-Loop AI Review Queues (2026) — All Days Tech](https://alldaystech.com/guides/artificial-intelligence/human-in-the-loop-ai-review-queue-workflows)
- [Human in the Loop AI Review Layer — Velt](https://velt.dev/blog/human-in-the-loop-ai-review-layer)
- [AI Human in the Loop: Production Oversight Patterns — Redis](https://redis.io/blog/ai-human-in-the-loop/)

---
*Feature research for: Human-in-the-loop AI data-mapping / curation review tool (CRO assay ingest)*
*Researched: 2026-07-09*
