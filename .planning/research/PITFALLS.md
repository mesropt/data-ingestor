# Pitfalls Research

**Domain:** AI-assisted CRO assay data ingestion — LLM structured-output mapping, no-LLM validator, per-lab learning store (SQLite), human-in-the-loop review UI, live hackathon demo.
**Researched:** 2026-07-09
**Confidence:** MEDIUM — general patterns (LLM guardrails, schema/fuzzy matching, HITL UI, live-demo reliability) are web-corroborated across multiple independent sources; no case study exists for this exact combination (CRO assay ingestion + lab-profile learning), so pitfalls are synthesized from adjacent domains plus static analysis of this codebase (`.planning/codebase/CONCERNS.md`). No LOW-confidence claim below is presented as settled fact.

## Critical Pitfalls

### Pitfall 1: Validator silently "fixes" instead of flagging

**What goes wrong:**
The no-LLM validator sees Claude propose `unit: "uM"` (ASCII, no µ), recognizes it as a typo for `µM`, and quietly normalizes it to the canonical form with `confidence: 1.0` and no flag. The curator never sees that a correction happened. This is the exact failure mode Principle 1 exists to prevent — the validator has become a second silent LLM-equivalent black box, just written in Python instead of prompted.

**Why it happens:**
It is tempting to make the validator "smart" (normalize casing, strip whitespace, map synonyms) because it reduces yellow-field noise and makes the demo look cleaner. The line between "normalize a harmless variant" and "silently override a judgment call" is easy to blur under time pressure.

**How to avoid:**
The validator may only do two things: (1) confirm a value is already in the reference vocabulary — with no rewriting — or (2) reject/flag it as invalid and route to human review. Any normalization step (e.g., `"uM"` → `"µM"`) must itself be surfaced in the UI as "Claude proposed X, validator normalized to Y" — never applied invisibly. Treat "confidence forced to `needs_confirmation`" as the *only* validator output for anything not an exact vocabulary match.

**Warning signs:**
A field ends up green (confidence 1.0, no flag) whose raw value from Claude does not literally equal a reference-dictionary entry. Grep the validator for any `.replace()`, `.lower()`, or synonym-map call that also sets `needs_confirmation = False` in the same code path.

**Phase to address:**
Day 2 (validator).

---

### Pitfall 2: Validator conflates "invalid vocabulary" with "low confidence" and discards Claude's alternatives

**What goes wrong:**
The mapper already returns 2-3 ranked alternatives per ambiguous field (Day 1 behavior). If the validator's job is bolted on as a second pass that only looks at the top pick, an invalid top pick (e.g., `assay_type: "inhibition"` instead of `"%inhibition"`) gets rejected and the field is dumped into a generic "needs review, pick manually" state — even though alternative #2 from Claude's own output was the valid vocabulary term all along.

**Why it happens:**
The validator is built as "check the final answer" rather than "validate the whole proposal, including alternatives." Because it's the last thing implemented on Day 2 under deadline pressure, it's easy to treat `MappingProposal` as a flat value rather than a ranked list.

**How to avoid:**
Validate every alternative Claude returned, not just the top one. If the top pick is invalid but an alternative is a valid vocabulary term, promote it to top and keep the field yellow (still needs human confirmation — Principle 3 — but the curator now sees a clean list of *valid* choices instead of a dead end).

**Warning signs:**
Fields where the validator rejects Claude's pick but the UI review screen shows no "did you mean X?" suggestion, even though X was in Claude's own alternatives array.

**Phase to address:**
Day 2 (validator).

---

### Pitfall 3: Trivial encoding/formatting differences produce false-positive "invalid" flags, eroding curator trust

**What goes wrong:**
A CRO exports `unit` as `"micromolar"`, `"uM"`, `"µM "` (trailing space), or `"UM"` (caps). A validator that does exact-match-only comparison against the reference dictionary (`ALLOWED_UNITS = {"µM", "nM", "%"}`) flags all of these as invalid, even though every one is unambiguously µM to a human. If most files trigger a wall of false "invalid" flags, the curator learns to stop reading them carefully — the yellow highlight loses meaning (alert fatigue), which is worse than not having the validator at all.

