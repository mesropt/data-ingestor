# Phase 9: Mapping Registry & Documentation - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Mode:** Autonomous overnight build — decisions by the orchestrator per the locked spec, not interactive discuss.

<domain>
## Phase Boundary

The frontend capstone of v2.0: two new pages surface the backbone built in Phases 07–08.
- A **Mapping Registry** page renders the whole crosswalk — **canonical fields on the left, each vendor's name(s) + provenance on the right** (the "Profiles" tab descoped in v1.0, now realized).
- An in-app **Documentation** page — a how-to plus a glossary of the locked terms (Schema / Field / Alias / Organization) so a curator learns the governed vocabulary without leaving the app.

This phase is **frontend-only**. It needs NO new backend: the Registry reads the crosswalk from Phase 07's existing endpoints — `GET /api/schemas` (list) and `GET /api/schemas/{name}/master-map` (the versioned envelope that already carries canonical fields + each field's aliases with `vendor`, `source_column`, `provenance_kind`, `provenance_actor`, `created_at`). If a genuinely missing read is discovered, add a thin gated-consistent read endpoint — but prefer reusing master-map.

Requirements: REG-01, REG-02, DOCS-01.

Out of scope (FUTURE): editing/deleting aliases from the Registry (v2.0 Registry is read/audit only — mutation happens via confirm/import); schema versioning/history views; Organizations (the glossary DEFINES the term as future, the app does not implement org isolation); search/filter beyond a schema selector (nice-to-have, only if trivial).
</domain>

<binding_principles>
## Binding Principles (carry forward)

**P1 — Reuse the locked design system.** Extend the shipped shadcn / Tailwind / `data-theme` dark-primary system (Phase 04 UI-SPEC + `frontend/src/index.css` tokens). The Registry table reuses the `ReviewTable`/table idiom and existing tokens — no new palette, type scale, or component library. This is demo-visible (the "governed master, with lineage" story for judges), so it must look consistent and calm, not bolted on.

**P2 — Read/audit only, provenance is the point.** The Registry is the human-readable face of the data-lineage the crosswalk accretes. Every alias row must show its provenance legibly: `manual` (by which user) vs `from map file` (from which source), and when. Do not invent or omit provenance — render exactly what the envelope carries. No mutation from this page in v2.0.

**P3 — Consistent navigation.** Reuse the existing router-free tab shell (`App.tsx` `TABS` + `activeTab` state + `AppShell`); add the two pages as tabs, not a new routing library. Verification landing / auth overlays keep working unchanged.
</binding_principles>

<decisions>
## Implementation Decisions (orchestrator's calls — planner may refine)

### D-09-01 — Two new tabs in the existing shell
Add `Registry` and `Docs` (or `Documentation`) to the `TABS` array in `App.tsx`, rendered through the existing `AppShell` tab pattern. No new routing dependency; `activeTab` state drives which screen mounts, exactly like Upload/DefineFields/Review today.

### D-09-02 — Registry data from existing endpoints (no new backend)
The Registry screen: a **Schema selector** (from `GET /api/schemas`) → on select, fetch `GET /api/schemas/{name}/master-map` and render its canonical fields + aliases. Add typed api wrappers if not already present (Phase 07 added `listSchemas` + `masterMapDownloadUrl`; add a `getMasterMap(name)` fetch that returns the parsed envelope). Reuse the Phase 07/08 `MasterMapEnvelope` / alias types in `lib/types.ts`.

### D-09-03 — Registry table (REG-01, REG-02)
One row group per **canonical field** (left: field name + its type/unit/constraints as quiet metadata). Right: that field's **vendor aliases**, each showing `vendor`, the vendor's `source_column` name, and a compact **provenance** cell — `manual · <user email>` or `from map file · <source>`, plus the `created_at` timestamp (humanised). A canonical field with no aliases yet renders an explicit "no vendor aliases recorded yet" empty state (not a blank). A whole-Schema empty state when nothing has been confirmed/imported yet, with a one-line hint pointing to Review/confirm and Import. Keep numeric/mono metadata in the existing mono token.

