"""Command-line entry point — the Day-1 demo: messy file in, clean draft out.

Parses a CRO file, asks the mapper for a proposal, and prints both a structured
JSON draft and a human review summary. Export stays blocked while any field is
yellow; the human confirms before anything is trusted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import anthropic

from . import canonical, service
from .domain.models import FieldMapping, MappingProposal
from .env import load_project_env
from .fields.loader import load as load_field_set
from .fields.models import FieldSet
from .learning.postgres_store import PostgresProfileStore
from .learning.signature import column_signature
from .learning.store import ProfileStore
from .mapping.mapper import propose_mapping
from .parsing.hint import StructuralHint, StructureQuestion
from .parsing.structure_assist import propose_structure
from .parsing.table import RawTable, parse, parse_file, sheet_names
from .persistence.engine import new_session
from .validation.validator import validate

_GREEN = "✓"  # ✓ clear
_YELLOW = "⚠"  # ⚠ needs confirmation

#: Provenance values a per-table mapping resolution can carry (D-08) -- the
#: manifest a future export step (03-03) reads records which one applied.
_PROVENANCE_AUTO_APPLIED = "auto-applied-from-profile"
_PROVENANCE_FRESH_CLAUDE = "fresh-claude"
_MISSING_CREDENTIALS = "missing-credentials"


def proposal_to_dict(proposal: MappingProposal, provenance: str | None = None) -> dict:
    """Serialise a proposal to the JSON draft a downstream step would consume."""
    return {
        "ready": proposal.is_ready,
        "source_columns": proposal.source_columns,
        "field_mappings": [_field_to_dict(m) for m in proposal.field_mappings],
        "provenance": provenance,
    }


def _field_to_dict(mapping: FieldMapping) -> dict:
    return {
        "target_field": mapping.target_field,
        "source_column": mapping.source_column,
        "confidence": mapping.confidence,
        "reasoning": mapping.reasoning,
        "needs_confirmation": mapping.needs_confirmation,
        "inferred_value": mapping.inferred_value,
        "alternatives": [
            {"source_column": c.source_column, "confidence": c.confidence}
            for c in mapping.alternatives
        ],
    }


def render_report(proposal: MappingProposal) -> str:
    """A colour-coded review summary: one line per field, then the gate."""
    lines = ["Proposed mapping (Claude proposes, you dispose):", ""]
    lines.extend(_render_field(m) for m in proposal.field_mappings)
    lines.append("")
    lines.append(_render_gate(proposal))
    return "\n".join(lines)


def _render_field(mapping: FieldMapping) -> str:
    marker = _YELLOW if mapping.needs_confirmation else _GREEN
    source = _describe_source(mapping)
    head = (
        f"  {marker} {mapping.target_field:<13} <- {source}  "
        f"(conf {mapping.confidence:.2f})"
    )
    if not mapping.needs_confirmation:
        # VAL-03/D-04: a clear field's validator note (an objection's
        # explicit absence, or "no declared constraints to check") is still
        # shown -- the validator's silence must never look like it never ran.
        return _with_validator_note(head, mapping)
    detail = [head, f"      reason: {mapping.reasoning}"]
    if mapping.validator_note:
        detail.append(f"      validator_note: {mapping.validator_note}")
    if mapping.alternatives:
        options = ", ".join(
            f"{_label(c.source_column)} ({c.confidence:.2f})"
            for c in mapping.alternatives
        )
        detail.append(f"      options: {options}")
    return "\n".join(detail)


def _with_validator_note(head: str, mapping: FieldMapping) -> str:
    if not mapping.validator_note:
        return head
    return "\n".join([head, f"      validator_note: {mapping.validator_note}"])


def _label(source_column: str) -> str:
    """Render a source header, naming the blank (unlabelled) column explicitly."""
    return source_column if source_column else "(blank header)"


def _describe_source(mapping: FieldMapping) -> str:
    if mapping.source_column is not None:
        return f"'{mapping.source_column}'"
    if mapping.inferred_value is not None:
        return f"inferred '{mapping.inferred_value}' (no column)"
    return "(no match)"


def _render_gate(proposal: MappingProposal) -> str:
    if proposal.is_ready:
        return f"{_GREEN} READY: all fields clear — safe to confirm and export."
    n = len(proposal.unclear_fields)
    names = ", ".join(m.target_field for m in proposal.unclear_fields)
    return (
        f"{_YELLOW} BLOCKED: {n} field(s) need confirmation ({names}). "
        f"Export stays disabled until resolved."
    )


def resolve_tables(path: str, sheet: str | None = None) -> list[RawTable]:
    """Decide which tables to ingest — one per Excel sheet, so none is skipped.

    A CSV yields a single table. A one-sheet workbook yields that sheet. A
    multi-sheet workbook yields every sheet (unless `sheet` names just one) —
    the tool never collapses a workbook to its first sheet silently.
    """
    names = sheet_names(path)
    if not names:  # CSV
        return [parse_file(path)]
    if sheet is not None:
        return [parse_file(path, sheet)]
    if len(names) == 1:
        return [parse_file(path, names[0])]
    return [parse_file(path, name) for name in names]


def resolve_or_ask(
    path: str, sheet: str | None = None, hint: StructuralHint | None = None
) -> list[RawTable] | StructureQuestion:
    """Resolve a file's structure — CSV or Excel — or return the human's
    structural question.

    Both file types now run through the same `parsing.table.parse()`
    structural engine end-to-end: CSV delimiter/locale detection, and for
    Excel, sheet selection + header detection + drawing detection (D-05,
    D-08, D-09). v1 targets one chosen table per file (PROJECT.md Out of
    Scope) — `parse()` picks the one data sheet, or asks when genuinely
    ambiguous; it never loops every sheet silently.
    """
    outcome = parse(path, sheet=sheet, hint=hint)
    if isinstance(outcome, StructureQuestion):
        return outcome
    return [outcome]


def run(
    path: str,
    sheet: str | None = None,
    hint: StructuralHint | None = None,
    field_set: FieldSet | None = None,
    *,
    store: ProfileStore | None = None,
    save_profile: bool = False,
    strictness: str = "strict",
    export: bool = False,
    output_dir: str | None = None,
    headers_only: bool = False,
) -> int:
    """Parse → (auto-apply | propose) → validate → print, once per sheet.
    Returns a process exit code.

    `field_set` is optional at this Python-API layer so early-exit paths
    (missing file, structural question) never need one; `main()` requires
    `--fields` before calling here, so the mapping step always has a real
    `FieldSet` by the time it runs.

    The credentials check that used to run here unconditionally now lives
    per-table inside `_map_one` (Pitfall 3, D-10/P2): a matched profile
    auto-applies with no Anthropic client built and no credentials checked
    at all -- a profile-only user needs no API key configured.

    `strictness` (D-11) threads through to the validator on every table:
    "strict" (default) checks every row; "lenient" relaxes row coverage
    only, never an in-scope objection's severity.

    `export`/`output_dir` (EXPORT-02/03/04, D-09/P1): the tool never writes
    on its own -- `export=True` is the one explicit human command that
    unlocks writing CSV/.xlsx/JSON + manifest.json, and only once
    `proposal.is_ready`. `output_dir` defaults to beside the source file
    when omitted (`export=True, output_dir=None`).

    `headers_only` (D-10, P2, CR-01): threads through to `propose_mapping` on
    the fresh-Claude mapping branch, AND to `_ask_and_report` on the
    structure-question branch -- both are send sites that can reach Claude,
    so both must honour the flag. An auto-applied profile hit already sends
    nothing (Pattern 5), so the flag is a no-op there.

    LEARN-06/SC5: when parsing returns a `StructureQuestion` and the human
    gave no explicit `hint`, `_try_replay_saved_hint` gets one attempt to
    resolve it from a saved profile's own structural hint before the human
    is asked -- an explicit `hint` always wins and is never routed there
    (D-02: a human's own answer is never second-guessed by a replay).

    `store` is the test-injection seam (constructor injection on the ABSTRACT
    `ProfileStore`, never the concrete class -- dependencies point toward the
    domain). Production passes nothing and this opens its own session; a test
    passes a store already bound to its own transaction.

    SESSION LIFETIME. When a `store` is injected, or there is no `field_set`, this
    opens NO SESSION AT ALL -- guarded explicitly below, not merely implied by
    ordering. That matters: an unconditional session would make every CLI test open
    a live connection to the DEV database that it never uses, and against a stopped
    Postgres those tests would fail for a reason unrelated to what they test.
    Otherwise the session's lifetime is exactly this CLI invocation.
    """
    if store is not None or field_set is None:
        # No field set means no learning-loop key can be computed at all, so there is
        # nothing to look up and no reason to open a connection.
        return _run_with_store(
            path, sheet, hint, field_set, store,
            save_profile=save_profile, strictness=strictness,
            export=export, output_dir=output_dir, headers_only=headers_only,
        )
    with new_session() as session:
        return _run_with_store(
            path, sheet, hint, field_set, PostgresProfileStore(session),
            save_profile=save_profile, strictness=strictness,
            export=export, output_dir=output_dir, headers_only=headers_only,
        )


def _run_with_store(
    path: str,
    sheet: str | None,
    hint: StructuralHint | None,
    field_set: FieldSet | None,
    store: ProfileStore | None,
    *,
    save_profile: bool,
    strictness: str,
    export: bool,
    output_dir: str | None,
    headers_only: bool,
) -> int:
    """`run()`'s body, once the store question is settled -- one level of
    abstraction: this one decides what to DO, never where the store came from."""
    try:
        outcome = resolve_or_ask(path, sheet, hint)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if isinstance(outcome, StructureQuestion):
        if hint is None:
            export_dir = _resolve_export_dir(path, export, output_dir)
            replayed = _try_replay_saved_hint(
                path, sheet, field_set, store,
                save_profile=save_profile, strictness=strictness,
                export_dir=export_dir, headers_only=headers_only,
            )
            if replayed is not None:
                return replayed
        return _ask_and_report(outcome, headers_only=headers_only)
    tables = outcome

    export_dir = _resolve_export_dir(path, export, output_dir)
    return _map_and_report(
        tables, field_set, store=store, save_profile=save_profile, hint=hint,
        strictness=strictness, export_dir=export_dir, headers_only=headers_only,
    )


def _resolve_export_dir(path: str, export: bool, output_dir: str | None) -> Path | None:
    """`None` means `--export` was never given -- the tool writes nothing on
    any other path (P1). `output_dir` omitted defaults to beside the source
    file, matching D-09's stated default."""
    if not export:
        return None
    return Path(output_dir) if output_dir else Path(path).parent


def _try_replay_saved_hint(
    path: str,
    sheet: str | None,
    field_set: FieldSet | None,
    store: ProfileStore | None,
    *,
    save_profile: bool,
    strictness: str,
    export_dir: Path | None,
    headers_only: bool,
) -> int | None:
    """LEARN-06/SC5: when parsing hit an unresolved `StructureQuestion` and
    the human gave no explicit `--hint`, try every saved profile's
    structural hint for this field set and accept the FIRST one whose
    re-parsed table reproduces THAT profile's exact stored
    `column_signature` -- the same exact-signature guarantee LEARN-03/04
    already require for mapping auto-apply (P1 fail-closed), applied here to
    the hint itself: reparsing successfully is not enough on its own, since
    a hint saved against one file can happen to also resolve a structurally
    similar but genuinely different file (Pitfall: a hint is not a
    fingerprint, a column signature is).

    Returns `None` -- never guesses, never raises -- when no candidate hint
    reproduces its own profile's signature (or there is no `field_set`/store
    to look up against at all), so the caller falls through to asking the
    human exactly as it did before this replay existed.
    """
    if field_set is None or store is None:
        return None
    for profile in store.list_for_field_set(field_set.signature):
        if profile.structural_hint is None:
            continue
        tables = _reparse_with_hint(path, sheet, profile.structural_hint)
        if tables is None or column_signature(tables[0].headers) != profile.column_signature:
            continue
        print(
            f"{_GREEN} replayed saved structural hint from profile "
            f"{profile.profile_id} (no re-ask)"
        )
        return _map_and_report(
            tables, field_set, store=store, save_profile=save_profile,
            hint=profile.structural_hint, strictness=strictness,
            export_dir=export_dir, headers_only=headers_only,
        )
    return None


def _reparse_with_hint(
    path: str, sheet: str | None, hint: StructuralHint
) -> list[RawTable] | None:
    """One replay candidate's parse attempt -- a miss (still ambiguous, or
    the file no longer even parses at all under this hint) is a `None`
    result for THIS candidate, never a crash: a stale or unrelated-file hint
    must not take down the whole run (fail-closed, LEARN-06).

    `IndexError` is caught alongside the two errors `resolve_or_ask` itself
    raises: `header_row_index` is human/profile-supplied and unbounded by
    construction (PARSE-06 "an explicit hint is always honored"), and this
    is the one call site that now feeds a hint into `parse()` WITHOUT a
    human having just chosen it for THIS file -- a hint saved against a
    9-row file replayed against a 3-row one is exactly the kind of mismatch
    this function exists to survive rather than crash on.
    """
    try:
        outcome = resolve_or_ask(path, sheet, hint)
    except (FileNotFoundError, ValueError, IndexError):
        return None
    if isinstance(outcome, StructureQuestion):
        return None
    return outcome


def _ask_and_report(question: StructureQuestion, *, headers_only: bool = False) -> int:
    """Print a structural question instead of crashing or guessing (D-08).

    Asking is the caller's job, not the parser's — the CLI is one possible
    renderer of the same `StructureQuestion` object a future API/UI will
    receive verbatim (D-06). The question is enriched with a Claude pre-fill
    when available (D-01 layer 2), but enrichment only ever sets `proposal`
    — nothing is auto-applied; printing is as far as `run()` goes. Exit code
    4 is dedicated to "structure unresolved", never reused for
    parse/credential/mapping errors (codes 2/3/1).

    `headers_only` (D-10, P2, CR-01): `_enrich_question` is the only send
    site on this path, and it embeds `question.evidence_rows` -- raw source
    cell values -- in the Claude request. The privacy guarantee must hold on
    EVERY path, not only the mapping one, so enrichment is skipped entirely
    here rather than merely stripped, keeping this one condition the sole
    place that decides whether evidence ever leaves the machine.
    """
    if not headers_only:
        question = _enrich_question(question)
    print(json.dumps(question.to_dict(), indent=2, ensure_ascii=False))
    print()
    print(_render_question(question))
    return 4


def _enrich_question(
    question: StructureQuestion, client: anthropic.Anthropic | None = None
) -> StructureQuestion:
    """Pre-fill a not-confident question with a Claude structural proposal
    (D-01 layer 2) — strictly advisory; the human still confirms (D-02).

    Degrades gracefully to the deterministic question, unchanged, whenever
    Claude isn't available: no client and no configured credentials, or the
    SDK call itself fails. Reuses `_map_one`'s AuthenticationError/APIError
    handling shape so a missing key never crashes the CLI (D-04, T-01-10).
    """
    if client is None and not service.has_credentials():
        return question
    try:
        proposal = propose_structure(_render_question_evidence(question), client=client)
    except anthropic.AuthenticationError:
        return question
    except (anthropic.APIError, ValueError):
        return question
    return dataclasses.replace(question, proposal=proposal)


def _render_question_evidence(question: StructureQuestion) -> str:
    """Build the Claude request body from a `StructureQuestion`'s own raw
    evidence — the same rows and reasoning a human would read (D-07)."""
    lines = [f"Unsure about: {question.unsure_about}", f"Reason: {question.reason}", ""]
    if question.evidence_rows:
        lines.append("Raw evidence rows:")
        lines.extend(f"  {row}" for row in question.evidence_rows)
    return "\n".join(lines)


def _render_question(question: StructureQuestion) -> str:
    lines = [
        "Structural question — the tool is unsure and needs a hint "
        "(Claude proposes, you dispose):",
        "",
        f"  {_YELLOW} unsure about: {question.unsure_about}",
        f"      reason: {question.reason}",
        f"      confidence: {question.confidence:.2f}",
    ]
    if question.proposal is not None:
        lines.append(f"      proposal: {question.proposal.to_dict()}")
    if question.alternatives:
        options = ", ".join(str(alt.to_dict()) for alt in question.alternatives)
        lines.append(f"      alternatives: {options}")
    if question.evidence_rows:
        lines.append("      evidence rows:")
        lines.extend(f"        {row}" for row in question.evidence_rows[:5])
    lines.append("")
    lines.append(
        f"{_YELLOW} BLOCKED: structure unresolved. Nothing was mapped or exported."
    )
    lines.extend(_render_answer_hint(question))
    return "\n".join(lines)


def _render_answer_hint(question: StructureQuestion) -> list[str]:
    """Show the exact `--hint` flags that answer this question.

    A question the human cannot answer is worse than no question at all — the
    tool must say how to proceed, not merely that it stopped (PARSE-06). When
    nothing can proceed, it says that instead of offering a flag that would
    silently change nothing.
    """
    if not question.answerable_by_hint:
        return ["", "  This file's structure is unsupported in v1 — "
                "no structural hint resolves it."]
    flags = _hint_to_flags(question.proposal)
    if not flags:
        return []
    return ["", f"  To proceed, re-run with: {' '.join(flags)}"]


def _hint_to_flags(hint: StructuralHint | None) -> list[str]:
    """Render only the dimensions a hint actually pins down."""
    if hint is None:
        return []
    values = hint.to_dict()
    return [
        f"--hint {key}={values[attribute]!s}"
        for key, attribute in _HINT_KEYS.items()
        if values.get(attribute) is not None
    ]


def _map_and_report(
    tables: list[RawTable],
    field_set: FieldSet | None,
    *,
    store: ProfileStore | None = None,
    save_profile: bool = False,
    hint: StructuralHint | None = None,
    strictness: str = "strict",
    export_dir: Path | None = None,
    headers_only: bool = False,
) -> int:
    """Map each table and print its draft; worst per-table exit code wins."""
    multi = len(tables) > 1
    worst = 0
    for index, table in enumerate(tables, start=1):
        if multi:
            print(f"===== sheet {index}/{len(tables)}: "
                  f"{table.sheet_name} =====")
        if table.row_count == 0:
            print("  (skipped: sheet has no data rows)\n")
            continue
        worst = max(
            worst,
            _map_one(
                table, field_set, store=store, save_profile=save_profile, hint=hint,
                strictness=strictness, export_dir=export_dir, headers_only=headers_only,
            ),
        )
        print()
    return worst


def _resolve_proposal(
    table: RawTable,
    field_set: FieldSet | None,
    store: ProfileStore | None,
    *,
    headers_only: bool = False,
) -> tuple[MappingProposal | None, str]:
    """The per-table auto-apply/fresh-Claude branch (LEARN-03/04, D-05/D-08)
    -- a thin CLI wrapper around `service.resolve_table_mapping` (04-01):
    the decision logic itself now lives there so a future API route can
    reuse it without importing this private function. This wrapper's own
    job is only the CLI's own rendering (the "applied saved profile ... (no
    Claude call)" announcement) and translating `service`'s typed
    `MissingCredentialsError` back into the sentinel tuple `_map_one`
    already expects.

    Returns `(proposal, provenance)` on success, or `(None,
    "missing-credentials")` when the fresh-Claude path is needed but no
    credentials are configured -- the caller decides how to report that.
    Auto-apply constructs no Anthropic client and checks no credentials at
    all (Pattern 5/Pitfall 3): the credential check only ever runs on the
    miss branch, immediately before a Claude call is actually about to
    happen, so a multi-sheet workbook where one sheet hits a profile and
    another misses only ever gates the sheet that truly needs Claude.

    `headers_only` (D-10, P2) only ever reaches `propose_mapping` on this
    miss branch -- a profile hit already sends nothing to Claude at all, so
    the flag is a no-op there by construction, not by a separate check.

    Passes this module's own `propose_mapping` reference through as
    `propose_mapping_fn` -- so `monkeypatch.setattr(cli, "propose_mapping",
    ...)` still governs what actually gets called, unaffected by
    `service.py`'s own default import of the same function.
    """
    try:
        proposal, provenance, profile_id = service.resolve_table_mapping(
            table, field_set, store,
            headers_only=headers_only, propose_mapping_fn=propose_mapping,
        )
    except service.MissingCredentialsError:
        return None, _MISSING_CREDENTIALS
    if provenance == _PROVENANCE_AUTO_APPLIED:
        print(f"{_GREEN} applied saved profile {profile_id} (no Claude call)")
    return proposal, provenance


def _map_one(
    table: RawTable,
    field_set: FieldSet | None,
    *,
    store: ProfileStore | None = None,
    save_profile: bool = False,
    hint: StructuralHint | None = None,
    strictness: str = "strict",
    export_dir: Path | None = None,
    headers_only: bool = False,
) -> int:
    try:
        proposal, provenance = _resolve_proposal(
            table, field_set, store, headers_only=headers_only
        )
    except anthropic.AuthenticationError:
        print("error: Anthropic rejected the credentials (check ANTHROPIC_API_KEY).",
              file=sys.stderr)
        return 3
    except (anthropic.APIError, ValueError) as exc:
        print(f"error: mapping failed for {table.label}: {exc}", file=sys.stderr)
        return 1

    if provenance == _MISSING_CREDENTIALS:
        print(
            "error: no Anthropic credentials. Set ANTHROPIC_API_KEY to run the "
            "mapper.",
            file=sys.stderr,
        )
        return 3

    if field_set is not None:
        # D-03: the validator runs on EVERY value, on BOTH the fresh-Claude
        # and the auto-applied-profile branches -- a profile's or Claude's
        # own confidence never exempts a value from a declared constraint.
        # Runs before any output so the printed draft/review already
        # reflects the validated (possibly re-flagged) mapping.
        proposal = validate(table, proposal, field_set, strictness=strictness)

    print(json.dumps(proposal_to_dict(proposal, provenance), indent=2, ensure_ascii=False))
    if field_set is not None:
        # EXPORT-01: the tidy canonical table Phase 3's exports all derive
        # from -- the messy-in / clean-out money shot, alongside the draft.
        #
        # SHEET-03/D-11-15: every ingest records where its rows came from, the
        # CLI included -- a traceability column that only sometimes exists is
        # not a traceability column. Unlike the API path (service.py), the CLI
        # never parses a tempfile, so `source_name` IS the real file's name and
        # is the honest fallback for a source with no worksheet (a CSV).
        source_sheet = table.origin_sheet or table.source_name
        tidy = canonical.assemble(table, proposal, field_set, source_sheet=source_sheet)
        print()
        print(json.dumps(tidy.to_dict(), indent=2, ensure_ascii=False))
    print()
    print(render_report(proposal))
    if save_profile:
        _save_profile_if_ready(store, field_set, table, proposal, hint)
    if export_dir is not None:
        if field_set is None:
            print(f"{_YELLOW} not exported: no field set available (missing --fields).")
        else:
            _export_if_ready(export_dir, table, field_set, proposal, tidy, provenance, strictness)
    # D-23: a proposed-but-unclear mapping is BLOCKED, never a silent success.
    return 0 if proposal.is_ready else 5


def _save_profile_if_ready(
    store: ProfileStore | None,
    field_set: FieldSet | None,
    table: RawTable,
    proposal: MappingProposal,
    hint: StructuralHint | None,
) -> None:
    """LEARN-02/06, D-06: saving is blocked unless the mapping is fully
    clear -- a yellow field's column-to-field association is not yet a
    curator-confirmed fact. Any structural hint the file needed (D-07) is
    persisted with the profile so the same odd layout parses automatically
    next time.

    A thin CLI wrapper (04-01): the persist-and-gate logic itself lives in
    `service.save_profile_if_ready`, which raises typed exceptions instead
    of printing -- this function's only job is translating those into the
    CLI's existing messages.
    """
    try:
        profile_id = service.save_profile_if_ready(store, field_set, table, proposal, hint)
    except service.NoStoreError:
        print(f"{_YELLOW} not saved: no profile store available (missing --fields).")
        return
    except service.NotReadyError:
        print(f"{_YELLOW} not saved: mapping is not fully clear yet (D-06).")
        return
    print(f"{_GREEN} saved profile {profile_id} for future auto-apply.")


def _export_if_ready(
    export_dir: Path,
    table: RawTable,
    field_set: FieldSet,
    proposal: MappingProposal,
    tidy: canonical.CanonicalTable,
    provenance: str,
    strictness: str,
) -> None:
    """EXPORT-02/03/04, D-09/P1: only ever called when `--export` was
    explicit -- the tool never writes on its own. A not-ready mapping
    writes nothing; the caller's own `is_ready` gate (exit 5) already
    reports the block, so this only adds a matching export-specific note.
    Every writer takes the one canonical `tidy` table (D-15) -- nothing
    here re-derives records from `table`/`proposal` directly.

    A thin CLI wrapper (04-01): the write-only-when-ready logic itself
    lives in `service.export`, which raises `NotReadyError` instead of
    printing -- this function's only job is translating that into the
    CLI's existing message.
    """
    try:
        service.export(export_dir, table, field_set, proposal, tidy, provenance, strictness)
    except service.NotReadyError:
        print(f"{_YELLOW} not exported: mapping is not fully clear yet (D-09).")
        return
    print(f"{_GREEN} exported to {export_dir} (CSV, .xlsx, JSON, manifest.json).")


#: The structural dimensions `--hint` can pin down, mapped to the
#: `StructuralHint` field each one fills.
_HINT_KEYS = {
    "header-row": "header_row_index",
    "sheet": "sheet_name",
    "delimiter": "delimiter",
    "decimal": "decimal_separator",
}


def _hint_from_args(hints: list[str]) -> StructuralHint | None:
    """Turn repeated `--hint key=value` flags into a `StructuralHint` (PARSE-06).

    This is the CLI's rendering of the answer a browser form will collect in
    Phase 4 — the same `StructuralHint` object travels on either path (D-06,
    D-08). A malformed flag raises `ValueError`; unresolved structure does
    not (D-05).
    """
    if not hints:
        return None
    fields: dict[str, str | int] = {}
    for item in hints:
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError(f"Cannot apply the hint '{item}': expected key=value")
        if key not in _HINT_KEYS:
            raise ValueError(
                f"Cannot apply an unknown structural hint '{key}' — "
                f"expected one of: {', '.join(sorted(_HINT_KEYS))}"
            )
        fields[_HINT_KEYS[key]] = _coerce_hint_value(key, value)
    return StructuralHint(**fields)


def _coerce_hint_value(key: str, value: str) -> str | int:
    """`header-row` is a 0-based row index; every other dimension is literal."""
    if key != "header-row":
        return value
    try:
        return int(value)
    except ValueError:
        raise ValueError(
            f"Cannot apply the hint header-row='{value}': expected a "
            "0-based row number"
        ) from None


def main() -> None:
    # Loaded here, as the FIRST statement of main() -- deliberately NOT at
    # module import and NOT inside run(). run() is what the pytest suite
    # calls directly (test_cli_run.py and friends), so keeping the load
    # confined to main() leaves every existing test's environment semantics
    # exactly as they were before this existed; only a real `assayingest`
    # invocation (main()) picks up the repo-root .env.
    load_project_env()
    parser = argparse.ArgumentParser(
        prog="assayingest",
        description="Map a CRO assay CSV/Excel file to target fields with Claude.",
    )
    parser.add_argument("file", help="Path to the CSV or Excel file to ingest.")
    parser.add_argument(
        "--sheet",
        default=None,
        help="For a multi-sheet Excel workbook, ingest only this sheet "
        "(default: every sheet).",
    )
    parser.add_argument(
        "--hint",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Answer a structural question so the tool can proceed. Repeatable. "
        f"Keys: {', '.join(sorted(_HINT_KEYS))}. "
        "Example: --hint header-row=4 --hint decimal=,",
    )
    parser.add_argument(
        "--fields",
        required=True,
        metavar="PATH",
        help="Path to a YAML or JSON field-set file declaring the target "
        "fields to map onto (e.g. presets/assay-potency.yaml).",
    )
    parser.add_argument(
        "--save-profile",
        action="store_true",
        help="Save this file's confirmed mapping as a profile for future "
        "auto-apply. Refused unless every field is clear (D-06).",
    )
    parser.add_argument(
        "--strictness",
        choices=["strict", "lenient"],
        default="strict",
        help="Validator row coverage (D-11): 'strict' (default) checks "
        "every row; 'lenient' checks a sample only -- an in-scope "
        "violation is never softened, only how many rows are scanned.",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export the confirmed mapping as CSV/.xlsx/JSON + manifest.json "
        "(D-09). Refused (writes nothing) unless every field is clear -- "
        "the tool never writes on its own.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        metavar="DIR",
        help="Directory --export writes into (default: beside the source file).",
    )
    parser.add_argument(
        "--headers-only",
        action="store_true",
        help="Privacy mode (D-10): send Claude the column headers only -- "
        "zero data values. Mapping confidence may drop (more fields need "
        "confirmation), but no cell value leaves the machine. A saved "
        "profile's auto-apply path already sends nothing, so this only "
        "affects a fresh-Claude call.",
    )
    args = parser.parse_args()
    try:
        hint = _hint_from_args(args.hint)
        field_set = load_field_set(args.fields)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(
        run(
            args.file,
            args.sheet,
            hint,
            field_set,
            save_profile=args.save_profile,
            strictness=args.strictness,
            export=args.export,
            output_dir=args.output_dir,
            headers_only=args.headers_only,
        )
    )


if __name__ == "__main__":
    main()