**Why it happens:**
Reference dictionaries are built for the canonical case, not the long tail of real-world spelling variants. Teams under time pressure hardcode a small allowed-set and assume Claude will always normalize casing before the validator sees it — which it usually will, but not always (temperature, edge-case prompts).

**How to avoid:**
Normalize (trim, casefold, common synonym map: `"uM"→"µM"`, `"micromolar"→"µM"`, `"pct"/"percent"→"%"`) *before* the exact-match check, and log/display when normalization occurred (see Pitfall 1 — normalization must be visible, not silent). Build the synonym map from the actual synthetic demo files plus a few adversarial variants, not just the happy path.

**Warning signs:**
More than ~1 in 5 fields flagged yellow on a file that a human would consider unambiguous at a glance. Track false-positive rate against the synthetic corpus before recording the demo.

**Phase to address:**
Day 2 (validator); verify against all 4+ synthetic lab files before Day 3.

---

### Pitfall 4: Column-signature key breaks on header reorder, whitespace, or case — the learning loop silently never fires

**What goes wrong:**
The demo's entire differentiator hinges on: lab X file #1 → yellow fields → curator confirms → lab X file #2 (same lab, same columns) → auto-mapped at confidence 1.0. If the signature is computed as an ordered, un-normalized concatenation of raw header strings (e.g., `"Compound ID|Result (uM)|Target"`), then a second file from the same lab with columns in a different order, or with `"compound id"` (lowercase, no underscore) vs `"Compound_ID"`, produces a *different* signature. The lookup misses, the second file shows yellow fields again, and the money-shot of the demo fails live.

**Why it happens:**
The simplest implementation of "signature" is `"|".join(columns)` or a hash of the raw header list — it works on the first test and looks done. Real CRO exports commonly reorder columns run-to-run (LIMS exports rarely guarantee column order) and vary whitespace/case in headers.

**How to avoid:**
Normalize each header (trim, casefold, collapse internal whitespace, strip trailing punctuation) *then* sort the normalized set before hashing, so the signature is order-independent and whitespace/case-independent. Treat the signature as `hash(sorted(normalize(h) for h in headers))`, not a positional string. Write a unit test that feeds the same header set in two different orders and two different cases and asserts identical signatures.

**Warning signs:**
Manually re-running the "second file from same lab" scenario with columns shuffled or re-cased produces yellow fields instead of the expected all-green auto-map. This is the single most important thing to test before recording video — it is the demo's climax.

**Phase to address:**
Day 2 (learning store) — test this explicitly, ideally with a dedicated unit test named after the demo scenario, before Day 3 starts.

---

### Pitfall 5: Signature is too coarse — different labs collide and the wrong profile is applied silently at confidence 1.0

**What goes wrong:**
The opposite failure of Pitfall 4: if the signature is based on something too generic (e.g., just column *count*, or just the set of *target fields* Claude mapped to, rather than the actual source header text), two different labs with superficially similar files ("6 columns including one that looks like an ID and one that looks like a result") collide on the same signature. Lab Y's first file gets auto-mapped using Lab X's learned profile — at confidence 1.0, meaning it bypasses human review entirely (Principle 3 says nothing needs confirming). A wrong mapping now flows through as if it were correct, which is the single worst failure mode for a tool whose whole pitch is "never guess silently."

**Why it happens:**
Teams sometimes generalize the signature to increase "hit rate" of the learning store, especially near a demo deadline where showing auto-mapping working across more files feels like a win. This directly trades away correctness for a more impressive-looking demo.