### D-09-04 — Documentation page (DOCS-01)
A static in-app page (pure React content, no backend) with:
- **How-to:** the end-to-end flow in a few steps — define fields (or load a preset) → upload (optionally attach a map file) → review yellow fields & resolve → confirm (signed in) → promote to a Schema → download/import the master map → reconcile a known vendor's next file. Mention the `--headers-only` privacy mode and the learning/auto-map behavior.
- **Glossary:** the four locked terms with the exact locked definitions — **Schema** (one canonical model per domain; its JSON export is the master map file), **Field** (a canonical field in a Schema), **Alias** (a vendor's name for a field, with provenance), **Organization** (owner of a set of Schemas — clearly marked *future / not yet in the app*). Keep copy concise and curator-facing.

### D-09-05 — Viewing is open; consistent with the open master-map GET
Registry viewing does NOT hard-require sign-in in v2.0 (the underlying master-map GET is not gated — only mutations are). Docs is always open. This keeps the demo smooth; the governance gate remains where it matters (confirm/promote/import). If the planner prefers to mirror a soft "sign in to see your governed schemas" affordance it may, but must not block the demo read.

### Claude's Discretion (planner decides)
- Exact table structure (nested rows vs a two-column card per field vs a flat table with a field column) — optimise for readability of the canonical↔alias relationship and provenance.
- Whether the Docs content lives in a `.tsx` component or a small markdown-rendered constant (no new heavy markdown dep — a simple component is fine).
- Whether to add a light client-side search/filter over fields/vendors (only if trivial).
- Tab labels and ordering; whether Registry shows a per-schema "Download master map" affordance (reuses Phase 07's URL — a nice touch).
</decisions>

<canonical_refs>
## Canonical References — downstream agents MUST read before planning/implementing

### Reuse / extend
- `frontend/src/App.tsx` — the `TABS` array + `activeTab` router-free shell to extend with Registry/Docs tabs (keep auth overlay + verify landing working).
- `frontend/src/components/AppShell.tsx` — tab rendering + the Phase 06 `trailing` identity slot.
- `frontend/src/components/ReviewTable.tsx`, `FieldRow.tsx`, `ConfidenceChip.tsx`, `components/ui/*` (table, card, badge, separator, tooltip) — the table/row idiom + tokens the Registry reuses.
- `frontend/src/components/SchemaControls.tsx` (Phase 07) — the Schema selector idiom + existing schema api wrappers.
- `frontend/src/lib/api.ts` + `lib/types.ts` — `listSchemas`, `masterMapDownloadUrl`, `MasterMapEnvelope`/`AliasPayload`/`CanonicalFieldPayload` (Phase 07/08); add `getMasterMap(name)` if missing.
- `frontend/src/state/*` — the store-module idiom if the Registry needs a small reducer (or plain component state is fine for a read-only page).
- Backend (read-only, do NOT change unless a read is genuinely missing): `src/assayingest/api/routes/schemas.py` (`GET /api/schemas`, `GET /api/schemas/{name}/master-map`), `domain/models.py` `Schema.to_master_map` (the exact envelope shape the Registry renders).

### Design contract
- `.planning/phases/04-api-review-ui/04-UI-SPEC.md` + `.planning/phases/06-auth-attribution/06-UI-SPEC.md` — the locked tokens/aesthetic to stay consistent with.
</canonical_refs>

<success_criteria>
## Success Criteria (from ROADMAP — what must be TRUE)

1. **REG-01** — A user can open a Mapping Registry page showing a table with canonical fields on the left and each vendor's name(s) for that field on the right.
2. **REG-02** — The Mapping Registry shows each alias's provenance — how it was mapped, by whom/from what source, and when.
3. **DOCS-01** — A user can open an in-app Documentation page with a how-to and a glossary of the locked terms (Schema / Field / Alias / Organization).
</success_criteria>