**How to avoid:**
The signature must be derived from the actual normalized source header *text* (Pitfall 4's fix), not from Claude's output or from coarse structural features. Never key on `lab_name` alone as a fallback — a lab profile only applies when the incoming file's normalized header signature exactly matches a previously *confirmed* one. If no exact match, fall through to full LLM mapping + validation; do not "fuzzy-apply" a nearby profile at full confidence. Fuzzy/partial matches (see Pitfall 4) should at most pre-fill suggestions with reduced confidence, never bypass the review gate.

**Warning signs:**
Auto-mapping fires (confidence 1.0, no yellow) on a file from a lab that has never had a confirmed mapping before. Any code path where `needs_confirmation` can become `False` without an *exact* signature match to a stored, human-confirmed profile.

**Phase to address:**
Day 2 (learning store design) — this is a design decision, not a bug to catch later; get the match semantics (exact-only) right before writing the SQLite schema.

---

### Pitfall 6: Export gate is enforced only in the React UI, not on the backend

**What goes wrong:**
Principle 3 ("nothing saved until all fields are clear") is implemented as a disabled Confirm button in React that re-enables once no cell is yellow. If the actual persistence/export call is a separate API endpoint, nothing stops it from being invoked directly (browser devtools, a stale tab, a second window, curl) while fields are still uncertain — the UI gate is cosmetic, not a real guarantee.

**Why it happens:**
Client-side state is the fastest way to get the "block until clear" behavior visible for the demo, and for a hackathon it is tempting to stop there since the video only shows the UI, not an adversarial bypass attempt.

**How to avoid:**
The backend confirm/export endpoint must independently recompute "are there any uncertain fields" from the mapping proposal + validator result before writing anything, and reject the request (4xx) if any field is still flagged. The React gate is a UX nicety; the server-side check is the actual enforcement of Principle 3.

**Warning signs:**
There exists a code path (endpoint, CLI flag) that writes a mapping to the learning store or an export file without first re-running validation server-side.

**Phase to address:**
Day 3 (review UI + confirm flow) — build the backend check in the same slice as the endpoint, not as a follow-up.

---

### Pitfall 7: A manual edit clears the yellow flag without re-validating the new value

**What goes wrong:**
Curator edits a yellow cell (e.g., corrects `assay_type` from Claude's guess to the right vocabulary term). The UI naively treats "user typed something" as "resolved" and turns the cell green — without re-running it through the reference-dictionary validator. If the curator fat-fingers an invalid value (typo, wrong casing), it now passes as confirmed and clean, defeating the entire point of the validator.

**Why it happens:**
It feels reasonable that a human-provided value doesn't need machine validation — "the human is the source of truth." But the reference dictionary exists precisely to catch typos and out-of-vocabulary values regardless of whether they came from Claude or a human under time pressure.

**How to avoid:**
Every edit — human or Claude-proposed — flows through the same validator before a field can turn green. The only thing that changes on human edit is that the "reason" text now says "human-provided" instead of Claude's original reasoning. Design this as an explicit "revalidate on change" event in the UI plan.

**Warning signs:**
A cell edited by a human can turn green even when the new value doesn't match any reference-dictionary entry.

**Phase to address:**
Day 3 (review UI) — must be part of the edit-cell interaction design, not bolted on after.

---

### Pitfall 8: Live LLM calls during demo recording introduce latency, nondeterminism, and single-take API failure risk

**What goes wrong:**
The money-shot ("messy file in → clean structure out in ~5s") is recorded as a genuinely live API call. Any one of: elevated API latency, a rate limit from earlier test runs, a subtly different response on retake (different confidence numbers, different flagged fields, different wording in `reason` text than what the narration describes), or a transient 5xx, can force a re-record — costly with ~4 days total and a hard deadline. Because structured output is not literally deterministic run-to-run even at fixed temperature, a rehearsed narration ("notice it flags `unit` because...") can mismatch what the live call actually returns.

**Why it happens:**
"Live and real" feels more honest/compelling for a hackathon video, and it is tempting to demo it live rather than plan for reliability. Teams underestimate how much API variance (and their own repeated testing eating into rate limits) compounds right before a deadline.

**How to avoid:**
Run the exact demo file through the exact pipeline several times beforehand and pick/lock a known-good, representative response; either (a) record on a successful live run after a dry-run rehearsal confirms stability, or (b) cache/replay the exact response used in the video (still real output from a real run — just not re-invoked live during the recording take) so narration and on-screen output always match. Set `temperature` low (structured-output tool-use is already fairly constrained) and pin the model version string used for the recorded run. Keep 1-2 backup demo files ready in case the primary one produces a confusing edge case on the day of recording. Budget API quota explicitly — don't burn it all on iteration the day before recording.

**Warning signs:**
No rehearsal run of the exact recording script has been done end-to-end; the model/version isn't pinned anywhere in code or notes; there's no fallback if the live call fails or returns something that doesn't match the narration.

**Phase to address:**
Day 4 (demo recording) — but the *capability* to pin/replay a known-good response should exist by end of Day 3 so Day 4 isn't the first time this is tested.

---

### Pitfall 9: Life-sciences-specific source-data hazards are treated as generic parsing problems instead of domain-aware validation targets

**What goes wrong:**
Several failure modes are specific to CRO assay data and easy to miss if the validator/parser is designed generically:
- **µM/nM scale ambiguity**: a value of `50` could be `50 µM` or `50 nM` — three orders of magnitude apart — and both are "plausible-looking" numbers, so a wrong unit doesn't look wrong. (Corroborated by public IC50/EC50 curation literature: unit transcription is cited as one of the dominant, non-automatically-detectable error classes in bioactivity databases.)
- **Date format ambiguity**: `03/04/2026` is March 4 (US) or April 3 (EU) depending on the lab's locale; Excel can also store dates as serial numbers that pandas may or may not auto-convert depending on cell formatting, silently producing an integer instead of a date.
- **Blank/duplicate headers**: Excel auto-renames duplicate columns (`Result`, `Result.1`, `Result.2` for replicate wells) and CRO exports frequently have literally blank header cells for a "notes" or merged-cell column — already partially handled by Day 1's `_clean_header()`, but the mapper/validator layer needs to know these represent legitimate business meaning (replicates), not junk to discard.
- **compound_id format variance**: batch suffixes, vendor prefixes, or salt-form annotations (`CPD-1023-B` vs `CPD-1023`) can make the "same" compound look like different IDs to a naive string match — relevant both to mapping confidence and (per Pitfall 4/5) to column-signature stability if IDs ever leak into signature logic.

**Why it happens:**
These are domain facts a generalist engineer wouldn't necessarily encode without explicit life-sciences context; a validator built only against the happy-path reference vocabulary (assay type + unit strings) won't catch a *scale* error, only a *vocabulary* error — `50` tagged as `unit: nM` when it should be `µM` still validates cleanly against `ALLOWED_UNITS` because `nM` is a legal unit, just the wrong one for that value.

**How to avoid:**
For unit inference specifically, keep Day 1's existing behavior of using value-range heuristics as a *signal to lower confidence and flag*, not to silently pick — a value like `50` with no explicit unit column should always be `needs_confirmation`, regardless of which unit Claude guesses. For dates, normalize to ISO 8601 at the parser boundary and flag (not silently coerce) anything ambiguous (day ≤ 12 and month ≤ 12 in a delimited date is inherently ambiguous — flag it). For duplicate/replicate columns, make sure the mapper prompt and validator both understand `n_replicates`-shaped column groups rather than treating each `Result.N` column as a mapping collision.

**Warning signs:**
A file where `unit` is missing entirely produces a confidently green field. A date field silently loses information (e.g., an Excel serial integer passes through as `45000` instead of a date). A file with 3 replicate `Result` columns causes the mapper to only pick one and silently discard the others with no flag.

**Phase to address:**
Day 2 (validator design should explicitly separate "vocabulary-valid" from "plausible" checks) and Day 4 (synthetic demo files should include at least one file exercising each of these hazards, to prove the flagging behavior on video).

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Hardcoded model/token constants in mapper (already present per `CONCERNS.md`) | Simpler code, one less config surface for the demo | Cannot swap models when deprecated/repriced; no per-environment tuning | Acceptable through the hackathon deadline; flag clearly as "move to env config" for any post-hackathon continuation |
| Column-signature = simple normalized hash with no fuzzy/partial matching | Fast to build, easy to test, demoable in one scenario | Any file that adds/drops a single column (e.g., a new QC column) never benefits from a prior confirmed profile — learning loop looks "brittle" beyond the scripted demo | Acceptable for the hackathon's scripted demo; call out explicitly as a known limitation in the README so it isn't mistaken for full production readiness |
| No retry/backoff on Anthropic API calls (already present per `CONCERNS.md`) | Less code, ships faster | A single transient 429/5xx kills the CLI run with no recovery — directly threatens the live-demo recording (Pitfall 8) | Never acceptable once a live/recorded demo depends on the call succeeding — at minimum add one retry with backoff before Day 4 |
| Validator hardcodes a small synonym/normalization map by hand instead of a general fuzzy-match library | Fast, fully deterministic, easy to reason about and test | Won't generalize past the specific synthetic files tested; a new lab's spelling variant reintroduces Pitfall 3 | Acceptable and arguably *correct* for this project — a small explicit list is auditable, which fits Principle 2 ("never guess silently") better than a black-box fuzzy matcher would |
| SQLite learning store with no schema migration story | One file, zero ops overhead, trivial to demo | Any post-hackathon change to the reference dictionary or target-field list leaves stale profiles applying outdated mappings silently | Acceptable through submission; if continued, version the `mapping_json` payload with a schema version field from day one |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|------------------|-------------------|
| Anthropic SDK (structured output) | Treating a schema-valid-but-semantically-wrong response (e.g., `confidence: 1.5`, an out-of-vocabulary `target_field`) as a code bug rather than an expected occasional case | Catch `pydantic.ValidationError` and unexpected enum values explicitly (already flagged in `CONCERNS.md`); treat as "Claude produced something the schema/domain doesn't accept" → surface a clear, recoverable message, don't let it crash the CLI/API mid-demo |
| Anthropic SDK (rate limits) | No handling for 429s beyond a generic exception; repeated local testing right before the deadline can exhaust quota | Add basic retry-with-backoff on 429/5xx; track roughly how many calls are "budgeted" for final testing + recording so the last hour isn't spent rate-limited |
| SQLite learning store | Building the lookup as a fuzzy/LIKE query on `lab_name` or partial signature match "for convenience" | Exact match only on the normalized signature (Pitfall 5); `lab_name` is metadata for display, not a matching key |
| React frontend ↔ backend confirm/export endpoint | Assuming the UI's disabled-button state is sufficient enforcement of "block until clear" | Re-validate server-side on every confirm/export call (Pitfall 6) |
| pandas/openpyxl parsing | Assuming Excel dates always parse as `datetime` — some cells resolve to raw serial integers depending on source formatting | Explicitly detect and convert Excel serial dates; flag anything that doesn't parse cleanly to ISO 8601 rather than passing an integer through as if it were a valid date |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Sequential per-sheet API calls (already flagged in `CONCERNS.md`) | Multi-sheet workbook ingestion feels slow; noticeable during live recording if the demo file has several sheets | Keep demo files to 1-2 sheets; note parallelization as a documented future improvement rather than solving it under deadline pressure | Becomes visibly bad above ~5-10 sheets in one workbook — irrelevant for a scripted 3-minute demo, worth a one-line README caveat |
| Sending all columns/rows for very wide tables (already flagged in `CONCERNS.md`) | Slower response, higher token cost, more room for the model to lose track of far-right columns | Cap sample columns for the demo corpus (synthetic files are hand-built, so this is controllable); document the cap rather than engineering a general solution | Matters if a real 100+ column CRO export is ever used — out of scope for the hackathon's bounded demo files |
| Learning-store lookup scanning all profiles for a fuzzy match "just in case" | Lookup latency grows with number of stored profiles; also reintroduces Pitfall 5's collision risk | Index on the exact normalized signature (a simple hash/string equality lookup is O(1) with a DB index) — never scan-and-fuzzy-compare at lookup time | Not a real risk at hackathon scale (a handful of profiles), but the *design smell* (fuzzy lookup) is worth avoiding regardless of scale because of the correctness risk, not just performance |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| API key read directly from env vars with no masking guarantee (already flagged in `CONCERNS.md`) | Key leaks via crash logs, error output, or a screen-recorded terminal during demo prep | Never print/log the raw env var; double-check terminal output isn't captured verbatim in the demo video or committed shell history |
| No path validation on uploaded/ingested files (already flagged in `CONCERNS.md`) | Path traversal if this ever accepts user-supplied paths beyond the CLI's trusted local use | Constrain ingestion to a known data directory once any upload/API surface exists (React UI in Day 3 introduces exactly this surface) |
| Raw cell values rendered unescaped in the React review grid | If a sheet contains a formula-like string (e.g., `=HYPERLINK(...)`), rendering it as literal text is safe, but re-exporting it to CSV without escaping reintroduces classic CSV/formula injection when the exported file is later opened in Excel | Escape/neutralize leading `=`, `+`, `-`, `@` characters on export, and never `dangerouslySetInnerHTML` raw cell values in React |
| `lab_name` or signature values interpolated into SQL by string formatting instead of parameterized queries | Classic SQL injection, however unlikely given controlled input for a hackathon demo | Use parameterized queries throughout the SQLite layer as a matter of habit, not because the demo data is adversarial |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|--------------|-------------------|
| Yellow highlight with no visible reason text | Curator sees *that* something is uncertain but not *why*, defeating Principle 2 ("never guess silently") and forcing them to re-derive Claude's reasoning themselves | Always show Claude's `reason` (or the validator's rejection reason) inline next to the flagged cell, per Principle 2 |
| Binary confirm/reject per field with no inline edit | Forces the curator to reject and start over for a field that's 90% right, which is slower than manual reformatting was — undermining the entire value proposition | Let the curator pick from Claude's ranked alternatives or type a correction directly in the cell, then re-validate (Pitfall 7) |
| Auto-mapped (learned) fields shown identically to freshly-proposed fields | Curator can't tell at a glance "this came from the learning store" vs "this is Claude's first guess," which undercuts the demo's core "look, it learned!" narrative | Visually distinguish learned/auto-mapped fields (e.g., a small badge: "auto-mapped from lab profile") so the learning-loop payoff is legible on video, not just functionally present |

## "Looks Done But Isn't" Checklist

- [ ] **No-LLM validator:** Often missing coverage of Claude's *alternatives*, not just the top pick — verify a rejected top pick with a valid alternative promotes cleanly (Pitfall 2)
- [ ] **Column-signature matching:** Often missing order/whitespace/case normalization — verify with a test that reorders and re-cases the same header set and asserts identical signatures (Pitfall 4)
- [ ] **Learning-store auto-map:** Often missing an "exact match only" guarantee — verify a *different* lab's file with superficially similar columns does NOT trigger auto-mapping at confidence 1.0 (Pitfall 5)
- [ ] **Export/confirm gate:** Often enforced only in the frontend — verify the backend endpoint independently rejects a confirm/export call while any field is still uncertain, e.g. via a direct API call bypassing the UI (Pitfall 6)
- [ ] **Manual field edit:** Often skips re-validation — verify editing a yellow cell to an invalid value keeps it flagged rather than turning it green (Pitfall 7)
- [ ] **Demo recording:** Often assumes the live call will "just work" on the day — verify a full dry-run of the exact recording script, end to end, at least once before the real recording session (Pitfall 8)
- [ ] **Unit/date handling:** Often validates vocabulary but not plausibility — verify a value with a missing/ambiguous unit or an ambiguous date format is flagged, not silently resolved (Pitfall 9)

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|------------------|
| Signature breaks on reorder/case (Pitfall 4) | LOW | Add normalization to the signature function and re-run the two-file demo scenario; no data migration needed since profiles can be recomputed/re-saved |
| Signature collision across labs (Pitfall 5) | MEDIUM | Tighten matching to exact-normalized-header equality; purge or namespace any already-stored profiles created under the looser scheme before recording the demo |
| Export gate bypassable via direct API call (Pitfall 6) | LOW | Add the server-side re-validation check to the confirm/export endpoint; this is a small, isolated addition to an already-existing endpoint |
| Live demo call fails/mismatches during recording (Pitfall 8) | MEDIUM | Fall back to a previously-recorded successful run's cached response for the on-screen output, or re-record after confirming API/network health; keep a backup demo file ready to swap in |
| False-positive validator flags erode trust in a recorded take (Pitfall 3) | LOW | Extend the normalization/synonym map with the specific variant that triggered the false positive, re-run against the full synthetic corpus, re-record only the affected segment |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|--------------------|----------------|
| 1. Validator silently auto-corrects | Day 2 (validator) | Code review: no path sets `needs_confirmation=False` while also rewriting the value |
| 2. Validator discards Claude's alternatives | Day 2 (validator) | Unit test: invalid top-pick + valid alternative → alternative promoted, field still yellow |
| 3. False-positive flags from trivial variants | Day 2 (validator) | Run validator against all synthetic demo files; false-positive rate near zero before Day 3 |
| 4. Signature breaks on reorder/case | Day 2 (learning store) | Unit test: same headers, different order/case → identical signature |
| 5. Signature collision across labs | Day 2 (learning store) | Unit test: two different labs' files never share a signature; auto-map never fires on an unconfirmed profile |
| 6. Export gate bypassable | Day 3 (review UI + confirm endpoint) | Integration test: direct API call to confirm/export with a yellow field present is rejected |
| 7. Edited field skips re-validation | Day 3 (review UI) | Manual/E2E test: editing a cell to an invalid value keeps it yellow |
| 8. Live demo reliability | Day 3 (capability) / Day 4 (execution) | Full dry-run of the recording script completed successfully at least once before the final take |
| 9. Life-sciences data hazards (unit scale, dates, duplicate headers) | Day 2 (validator/parser) + Day 4 (synthetic files) | At least one synthetic demo file explicitly exercises each hazard and produces the expected flag, not a silent resolution |

## Sources

- [The Ultimate Guide to Guardrails in GenAI](https://medium.com/@ajayverma23/the-ultimate-guide-to-guardrails-in-genai-securing-and-standardizing-llm-applications-1502c90fdc72) — LLM guardrail / requires-human-review pattern
- [LLM Guardrails: Strategies & Best Practices](https://leanware.co/insights/llm-guardrails) — rules-engine-has-veto-power pattern
- [LLM Guardrails in Production](https://www.kalviumlabs.ai/blog/guardrails-for-llm-applications/) — output guardrails routing ambiguous responses to human review
- [Fuzzy Match for Column Headers (Alteryx community)](https://community.alteryx.com/t5/Alteryx-Designer-Desktop-Discussions/Fuzzy-Match-but-for-Column-Headers-w-o-replacing-Spaces-amp/td-p/909979) — real-world header normalization pain points
- [Making Table Understanding Work in Practice (arXiv)](https://arxiv.org/pdf/2109.05173) — column/schema matching approaches
- [Human-in-the-loop in AI workflows: Meaning and patterns (Zapier)](https://zapier.com/blog/human-in-the-loop/) — synchronous/blocking review pattern
- [AI Human in the Loop: Production Oversight Patterns (Redis)](https://redis.io/blog/ai-human-in-the-loop/) — approve-before-side-effects principle
- [Human-in-the-Loop AI Agents: Implementation Patterns](https://www.buildmvpfast.com/blog/human-in-the-loop-ai-agents-implementation-patterns-2026) — edit-then-approve UI guidance
- [6 Tips for making a winning hackathon demo video (Devpost)](https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video) — demo video structuring for judges
- [Defeating Nondeterminism in LLM Inference](https://www.propelcode.ai/blog/defeating-nondeterminism-in-llm-inference-ramifications) — pinning model/version, golden-snapshot approach for reproducibility
- [Comparability of Mixed IC50 Data – A Statistical Analysis (PLOS ONE / PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3628986/) — unit transcription errors as a dominant, non-automatically-detectable class of curation error in bioactivity data
- [Why Changing from IC50 to pIC50 Will Change Your Life (CDD)](https://www.collaborativedrug.com/cdd-blog/why-changing-from-ic50-to-pic50-will-change-your-life) — log-scale nature of potency values and why raw-unit errors are easy to miss
- `.planning/codebase/CONCERNS.md` (2026-07-09) — project-specific gaps: reference dictionary not yet used to validate output, no confirmation/persistence path, unhandled Pydantic validation errors, no API retry logic, credential/security notes, performance bottlenecks

---
*Pitfalls research for: AI-assisted CRO assay data ingestion (AssayIngest)*
*Researched: 2026-07-09*
