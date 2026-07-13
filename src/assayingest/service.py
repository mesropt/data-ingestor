"""Orchestration used by both the CLI and the API — decides, never renders.

`cli.py`'s private, print-coupled orchestration (`_resolve_proposal`,
`_map_one`, `_save_profile_if_ready`, `_export_if_ready`) both *decided* what
to do and *rendered* the result to stdout in the same function. That mixing
is fine for a single CLI adapter, but `.claude/CLAUDE.md`'s own convention
("Public API is everything not prefixed with `_`") makes it a boundary
violation for a second adapter (a future `api/` package) to import a
`cli._foo` name directly — and several of those functions print to stdout,
which is wrong for a function an HTTP endpoint calls.

Every function here returns plain data (a domain object, a frozen result
dataclass) or raises a typed exception; it prints nothing and writes to disk
only when a writer function (`export`) is explicitly called. `cli.py` and
the eventual FastAPI routes both call these same functions, then each
renders the result its own way (print vs JSON response) — the "decide vs
render" split PATTERNS.md's Pattern 1 describes.

`propose_mapping` is imported here exactly the way `cli.py` used to
(`from .mapping.mapper import propose_mapping`), so a test can
`monkeypatch.setattr(service, "propose_mapping", ...)` with zero new test
infrastructure — the same idiom `tests/test_cli_run.py` already established
for `cli.propose_mapping`. `cli.py` itself keeps its own `propose_mapping`
import (for its own monkeypatch seam) and threads its own reference into
`resolve_table_mapping` as an override, so a test patching `cli.propose_mapping`
still governs what the CLI actually calls, unaffected by this module's
default.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import canonical
from .canonical import CanonicalTable
from .domain.models import (
    Alias,
    DateFormatConflict,
    DateFormatQuestion,
    FieldMapping,
    MappingProposal,
    ReconcileConflict,
    ReconcileQuestion,
    Schema,
)
from .export.writers import build_manifest, write_csv, write_json, write_xlsx
from .fields.loader import MAX_FIELDS
from .fields.loader import from_dict as _field_dict_to_field_set
from .fields.models import Field, FieldSet
from .learning.profile import LearnedProfile
from .learning.reconstruct import reconstruct_proposal, stored_mapping_from
from .learning.schema_store import SchemaStore
from .learning.signature import _normalise_header, column_signature
from .learning.store import ProfileStore
from .mapping.mapper import propose_mapping
from .parsing.hint import StructuralHint, StructureQuestion
from .parsing.structure import date_order
from .parsing.structure.date_order import DateOrder
from .parsing.table import RawTable, parse
from .validation.validator import validate

#: Env vars the Anthropic SDK resolves credentials from (first match wins) --
#: mirrors cli.py's former `_CREDENTIAL_ENV_VARS`, now the single owner of
#: this check so the CLI's structural-assist enrichment and a future API
#: `deps.py` both reuse it instead of re-deriving a second copy.
_CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

#: Provenance values a per-table mapping resolution can carry (D-08) -- the
#: manifest / a future API response records which one applied.
_PROVENANCE_AUTO_APPLIED = "auto-applied-from-profile"
_PROVENANCE_FRESH_CLAUDE = "fresh-claude"

#: D-10-03/INGEST-02: the provenance a Python-first-crosswalked mapping
#: carries when the vendor-agnostic pre-fill covered EVERY field and zero
#: Claude calls were made -- the demo money shot. A PARTIAL pre-fill keeps
#: `_PROVENANCE_FRESH_CLAUDE`; the `Escalation` counts on `MapResult` carry
#: the honest python-vs-claude breakdown in that case.
_PROVENANCE_PYTHON_FIRST = "python-first-crosswalk"

#: Provenance a reconcile-produced mapping carries (D-08-02): a proposal whose
#: covered columns were pre-filled deterministically from the target Schema's
#: crosswalk (alias match at confidence 1.0), with Claude filling only the rest.
_PROVENANCE_RECONCILED = "reconciled-from-crosswalk"


def has_credentials() -> bool:
    """True if the SDK can find a key without constructing a client first.

    The one credential check every send site shares: the fresh-Claude
    mapping branch (`resolve_table_mapping`) and the CLI-only structural
    enrichment (`cli._enrich_question`) both call this instead of each
    keeping their own copy of `_CREDENTIAL_ENV_VARS`.
    """
    return any(os.environ.get(var) for var in _CREDENTIAL_ENV_VARS)


class MissingCredentialsError(Exception):
    """Raised on the fresh-Claude branch when no Anthropic credentials are
    configured. Replaces the `(None, "missing-credentials")` sentinel tuple
    `cli._resolve_proposal` used to return -- a caller now catches a typed
    exception instead of comparing a magic string."""


class NotReadyError(Exception):
    """Raised by every P1 gate (`confirm`, `save_profile_if_ready`,
    `export`) when asked to act on a mapping that is not yet fully clear.

    `unclear_fields` carries the actual `FieldMapping` objects still yellow
    (mirrors `MappingProposal.unclear_fields`) so a caller (an HTTP route,
    a CLI printer) can report exactly which target fields are blocking --
    never a bare "something is wrong".
    """

    def __init__(self, unclear_fields: list[FieldMapping]):
        self.unclear_fields = unclear_fields
        names = ", ".join(m.target_field for m in unclear_fields)
        super().__init__(f"mapping is not fully clear yet: {names}")


class NoStoreError(Exception):
    """Raised by `save_profile_if_ready` when no profile store (or no
    field set) is available to save against -- distinct from `NotReadyError`
    so a caller can tell "nothing to save into" apart from "not clear yet"."""


class FieldCoverageError(Exception):
    """Raised by `confirm` (CR-02) when the submitted `edited_mappings` do
    not cover EXACTLY the retained field set's fields.

    `MappingProposal.is_ready` is computed only over the mappings actually
    present in a `MappingProposal` -- nothing on that object cross-checks
    coverage against `field_set.fields`. A tampering client could therefore
    drop a still-yellow (or any) required field from the confirm body
    entirely: the remaining mappings are all clear, `is_ready` is `True`,
    and `canonical.assemble` would go on to silently emit `None` for the
    missing field with no flag at all. This check runs BEFORE `is_ready` is
    ever read, so an omission never reaches that point.

    `missing_fields`/`unknown_fields` name the exact mismatch (mirrors
    `NotReadyError.unclear_fields`'s "name the exact blocker, never a bare
    rejection" convention) so a caller (an HTTP route) can report precisely
    what the client's body got wrong.
    """

    def __init__(self, missing_fields: list[str], unknown_fields: list[str]):
        self.missing_fields = missing_fields
        self.unknown_fields = unknown_fields
        parts = []
        if missing_fields:
            parts.append(f"missing={missing_fields}")
        if unknown_fields:
            parts.append(f"unknown={unknown_fields}")
        super().__init__(f"field coverage mismatch: {', '.join(parts)}")


@dataclass(frozen=True)
class MapResult:
    """What the CLI prints and a future API returns as JSON -- identical
    data, two renderers. `profile_id` is set only on the auto-applied
    branch (the CLI's exact "applied saved profile {id} (no Claude call)"
    message needs it; the fresh-Claude branch has no profile to name).

    `date_question` (D-10-07, defaulted so no existing construction breaks)
    carries whatever per-column date-order ambiguities `resolve_date_formats`
    could not resolve on its own -- an empty `DateFormatQuestion` means every
    date-typed mapped column resolved cleanly.

    `escalation` (D-10-03, defaulted to `None`) carries the Python-vs-Claude
    breakdown ONLY when a `schema` was supplied to `resolve_or_map` AND the
    profile auto-apply did not already short-circuit everything -- a profile
    hit is a stronger, whole-file fact with no per-field breakdown to report,
    so it leaves this `None` rather than a misleading all-zero count."""

    proposal: MappingProposal
    table: RawTable
    provenance: str
    profile_id: str | None = None
    date_question: DateFormatQuestion = field(default_factory=lambda: DateFormatQuestion(()))
    escalation: Escalation | None = None


@dataclass(frozen=True)
class ConfirmResult:
    """The result of a successful `confirm()` -- the re-validated proposal,
    the one canonical tidy table (EXPORT-01) every export format derives
    from, and the manifest a future export step writes alongside the data.
    `profile_id` is set only when `confirm(save_profile=True)` persisted a
    profile."""

    proposal: MappingProposal
    tidy: CanonicalTable
    manifest: dict
    profile_id: str | None = None


def resolve_table_mapping(
    table: RawTable,
    field_set: FieldSet | None,
    store: ProfileStore | None,
    *,
    headers_only: bool = False,
    client=None,
    propose_mapping_fn=None,
    schema: Schema | None = None,
) -> tuple[MappingProposal, str, str | None]:
    """The per-table auto-apply/Python-first/fresh-Claude decision (LEARN-03/04,
    D-05/D-08, D-10-03) -- decides, never renders. Mirrors `cli._resolve_proposal`'s
    exact logic (PATTERNS.md cli.py:490-533), copied almost unchanged.

    Escalation order, exactly (D-10-03):
      1. profile auto-apply (existing, unchanged, strictly strongest -- a
         whole-file, human-confirmed fact beats a per-column alias guess, so
         it is checked FIRST and short-circuits everything below it);
      2. **NEW** the Python alias crosswalk pre-fill (`_python_first_prefill`),
         only when `schema` is given -- deterministic, free, no LLM;
      3. Claude, on whatever (2) left uncovered (or the full field set when
         no `schema` was given at all -- today's exact behavior, unchanged);
      4. the human, via the existing amber gate (`validate()`, unchanged,
         called by this function's own callers, not here).

    Returns `(proposal, provenance, profile_id)` -- `profile_id` is `None`
    on every branch except the auto-applied one. Raises `MissingCredentialsError`
    instead of the old `(None, "missing-credentials")` sentinel, and `ValueError`
    verbatim (naming the consequence) when `field_set` is `None` and
    credentials ARE configured -- the "error names the consequence"
    convention (CLAUDE.md).

    Auto-apply constructs no Anthropic client and checks no credentials at
    all (Pattern 5/Pitfall 3): the credential check only ever runs on the
    miss branch, immediately before a Claude call is actually about to
    happen.

    `schema` (D-10-02/03, keyword-only, defaulted to `None`) is the ONLY new
    parameter -- every existing call site (the CLI's `cli._resolve_proposal`,
    which never passes it) reaches the exact same fresh-Claude-on-the-full-
    -field-set branch as before, byte for byte.

    `propose_mapping_fn` lets a caller substitute its own (monkeypatchable)
    reference -- `cli.py` passes its own module-level `propose_mapping` so a
    test patching `cli.propose_mapping` still governs what the CLI calls;
    defaults to this module's own `propose_mapping` import so a test can
    instead patch `service.propose_mapping` directly (e.g. from a future API
    test).
    """
    fn = propose_mapping_fn if propose_mapping_fn is not None else propose_mapping

    if field_set is not None and store is not None:
        profile = store.find(field_set.signature, column_signature(table.headers))
        if profile is not None:
            proposal = reconstruct_proposal(profile, table.headers)
            return proposal, _PROVENANCE_AUTO_APPLIED, profile.profile_id

    if not has_credentials():
        raise MissingCredentialsError(
            "no Anthropic credentials configured; cannot run the mapper"
        )
    if field_set is None:
        # WR-03: field_set=None is a documented convenience for early-exit
        # callers, but a caller reaching this far with credentials
        # configured genuinely has no target fields to map onto -- raising
        # here (instead of letting propose_mapping dereference
        # field_set.fields and crash with a bare AttributeError) names the
        # consequence and lets the caller's own ValueError handler exit
        # cleanly.
        raise ValueError(
            "Cannot map: no field set was provided, so no target fields can "
            "be resolved."
        )
    if schema is not None:
        proposal, escalation = _python_first_prefill(
            table, field_set, schema,
            headers_only=headers_only, client=client, propose_mapping_fn=fn,
        )
        provenance = (
            _PROVENANCE_PYTHON_FIRST if escalation.claude_matched == 0 else _PROVENANCE_FRESH_CLAUDE
        )
        return proposal, provenance, None

    proposal = fn(table, field_set, client, headers_only=headers_only)
    return proposal, _PROVENANCE_FRESH_CLAUDE, None


def resolve_or_map(
    path: str,
    field_set: FieldSet | None,
    *,
    store: ProfileStore | None = None,
    hint: StructuralHint | None = None,
    sheet: str | None = None,
    strictness: str = "strict",
    headers_only: bool = False,
    client=None,
    propose_mapping_fn=None,
    schema: Schema | None = None,
) -> MapResult | StructureQuestion:
    """The single seam a future `POST /api/upload` route calls: parse the
    file, return the human's structural question unchanged when the parser
    is unsure, otherwise resolve (auto-apply, Python-first, or fresh-Claude)
    and validate. Never prints; never called from `cli.run()`'s own flow in
    this plan -- `cli.py` keeps its existing per-sheet
    `resolve_or_ask`/`_map_and_report` loop, wired through
    `resolve_table_mapping` instead (below).

    `validate()` runs here on BOTH branches (D-03) before the result is
    returned -- a profile's or Claude's own confidence never exempts a
    value from a declared constraint, matching the RESEARCH.md upload
    sequence ("validate() -- runs on both branches").

    `resolve_date_formats` (D-10-04..08) runs immediately BEFORE `validate()`
    on both branches too: it needs to know which source column feeds each
    date-typed field, which only exists once the proposal has resolved. It
    is pure Python, makes no network call, and behaves identically whatever
    `headers_only` is (D-10-05) -- it reads `table` directly, never anything
    sent to Claude.

    `schema` (D-10-02/03, keyword-only, defaulted to `None`) threads straight
    into `resolve_table_mapping` for the Python-first pre-fill. This function
    never re-invokes the mapper to compute `MapResult.escalation`:
    `_prefill_coverage` (the same pure, no-LLM computation
    `_python_first_prefill` already ran once to build the merged proposal)
    is re-derived here ONLY to count how many fields Python covered vs how
    many Claude was asked for -- cheap and side-effect-free, never a second
    Claude call. Left `None` when no `schema` was given, or when the profile
    auto-apply already won (there is nothing to break down).
    """
    outcome = parse(path, sheet=sheet, hint=hint)
    if isinstance(outcome, StructureQuestion):
        return outcome
    table = outcome

    proposal, provenance, profile_id = resolve_table_mapping(
        table, field_set, store,
        headers_only=headers_only, client=client, propose_mapping_fn=propose_mapping_fn,
        schema=schema,
    )
    escalation = None
    if schema is not None and field_set is not None and provenance != _PROVENANCE_AUTO_APPLIED:
        prefilled, remaining = _prefill_coverage(table, field_set, schema)
        escalation = Escalation(
            python_matched=len(prefilled), claude_matched=len(remaining), total=len(field_set.fields)
        )

    date_question = DateFormatQuestion(())
    if field_set is not None:
        resolution = resolve_date_formats(table, proposal, field_set)
        date_question = resolution.question
        proposal = validate(
            table, proposal, field_set, strictness=strictness,
            date_formats=resolution.formats, date_contradictions=resolution.contradictions,
        )
    return MapResult(proposal, table, provenance, profile_id, date_question, escalation)


def confirm(
    table: RawTable,
    edited_mappings: list[FieldMapping],
    field_set: FieldSet,
    *,
    save_profile: bool = False,
    strictness: str = "strict",
    store: ProfileStore | None = None,
    hint: StructuralHint | None = None,
    provenance: str = "fresh-claude",
    confirmed_by: str | None = None,
    schema_store: SchemaStore | None = None,
    target_schema_name: str | None = None,
    vendor: str | None = None,
    date_answers: Mapping[str, DateOrder] | None = None,
    source_label: str | None = None,
) -> ConfirmResult:
    """The P1 server-side confirm gate (mirrors `cli._map_one`'s recompute
    order, PATTERNS.md cli.py:567-592): rebuild a FRESH `MappingProposal`
    from the human's edited column choices, re-run `validate()`, and read
    `is_ready` off the freshly-built object -- never off anything the caller
    claims. A tampered/stale `needs_confirmation=False` in `edited_mappings`
    cannot survive this recomputation (`reconstruct.py`'s "build fresh, then
    validate, never trust the source's readiness claim" idiom, applied to
    an HTTP body instead of a stored profile).

    The re-validation runs at `stage="confirm"`: it judges the chosen
    `source_column` and any `inferred_value` -- the only inputs the export
    writes -- but not Claude's ranked alternatives, which the human's choice
    has rejected and which the Review screen offers no way to remove; an
    objection to one of those would block the confirm forever (see
    `validation.validator`). This narrows scope only, never severity: a
    violation in the chosen column or inferred value still raises
    `NotReadyError` exactly as before.

    Raises `FieldCoverageError` (CR-02) when `edited_mappings` does not
    cover exactly `field_set.fields` -- checked BEFORE `is_ready` is ever
    read, so a client cannot drop a still-yellow field and have the
    remainder's clearness silently stand in for the whole mapping. Raises
    `NotReadyError` when any (fully covered) field is still yellow -- there
    is no "blocked" return value, so every caller is forced to handle the
    gate explicitly, never silently proceed on a partial mapping.

    `confirmed_by` (AUTH-04, keyword-only, additive) is threaded into the
    manifest: the API confirm route supplies the authenticated curator's
    email (from `require_verified_user`), while the CLI path passes nothing
    and records `None` -- the seam is purely additive, so no CLI call site
    changes.

    `schema_store` + `target_schema_name` + `vendor` (D-07-05/06, ALIAS-04,
    keyword-only, additive) let this same confirm accrete the crosswalk: when
    ALL THREE are supplied, each resolved `(canonical field <- source column)`
    is upserted as a `manual` `Alias` stamped `provenance_actor=confirmed_by`
    (the server-resolved curator email on the API path) -- recorded ONLY after
    the gate passes (`_record_aliases`, below), never on a rejected mapping.
    When any of the three is absent (the CLI path, and any confirm without a
    target Schema/vendor) NOTHING is written -- mirrors how `confirmed_by` was
    threaded additively in Phase 06, so no existing call site changes.

    `date_answers` (D-10-08/INGEST-04, keyword-only, defaulted `None`) is the
    human's per-column date ORDER, retained server-side on `UploadEntry` by
    `/api/date-format/resolve` -- NEVER a format string (T-10-21/T-10-30).
    This function re-derives the concrete resolved format itself, from the
    RETAINED `table` and the FRESH `proposal` just built below, by calling
    `resolve_date_formats` exactly as `resolve_or_map`/`date_format.py`
    already do -- it never accepts or trusts a caller-supplied format. The
    resolution is threaded into BOTH `validate()` (so the gate agrees a
    resolved date field is clear) AND the canonical assembly step below (so
    the exported cell is actually ISO-8601) -- threading only the first would
    yield a green gate and a wrong file. `confirm()` has exactly ONE call
    site (`api/routes/confirm.py`), which passes `entry.date_answers`
    (`None` on every upload that never raised a date question) -- an
    omitted `date_answers` therefore preserves today's exact behavior.
    `answers=None` never raises (10-03's "first pass" asymmetry); a
    genuinely ambiguous, unanswered column simply stays out of `formats`, so
    `validate()` flags it amber and the EXISTING `is_ready` check below
    still raises `NotReadyError` -- fail-closed through the gate that
    already exists, never a new one. A human who re-points a date field at
    a DIFFERENT, still-ambiguous column after resolving raises
    `UnresolvedDateColumnsError`, which the route maps to 422.

    `source_label` (SHEET-03/D-11-15, keyword-only, defaulted `None`) is the
    caller's name for the source when the table has no worksheet of its own --
    the client's REAL filename on the API path (`UploadEntry.source_file_name`).
    The provenance actually written is `table.origin_sheet or source_label`:
    the worksheet title when there is one, the uploaded file's name when there
    is not (a CSV has no sheets, and D-11-15 still requires every row to record
    where it came from -- a traceability column that only sometimes exists is
    not a traceability column). `RawTable.source_name` is deliberately NOT the
    fallback: on the API path the parser only ever saw a TEMPFILE's generated
    name (`api/wire.py`'s own `source_name` docstring), which would tell a
    curator nothing and would leak a server path fragment into a downloaded
    file (T-11-09). Omitting the argument (the CLI path) writes no provenance
    at all -- `assemble` leaves `record_sources` empty and every writer's
    output is byte-identical to today.
    """
    expected = set(field_set.field_names)
    got = {m.target_field for m in edited_mappings}
    if got != expected:
        raise FieldCoverageError(
            sorted(expected - got), sorted(got - expected)
        )

    proposal = MappingProposal(
        source_columns=list(table.headers), field_mappings=list(edited_mappings)
    )
    resolution = resolve_date_formats(table, proposal, field_set, answers=date_answers)
    # stage="confirm" (VAL-02 scoping): the gate judges only the inputs the
    # export actually reads -- the human's chosen source_column and any
    # inferred_value -- never Claude's rejected alternatives, which no
    # Review-screen action can remove and which feed nothing that is
    # written. The severity of an in-scope violation is unchanged.
    proposal = validate(
        table, proposal, field_set, strictness=strictness, stage="confirm",
        date_formats=resolution.formats, date_contradictions=resolution.contradictions,
    )
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)

    # SHEET-03/D-11-15: the worksheet title when the source had one, the
    # caller's real file name when it did not (a CSV) -- never
    # `table.source_name`, a tempfile's name on the API path (T-11-09).
    source_sheet = table.origin_sheet or source_label
    tidy = canonical.assemble(
        table, proposal, field_set,
        date_formats=resolution.formats, source_sheet=source_sheet,
    )
    manifest = build_manifest(
        field_set, table.headers, proposal, provenance=provenance,
        strictness=strictness, confirmed_by=confirmed_by, source_sheet=source_sheet,
    )
    profile_id = None
    if save_profile:
        profile_id = save_profile_if_ready(store, field_set, table, proposal, hint, vendor=vendor)
    _record_aliases(proposal, schema_store, target_schema_name, vendor, confirmed_by)
    return ConfirmResult(proposal, tidy, manifest, profile_id)


def _record_aliases(
    proposal: MappingProposal,
    schema_store: SchemaStore | None,
    target_schema_name: str | None,
    vendor: str | None,
    confirmed_by: str | None,
) -> None:
    """ALIAS-04 (D-07-05/06): accrete the crosswalk from a passed confirm.

    A no-op unless a target Schema store, Schema name, AND vendor are ALL
    supplied -- the CLI path and any confirm without a target Schema/vendor
    record nothing (purely additive). Each resolved `(canonical field <-
    source column)` is upserted as a `manual` `Alias` whose provenance actor is
    the caller-supplied `confirmed_by` (a server-resolved email on the API
    path), NEVER re-derived here. A field with no resolved `source_column` (an
    inferred-only field) has no vendor column to crosswalk, so it records
    nothing. Relies on the store's idempotent INSERT-OR-IGNORE, so re-confirming
    keeps an alias's first-seen provenance (ALIAS-03) -- this never overwrites.
    """
    if schema_store is None or not target_schema_name or not vendor:
        return
    schema = schema_store.get_schema(target_schema_name)
    if schema is None:
        return
    stamped_at = datetime.now(UTC).isoformat()
    canonical_names = {cf.field.name for cf in schema.fields}
    for mapping in proposal.field_mappings:
        if mapping.source_column is None or mapping.target_field not in canonical_names:
            continue
        schema_store.add_alias(
            schema.id,
            mapping.target_field,
            Alias(
                vendor=vendor,
                source_column=mapping.source_column,
                provenance_kind="manual",
                provenance_actor=confirmed_by or "",
                created_at=stamped_at,
            ),
        )


def save_profile_if_ready(
    store: ProfileStore | None,
    field_set: FieldSet | None,
    table: RawTable,
    proposal: MappingProposal,
    hint: StructuralHint | None,
    *,
    vendor: str | None = None,
) -> str:
    """LEARN-02/06 (mirrors `cli._save_profile_if_ready`, PATTERNS.md
    cli.py:595-624): persist a confirmed mapping as a profile for future
    auto-apply. Blocked unless the mapping is fully clear -- a yellow
    field's column-to-field association is not yet a curator-confirmed
    fact. Any structural hint the file needed is persisted with the profile
    (D-07) so the same odd layout parses automatically next time.

    `vendor` (10-09/INGEST-02, keyword-only, defaulted `None`) is persisted
    onto the profile at the ONE moment it is known -- confirm time. The CLI
    call site (`cli.py`) passes nothing, since it has no vendor to assert;
    that profile is saved with `vendor=None`, exactly as before this change.

    Raises `NoStoreError` when no store/field set is available, and
    `NotReadyError` when the proposal is not yet fully clear. Returns the
    new profile's id.
    """
    if store is None or field_set is None:
        raise NoStoreError("no profile store available (missing field set)")
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)
    profile = LearnedProfile(
        profile_id=str(uuid.uuid4()),
        field_set_signature=field_set.signature,
        column_signature=column_signature(table.headers),
        field_mappings=tuple(
            stored_mapping_from(m, table.headers) for m in proposal.field_mappings
        ),
        structural_hint=hint,
        created_at=datetime.now(UTC).isoformat(),
        vendor=vendor,
    )
    store.save(profile)
    return profile.profile_id


def export(
    export_dir: Path,
    table: RawTable,
    field_set: FieldSet,
    proposal: MappingProposal,
    tidy: CanonicalTable,
    provenance: str,
    strictness: str,
) -> dict:
    """EXPORT-02/03/04 (mirrors `cli._export_if_ready`, PATTERNS.md
    cli.py:627-656): writes CSV/.xlsx/JSON + manifest.json -- only when the
    mapping is fully clear (D-09/P1). Raises `NotReadyError` otherwise; the
    tool never writes a partial export. Every writer takes only the one
    canonical `tidy` table (D-15) -- nothing here re-derives records from
    `table`/`proposal` directly. Returns the manifest dict that was written.

    SHEET-03: the manifest's `source_sheet` is read OFF THE SAME `tidy` the
    three writers just wrote, never re-derived from `table` -- so the audit
    trail cannot claim one source while the data files ship another. This is
    the `value_source` discipline (manifest and data read one function)
    applied to the provenance column. An assembly with no source (the CLI
    path) leaves `record_sources` empty, and the manifest honestly records
    `None`.
    """
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)
    export_dir.mkdir(parents=True, exist_ok=True)
    write_csv(tidy, export_dir / "export.csv")
    write_xlsx(tidy, export_dir / "export.xlsx")
    write_json(tidy, export_dir / "export.json")
    manifest = build_manifest(
        field_set, table.headers, proposal, provenance=provenance, strictness=strictness,
        source_sheet=tidy.record_sources[0] if tidy.record_sources else None,
    )
    (export_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


# --- Phase 07: governed Schema (promote) + master-map export/import ----------


class SchemaNotFoundError(Exception):
    """Raised when a named target Schema does not exist -- naming the
    consequence ("nothing to act on") instead of letting a downstream store
    call fail obscurely against a `None` schema id. Used by `import_master_map`
    (Phase 07) and every Phase 10 explicit edit function below
    (`add_schema_field`/`update_schema_field`/`remove_schema_field`/
    `add_schema_alias`/`remove_schema_alias`). A route maps this to HTTP 404
    exactly as `field_sets.py`/`confirm.py` map their own typed misses."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"No Schema named {name!r} exists.")


def promote(
    field_set: FieldSet,
    *,
    created_by: str | None,
    store: SchemaStore,
    name: str | None = None,
) -> Schema:
    """D-07-03 (SCHEMA-01/04): turn a field set into a governed Schema whose
    canonical fields ARE the field set's fields (each starting with no
    aliases), stamped `created_by` = the server-resolved user email.

    The Schema name is `name` when given, else the field set's own name -- the
    domain identity, unique per store (D-07-03). Two differently-named field
    sets promote into two isolated Schemas that share no fields or aliases
    (SCHEMA-04, enforced by the store's `schema_id` foreign key, never Python
    name filtering). Decides, never renders: returns the persisted `Schema`
    or raises `ValueError` naming the consequence when no name is resolvable.
    """
    schema_name = name if name is not None else field_set.name
    if not schema_name:
        raise ValueError(
            "Cannot promote: the field set has no name and none was supplied."
        )
    return store.create_schema(schema_name, field_set.fields, created_by)


def export_master_map(schema: Schema) -> dict:
    """SCHEMA-02: the Schema's versioned JSON master-map envelope -- the
    downloadable crosswalk (canonical fields + their aliases + provenance). A
    pure projection of the domain object; the route layer serialises it to a
    response the browser saves."""
    return schema.to_master_map()


def import_master_map(
    store: SchemaStore,
    target_schema_name: str,
    envelope: dict,
    *,
    source_name: str,
) -> Schema:
    """SCHEMA-03 (D-07-04): AUGMENT the named target Schema from a master-map
    envelope -- add missing canonical fields and union in missing aliases,
    NEVER discard.

    The envelope is parsed through `Schema.from_master_map` first, so every
    incoming field name gets the same `fields.loader` name-safety guard a
    file-loaded or promoted field set gets (T-07-08) -- no second, weaker
    check here. Missing fields are added via `store.add_or_update_fields`
    (existing definitions kept, never overwritten). Each incoming alias is
    then recorded with `provenance_kind="from_map_file"` and
    `provenance_actor=source_name` (the map file's declared/derived source),
    relying on the store's INSERT-OR-IGNORE idempotency: an alias already
    present (a prior manual confirmation, say) keeps its first-seen provenance
    untouched (ALIAS-03). Nothing is ever overwritten or deleted.

    Fields are added BEFORE their aliases so `add_alias` always finds its
    canonical field. Raises `SchemaNotFoundError` when `target_schema_name`
    names no existing Schema -- there is nothing to augment.
    """
    target = store.get_schema(target_schema_name)
    if target is None:
        raise SchemaNotFoundError(target_schema_name)

    incoming = Schema.from_master_map(envelope)
    store.add_or_update_fields(target.id, tuple(cf.field for cf in incoming.fields))

    stamped_at = datetime.now(UTC).isoformat()
    for canonical_field in incoming.fields:
        for alias in canonical_field.aliases:
            store.add_alias(
                target.id,
                canonical_field.field.name,
                Alias(
                    vendor=alias.vendor,
                    source_column=alias.source_column,
                    provenance_kind="from_map_file",
                    provenance_actor=source_name,
                    created_at=stamped_at,
                ),
            )
    return store.get_schema(target.id)


# --- Phase 10: explicit governed-Schema edit (D-10-12) -----------------------
#
# D-07-04 stays intact: `import_master_map` above is UNCHANGED and remains
# augment-only -- a map file may only ADD. Only a human, through the four
# functions below (reached via their own routes, never through the
# master-map route), may UPDATE or REMOVE a canonical field or alias, and
# every removal is attributed to the server-resolved actor and stamped with
# a server-minted timestamp -- never a client-supplied value (T-10-16).


class SchemaNameTakenError(Exception):
    """Raised when a rename would give two Schemas one name -- naming the
    consequence (nothing was renamed) rather than surfacing the store's
    UNIQUE-constraint violation as a bare driver error. A Schema's name is
    its domain identity (SCHEMA-04: two Schemas never share fields or
    aliases), so a collision must be refused, never merged or overwritten."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            f"Cannot rename: a Schema named {name!r} already exists -- two "
            f"Schemas never share a name, so nothing was renamed. Pick a "
            f"different name."
        )


def rename_schema(store: SchemaStore, schema_name: str, new_name: str) -> Schema:
    """Rename a governed Schema (quick 260712) -- the label changes, the
    identity row does not: `id`, canonical fields, aliases, and provenance
    all survive untouched.

    Safe for the learning loop BY CONSTRUCTION: learned profiles are keyed
    on `FieldSet.signature`, which hashes the FIELDS ONLY (never the
    Schema's name -- `fields/models.py::FieldSet.signature`), so a renamed
    Schema's uploads keep auto-applying every profile learned under the old
    name (pinned by `test_renaming_a_schema_never_orphans_learned_profiles`).

    Raises `SchemaNotFoundError` when `schema_name` names no Schema,
    `ValueError` when the new name is blank (nothing to rename to), and
    `SchemaNameTakenError` when another Schema already owns `new_name`.
    Renaming to the current name is a no-op returning the Schema unchanged.
    """
    schema = _resolve_schema(store, schema_name)
    cleaned = new_name.strip()
    if not cleaned:
        raise ValueError(
            "Cannot rename: the new name is empty, so nothing was renamed. "
            "Give the Schema a non-blank name."
        )
    if cleaned == schema.name:
        return schema
    other = store.get_schema(cleaned)
    if other is not None and other.id != schema.id:
        raise SchemaNameTakenError(cleaned)
    return store.rename_schema(schema.id, cleaned)


class SchemaFieldNotFoundError(Exception):
    """Raised when a named field (or a specific alias hanging off it) does
    not exist -- or is already tombstoned -- in the named Schema. Wraps the
    store's own `ValueError` (whose message already names the exact
    consequence) so a route can map this to HTTP 404 instead of letting a
    bare `ValueError` surface as a 500."""


def _resolve_schema(store: SchemaStore, schema_name: str) -> Schema:
    """The one place every Phase 10 edit function resolves its target
    Schema -- raises `SchemaNotFoundError` naming the consequence on a miss,
    instead of letting a `None` schema id reach the store."""
    schema = store.get_schema(schema_name)
    if schema is None:
        raise SchemaNotFoundError(schema_name)
    return schema


def _field_from_raw(field_dict: dict) -> Field:
    """Build one validated `Field` from a raw, untrusted dict -- through the
    SAME `fields.loader.from_dict` -> `_validated_name` guard a CLI-loaded,
    promoted, or map-file-imported field gets (T-07-08/T-10-17). Never a
    second, weaker Pydantic-only check at this or the route layer. Wrapped
    in a single-field envelope because `from_dict` is a `FieldSet` loader,
    not a single-`Field` one -- this is the shared seam, not a fork of it."""
    field_set = _field_dict_to_field_set({"fields": [field_dict]})
    return field_set.fields[0]


def add_schema_field(store: SchemaStore, schema_name: str, field_dict: dict) -> Schema:
    """Add ONE new canonical field to the named Schema (INGEST-05) -- the
    "Add Field" affordance. Raises `SchemaNotFoundError` on a missing
    Schema, and `ValueError` (naming the consequence) both from the shared
    `fields.loader` name/type guard and from this function's own MAX_FIELDS
    cap check, run BEFORE any field is built -- an accidental 51st field
    must fail with a named error, not a silent no-op via the store's
    augment-only `ON CONFLICT DO NOTHING` (D-04's field-cap discipline,
    mirrored from the whole-file loader)."""
    schema = _resolve_schema(store, schema_name)
    if len(schema.fields) >= MAX_FIELDS:
        raise ValueError(
            f"Cannot add field: schema {schema_name!r} already has "
            f"{MAX_FIELDS} fields, the maximum allowed."
        )
    field = _field_from_raw(field_dict)
    return store.add_or_update_fields(schema.id, (field,))


def update_schema_field(
    store: SchemaStore, schema_name: str, field_name: str, field_dict: dict
) -> Schema:
    """Overwrite an existing canonical field's constraints -- a genuine
    update, unlike the augment-only master-map import (D-10-12). `field_dict`
    may declare a different `name` than `field_name`: that is the rename
    affordance, and the field's aliases survive it (the store scopes by the
    field's row id, resolved from `field_name` BEFORE the rename is applied).
    Raises `SchemaNotFoundError` on a missing Schema, `ValueError` on an
    invalid field name/type (T-07-08), and `SchemaFieldNotFoundError` when
    `field_name` is absent from this Schema or already tombstoned."""
    schema = _resolve_schema(store, schema_name)
    field = _field_from_raw(field_dict)
    try:
        return store.update_field(schema.id, field_name, field)
    except ValueError as exc:
        raise SchemaFieldNotFoundError(str(exc)) from exc


def remove_schema_field(
    store: SchemaStore, schema_name: str, field_name: str, *, removed_by: str
) -> Schema:
    """Tombstone a canonical field (D-10-15) -- cascades to every live alias
    hanging off it (the store's own transaction). `removed_by` is
    keyword-only and required so a caller can never forget to attribute a
    removal; the timestamp is minted HERE, server-side, never taken from a
    caller. Raises `SchemaNotFoundError` on a missing Schema, and
    `SchemaFieldNotFoundError` when `field_name` is absent or already
    tombstoned."""
    schema = _resolve_schema(store, schema_name)
    removed_at = datetime.now(UTC).isoformat()
    try:
        return store.remove_field(schema.id, field_name, removed_by=removed_by, removed_at=removed_at)
    except ValueError as exc:
        raise SchemaFieldNotFoundError(str(exc)) from exc


def add_schema_alias(
    store: SchemaStore,
    schema_name: str,
    field_name: str,
    vendor: str,
    source_column: str,
    *,
    actor: str,
) -> Schema:
    """Record ONE manually-entered vendor alias (D-10-12) -- functionally the
    same manual-provenance path `confirm`'s `_record_aliases` already
    exercises via `store.add_alias`; reused here rather than re-implemented.
    `actor` is keyword-only and required (never a body field, T-10-16); the
    timestamp is minted here. Raises `SchemaNotFoundError` on a missing
    Schema, and `SchemaFieldNotFoundError` when `field_name` names no live
    canonical field on this Schema."""
    schema = _resolve_schema(store, schema_name)
    stamped_at = datetime.now(UTC).isoformat()
    alias = Alias(
        vendor=vendor,
        source_column=source_column,
        provenance_kind="manual",
        provenance_actor=actor,
        created_at=stamped_at,
    )
    try:
        store.add_alias(schema.id, field_name, alias)
    except ValueError as exc:
        raise SchemaFieldNotFoundError(str(exc)) from exc
    return store.get_schema(schema.id)


def remove_schema_alias(
    store: SchemaStore,
    schema_name: str,
    field_name: str,
    vendor: str,
    source_column: str,
    *,
    removed_by: str,
) -> Schema:
    """Tombstone ONE vendor alias (D-10-15) -- never a physical DELETE.
    `removed_by` is keyword-only and required; the timestamp is minted here.
    Raises `SchemaNotFoundError` on a missing Schema, and
    `SchemaFieldNotFoundError` when `field_name` names no live canonical
    field, or no live alias matches `(vendor, source_column)` on it."""
    schema = _resolve_schema(store, schema_name)
    removed_at = datetime.now(UTC).isoformat()
    try:
        store.remove_alias(
            schema.id, field_name, vendor, source_column,
            removed_by=removed_by, removed_at=removed_at,
        )
    except ValueError as exc:
        raise SchemaFieldNotFoundError(str(exc)) from exc
    return store.get_schema(schema.id)


# --- Phase 08: reconcile-on-upload (D-08-02/04) ------------------------------


class UnresolvedConflictsError(Exception):
    """Raised by `apply_reconcile_resolution` (F2) when the human's `choices` do
    not carry an explicit decision for EVERY conflict the map file still has with
    the master.

    Continuing with an uncovered conflict would leave that column to the
    post-augment normalized index, which resolves it nondeterministically by row
    order -- a silent wrong-side pick (P1 fail-closed). `conflicts` carries the
    still-undecided `ReconcileConflict` objects so a caller (an HTTP route) can
    name exactly which pairs are blocking, never a bare rejection -- mirroring
    `NotReadyError.unclear_fields`. A route maps this to HTTP 422."""

    def __init__(self, conflicts: tuple[ReconcileConflict, ...]):
        self.conflicts = conflicts
        pairs = ", ".join(f"({c.vendor!r}, {c.source_column!r})" for c in conflicts)
        super().__init__(
            "Cannot apply resolution: every detected conflict must be explicitly "
            f"resolved, but these were left undecided: {pairs}."
        )


#: The two decisions a per-conflict `choice` may carry (D-08-02). A choice
#: carrying anything else does not count as covering its conflict (F2).
_VALID_RECONCILE_DECISIONS = ("keep_master", "take_map_file")


def detect_reconcile_conflicts(envelope: dict, schema: Schema) -> ReconcileQuestion:
    """Find every alias-target disagreement between an uploaded map file and the
    master Schema, BEFORE anything is mutated (D-08-02 step 1, P1).

    The envelope is parsed through `Schema.from_master_map` -- REUSED, never a
    second parser -- so an incoming field name carrying a control character is
    rejected by the same `fields.loader` name-safety guard a promoted or
    file-loaded field set gets (T-08-01); no weaker check is introduced here.

    A conflict is emitted ONLY when the master already crosswalks the same
    `(vendor, source_column)` pair to a DIFFERENT canonical field than the map
    file asserts (alias-target disagreement -- the primary conflict case per
    D-08-02; field-constraint diffs are out of scope this plan). A pair the
    master has never seen (novel, augment-safe), one it maps to the SAME field
    (agreement), or one whose vendor differs (a different identity per D-08-04)
    is NOT a conflict.

    Column identity is the SAME `(vendor, _normalise_header(source_column))` key
    the pre-fill index (`_alias_index`) uses -- bit-for-bit -- so a map file whose
    source column differs from a master alias ONLY by case or incidental
    whitespace is recognised as the SAME column and its disagreement is surfaced,
    never silently imported (F1, P1). Matching on the RAW pair here while the
    pre-fill matched on the normalised pair let a case/whitespace variant escape
    detection and then collide in the normalised index at confidence 1.0 with no
    human review -- exactly the silent wrong-side pick this gate exists to prevent.
    """
    incoming = Schema.from_master_map(envelope)
    master_index = {
        (alias.vendor, _normalise_header(alias.source_column)): canonical_field.field.name
        for canonical_field in schema.fields
        for alias in canonical_field.aliases
    }
    conflicts = [
        ReconcileConflict(
            vendor=alias.vendor,
            source_column=alias.source_column,
            master_field=master_field,
            map_file_field=canonical_field.field.name,
        )
        for canonical_field in incoming.fields
        for alias in canonical_field.aliases
        if (
            master_field := master_index.get(
                (alias.vendor, _normalise_header(alias.source_column))
            )
        )
        is not None
        and master_field != canonical_field.field.name
    ]
    return ReconcileQuestion(tuple(conflicts))


def _alias_index(schema: Schema, vendor: str) -> dict[tuple[str, str], str]:
    """The `(vendor, normalised source column) -> canonical field name` lookup
    the pre-fill matches uploaded headers against (D-08-02 step 4).

    Source columns are normalised through `learning.signature._normalise_header`
    -- REUSED, never forked -- so matching mirrors the exact-signature learning
    loop: a header differing only by case or incidental whitespace still matches
    (D-08-04). Keyed on `vendor` too, so an alias recorded for a different vendor
    never bleeds into this vendor's pre-fill (identity is the pair, D-08-04).
    """
    return {
        (alias.vendor, _normalise_header(alias.source_column)): canonical_field.field.name
        for canonical_field in schema.fields
        for alias in canonical_field.aliases
    }


def _reconcile_map(
    table: RawTable,
    field_set: FieldSet,
    schema: Schema,
    vendor: str,
    *,
    override_index: dict[tuple[str, str], str] | None = None,
    headers_only: bool,
    client=None,
    propose_mapping_fn=None,
) -> tuple[MappingProposal, str]:
    """Deterministic exact-alias pre-fill that seeds/short-circuits the mapper
    (D-08-02 steps 4-5) -- decides, never renders, and does NOT validate (the
    Task-3 entrypoints own that, matching `resolve_or_map`'s structure).

    Every uploaded header whose `(vendor, normalised name)` matches a known
    crosswalk alias is pre-mapped to that canonical field at confidence 1.0 with
    `needs_confirmation=False` (provenance = the crosswalk) -- never sent to
    Claude. Because matching uses column NAMES only, a headers_only table (rows
    empty) yields the identical pre-fill (P4, T-08-04). `override_index` layers a
    per-conflict human choice on top (the resolution path; `None` here).

    The mapper is invoked on a REDUCED field set holding ONLY the fields no alias
    covered -- and when EVERY field is covered it is not constructed or called at
    all (the known-vendor second-file money shot). Pre-filled and mapper mappings
    are merged in the field set's declared order into one `MappingProposal`.
    Returns `(proposal, _PROVENANCE_RECONCILED)`.
    """
    fn = propose_mapping_fn if propose_mapping_fn is not None else propose_mapping
    index = _alias_index(schema, vendor)
    if override_index:
        index = {**index, **override_index}

    prefilled: dict[str, FieldMapping] = {}
    for header in table.headers:
        canonical = index.get((vendor, _normalise_header(header)))
        if canonical is not None and canonical not in prefilled:
            prefilled[canonical] = FieldMapping(
                target_field=canonical,
                source_column=header,
                confidence=1.0,
                reasoning=f"pre-filled from the {vendor!r} crosswalk alias for {header!r}",
                needs_confirmation=False,
            )

    remaining = tuple(f for f in field_set.fields if f.name not in prefilled)
    mapped: dict[str, FieldMapping] = {}
    if remaining:
        reduced = FieldSet(name=field_set.name, fields=remaining)
        proposal = fn(table, reduced, client, headers_only=headers_only)
        mapped = {m.target_field: m for m in proposal.field_mappings}

    merged = [
        prefilled.get(name) or mapped[name]
        for name in field_set.field_names
        if name in prefilled or name in mapped
    ]
    return (
        MappingProposal(source_columns=list(table.headers), field_mappings=merged),
        _PROVENANCE_RECONCILED,
    )


def _resolution_override_index(
    master: Schema, envelope: dict, choices: list[tuple[str, str, str]]
) -> dict[tuple[str, str], str]:
    """Turn per-conflict human choices into a pre-fill override (D-08-02 step 2).

    Each `(vendor, source_column, decision)` deterministically fixes what THIS
    run's pre-fill maps that column to -- `take_map_file` -> the map file's
    asserted field, `keep_master` -> the master's stored field. The override is
    resolved from the choice EXPLICITLY (never left to rely on store row order),
    so the human's decision governs regardless of how many alias rows coexist
    for the pair after augment. It never touches the store -- master aliases stay
    immutable (P3, T-08-05); persisting a conflicting override is FUTURE.

    Both lookup indices AND the choice lookup are keyed on the SAME
    `(vendor, _normalise_header(source_column))` identity the conflict gate and
    the pre-fill use (F1). A conflict surfaced for a case/whitespace variant is
    therefore resolvable under BOTH decisions -- `keep_master` finds the master's
    field even though the choice carries the map file's raw column spelling, and
    vice versa -- so the human's decision can never fall through to a
    nondeterministic pick.
    """
    incoming = Schema.from_master_map(envelope)
    master_index = {
        (alias.vendor, _normalise_header(alias.source_column)): canonical_field.field.name
        for canonical_field in master.fields
        for alias in canonical_field.aliases
    }
    map_index = {
        (alias.vendor, _normalise_header(alias.source_column)): canonical_field.field.name
        for canonical_field in incoming.fields
        for alias in canonical_field.aliases
    }
    override: dict[tuple[str, str], str] = {}
    for vendor, source_column, decision in choices:
        source = map_index if decision == "take_map_file" else master_index
        key = (vendor, _normalise_header(source_column))
        target_field = source.get(key)
        if target_field is not None:
            override[key] = target_field
    return override


def _require_every_conflict_resolved(
    envelope: dict, master: Schema, choices: list[tuple[str, str, str]]
) -> None:
    """Fail closed unless the human's `choices` decide EVERY conflict (F2, P1).

    Re-derives the conflicts against the pre-augment master (the same
    `detect_reconcile_conflicts` the upload path surfaced) and requires each one
    to be covered by a choice carrying a valid decision. Coverage is matched on
    the SAME `(vendor, _normalise_header(source_column))` identity the gate and
    pre-fill use (F1), so a choice spelling the column differently in case or
    whitespace still counts. Any conflict left undecided -- including the empty
    `choices` list -- raises `UnresolvedConflictsError` naming the exact pairs,
    BEFORE anything is augmented or mapped: an uncovered conflict would otherwise
    fall through to the post-augment normalised index and be resolved
    nondeterministically by row order, a silent wrong-side pick.
    """
    conflicts = detect_reconcile_conflicts(envelope, master).conflicts
    covered = {
        (vendor, _normalise_header(source_column))
        for vendor, source_column, decision in choices
        if decision in _VALID_RECONCILE_DECISIONS
    }
    uncovered = tuple(
        conflict
        for conflict in conflicts
        if (conflict.vendor, _normalise_header(conflict.source_column)) not in covered
    )
    if uncovered:
        raise UnresolvedConflictsError(uncovered)


def reconcile_or_map(
    path: str,
    field_set: FieldSet,
    *,
    schema_store: SchemaStore,
    target_schema_name: str,
    vendor: str,
    envelope: dict,
    store: ProfileStore | None = None,
    sheet: str | None = None,
    strictness: str = "strict",
    headers_only: bool = False,
    client=None,
    propose_mapping_fn=None,
    source_name: str | None = None,
) -> MapResult | StructureQuestion | ReconcileQuestion:
    """The reconcile analogue of `resolve_or_map` (D-08-02): parse the file, then
    reconcile an uploaded map file against the target Schema before mapping.

    Sequence (decides, never renders):
      1. `parse` -- a `StructureQuestion` still takes precedence (structural
         ambiguity is resolved before any reconcile, mirroring `resolve_or_map`).
      2. Load the target Schema; a miss raises `SchemaNotFoundError` (there is
         nothing to reconcile against).
      3. `detect_reconcile_conflicts` BEFORE mutating anything -- if the map file
         disagrees with the master, return the `ReconcileQuestion` and mutate
         NOTHING (no augment, no map): P1, never silently pick a side.
      4. No conflicts -> `import_master_map` augments the crosswalk (REUSED,
         `from_map_file` provenance, augment-never-discard P3/D-08-03).
      5. `_reconcile_map` pre-fills exact alias matches at 1.0 and lets Claude
         fill only the rest; `validate()` runs on the merged proposal against the
         FULL field set (D-03), exactly like `resolve_or_map`.

    `source_name` labels the augment provenance (the uploaded map file's source);
    defaults to the envelope's declared name so the caller need not repeat it.
    """
    outcome = parse(path, sheet=sheet)
    if isinstance(outcome, StructureQuestion):
        return outcome
    table = outcome

    schema = schema_store.get_schema(target_schema_name)
    if schema is None:
        raise SchemaNotFoundError(target_schema_name)

    conflicts = detect_reconcile_conflicts(envelope, schema)
    if conflicts.has_conflicts:
        return conflicts

    import_master_map(
        schema_store, target_schema_name, envelope,
        source_name=source_name or envelope.get("name", "map-file"),
    )
    augmented = schema_store.get_schema(target_schema_name)
    proposal, provenance = _reconcile_map(
        table, field_set, augmented, vendor,
        headers_only=headers_only, client=client, propose_mapping_fn=propose_mapping_fn,
    )
    proposal = validate(table, proposal, field_set, strictness=strictness)
    return MapResult(proposal, table, provenance, profile_id=None)


def apply_reconcile_resolution(
    path: str,
    field_set: FieldSet,
    *,
    schema_store: SchemaStore,
    target_schema_name: str,
    vendor: str,
    envelope: dict,
    choices: list[tuple[str, str, str]],
    store: ProfileStore | None = None,
    sheet: str | None = None,
    strictness: str = "strict",
    headers_only: bool = False,
    client=None,
    propose_mapping_fn=None,
    source_name: str | None = None,
) -> MapResult | StructureQuestion:
    """Continue a reconcile AFTER the human resolved its conflicts (D-08-02 step
    2 continuation). `choices` is `(vendor, source_column, decision)` triples
    where `decision` is `keep_master` or `take_map_file`.

    Every conflict `detect_reconcile_conflicts` still finds between the map file
    and the (pre-augment) master MUST carry an explicit decision in `choices`,
    else `UnresolvedConflictsError` is raised BEFORE anything is augmented or
    mapped (F2, P1). An omitted or empty choice list would otherwise leave a
    conflicting column to the post-augment normalized index, which resolves it
    nondeterministically by row order -- a silent wrong-side pick.

    Augments the master from the map file (`import_master_map`, INSERT-OR-IGNORE
    -- master's first-seen alias for a pair is never overwritten, P3), then builds
    an override from the choices so THIS run's pre-fill maps each resolved column
    to the chosen field. The override governs the pre-fill only -- it is never
    persisted, so a `take_map_file` choice does NOT overwrite the master's
    conflicting alias (immutability, P3/T-08-05); persisting a conflicting
    override is deferred to FUTURE schema versioning. `validate()` runs on the
    merged proposal (D-03).
    """
    outcome = parse(path, sheet=sheet)
    if isinstance(outcome, StructureQuestion):
        return outcome
    table = outcome

    master = schema_store.get_schema(target_schema_name)
    if master is None:
        raise SchemaNotFoundError(target_schema_name)

    _require_every_conflict_resolved(envelope, master, choices)
    override_index = _resolution_override_index(master, envelope, choices)
    import_master_map(
        schema_store, target_schema_name, envelope,
        source_name=source_name or envelope.get("name", "map-file"),
    )
    augmented = schema_store.get_schema(target_schema_name)
    proposal, provenance = _reconcile_map(
        table, field_set, augmented, vendor,
        override_index=override_index,
        headers_only=headers_only, client=client, propose_mapping_fn=propose_mapping_fn,
    )
    proposal = validate(table, proposal, field_set, strictness=strictness)
    return MapResult(proposal, table, provenance, profile_id=None)


# --- Phase 10: date-order resolution (D-10-04..08) ---------------------------


@dataclass(frozen=True)
class DateResolution:
    """What `resolve_date_formats` decided for every date-typed mapped
    column in one file: `formats` threads straight into `canonical.assemble`/
    `validation.validator.validate`'s `date_formats` override; `question`
    carries whatever ambiguous columns still need a human's one-time answer
    (D-10-07); `contradictions` names, per field, one raw value that proves
    a DECLARED `date_format` wrong even though `strptime` never raised on it
    (D-10-06)."""

    formats: dict[str, str]
    question: DateFormatQuestion
    contradictions: dict[str, str]


class UnresolvedDateColumnsError(Exception):
    """Raised by `resolve_date_formats` when the caller passes an explicit
    `answers` mapping that does NOT cover every ambiguous date column it
    still finds -- mirrors `UnresolvedConflictsError`'s fail-closed shape
    verbatim (a route maps this to HTTP 422 in a later plan).

    `answers=None` (the default, first-pass call) never raises: it simply
    returns the still-open conflicts in `DateResolution.question` for a
    caller to present. Only a caller that supplies `answers` -- even an
    empty dict -- is asserting "resolve everything now", so an omission at
    that point is a fail-closed error, not silent forward progress.
    """

    def __init__(self, columns: tuple[DateFormatConflict, ...]):
        self.columns = columns
        names = ", ".join(f"{c.target_field!r} ({c.source_column!r})" for c in columns)
        super().__init__(
            "Cannot resolve dates: every ambiguous date column must be explicitly "
            f"answered, but these were left undecided: {names}."
        )


def resolve_date_formats(
    table: RawTable,
    proposal: MappingProposal,
    field_set: FieldSet,
    *,
    answers: Mapping[str, DateOrder] | None = None,
) -> DateResolution:
    """The always-runs, pure-Python date-order resolver (D-10-04): for every
    mapped column feeding a `type="date"` field, classify its own evidence
    and decide what -- if anything -- resolves for it. Makes no network
    call and needs no API key; behaves identically whatever `headers_only`
    is (D-10-05), since it only ever reads `table` directly.

    Decision table, one branch per row (`_resolve_one_column`):

    | column classification | declared date_format | human answer | outcome |
    |---|---|---|---|
    | DAY_FIRST/MONTH_FIRST/ISO | none | -- | resolve to the detected format |
    | DAY_FIRST/MONTH_FIRST/ISO | present, order AGREES | -- | resolve to the detected format |
    | DAY_FIRST/MONTH_FIRST | present, order CONTRADICTS | -- | contradiction -- no override (D-10-06) |
    | EXCEL_SERIAL | any | -- | resolve to EXCEL_SERIAL_MARKER |
    | AMBIGUOUS | none | none | conflict -- ask the human (D-10-07) |
    | AMBIGUOUS | none | present | resolve to the answered order's format for THIS column |
    | AMBIGUOUS | present, PARSES every value | -- | trust the declaration -- earned: the data cannot refute the claim |
    | AMBIGUOUS | present, REFUTED by a value | none | contradiction + conflict -- ask the human; a stale/wrong declaration is not blindly trusted (quick-260712-qgc/D-10-06) |
    | AMBIGUOUS | present, REFUTED by a value | present | resolve to the answered order's format -- the answer overrides the stale declaration for THIS run only |
    | INVALID/NON_DATE | any | -- | no resolution; the existing validator flag path owns it |

    A date-typed field with `source_column=None` (unmapped/inferred) is
    skipped entirely; a non-date-typed field is never touched.

    The detected order is a fact about THIS upload's column, never written
    back to the stored `Schema`/`Field` -- a different vendor's file may use
    the opposite order for the same target field (10-RESEARCH.md
    Anti-Patterns). Threaded through `canonical.assemble()`/`validate()` as
    a per-run override only.

    Raises `UnresolvedDateColumnsError` when `answers` is supplied (even
    empty) but leaves an ambiguous column undecided -- fail closed.
    """
    fields_by_name = {f.name: f for f in field_set.fields}
    resolved_answers = answers or {}
    formats: dict[str, str] = {}
    contradictions: dict[str, str] = {}
    conflicts: list[DateFormatConflict] = []

    for mapping in proposal.field_mappings:
        target_field = fields_by_name.get(mapping.target_field)
        if target_field is None or target_field.type != "date" or mapping.source_column is None:
            continue
        values = _mapped_column_values(table, mapping.source_column)
        column = date_order.classify_column(values)
        _resolve_one_column(
            mapping, target_field, column, values, resolved_answers, formats, contradictions, conflicts
        )

    if answers is not None and conflicts:
        raise UnresolvedDateColumnsError(tuple(conflicts))

    return DateResolution(
        formats=formats, question=DateFormatQuestion(tuple(conflicts)), contradictions=contradictions
    )


def _resolve_one_column(
    mapping: FieldMapping,
    target_field: Field,
    column: date_order.DateColumnFormat,
    values: list[str],
    answers: Mapping[str, DateOrder],
    formats: dict[str, str],
    contradictions: dict[str, str],
    conflicts: list[DateFormatConflict],
) -> None:
    """One column's verdict, per the decision table on `resolve_date_formats`."""
    name = target_field.name
    declared = target_field.date_format

    if column.order == DateOrder.EXCEL_SERIAL:
        formats[name] = date_order.EXCEL_SERIAL_MARKER
        return
    if column.order in (DateOrder.INVALID, DateOrder.NON_DATE):
        return
    if column.order == DateOrder.AMBIGUOUS:
        if declared is not None and date_order.parses_all(values, declared):
            formats[name] = declared
            return
        answer = answers.get(name)
        if answer is not None:
            formats[name] = date_order.format_for_order(column, answer)
            return
        if declared is not None:
            # The declaration was refuted by the data (D-10-06): the human's
            # claim cannot be trusted, but Python cannot pick an order on its
            # own either -- ask, and while unanswered carry the honest
            # contradiction note (not the generic conversion note).
            contradictions[name] = column.example_values[0] if column.example_values else ""
        conflicts.append(
            DateFormatConflict(
                target_field=name,
                source_column=mapping.source_column,
                day_first_format=column.day_first_format,
                month_first_format=column.month_first_format,
                example_values=column.example_values,
                ambiguous_row_count=_non_blank_count(values),
            )
        )
        return

    # DAY_FIRST / MONTH_FIRST / ISO -- a provably resolved order.
    implied = date_order.implied_order(declared) if declared is not None else None
    if implied is not None and implied != column.order:
        contradictions[name] = column.example_values[0] if column.example_values else ""
        return
    formats[name] = column.date_format


def _mapped_column_values(table: RawTable, source_column: str) -> list[str]:
    """Every raw value in `source_column`, in row order -- mirrors
    `canonical._column_index`'s "an empty string is a valid header" rule
    (only a header absent from `table.headers` yields nothing)."""
    try:
        col_index = table.headers.index(source_column)
    except ValueError:
        return []
    return [row[col_index] for row in table.rows if col_index < len(row)]


def _non_blank_count(values: list[str]) -> int:
    """How many rows actually carried evidence for this column -- the count
    the review panel can still show honestly under `headers_only`, once the
    wire layer redacts `example_values` (D-10-05, `DateFormatConflict`'s own
    docstring)."""
    return sum(1 for v in values if v.strip())


# --- Phase 10: Python-first alias pre-fill + Schema->FieldSet adapter --------
# (D-10-02/03, INGEST-02)


def field_set_from_schema(schema: Schema) -> FieldSet:
    """D-10-02: the selected Schema's canonical fields ARE the mapper's
    target fields -- there is no separate, user-facing field-set concept
    anymore (`FieldSet` stays an internal derivation only).

    `FieldSet.signature` is computed only from each `Field`'s own attributes
    (name/type/unit/allowed_values/required/min/max/date_format --
    `fields/models.py:66`), never from alias data, so a Schema-derived
    `FieldSet` produces the EXACT SAME signature a previously-promoted
    field-set-derived one did -- an already-learned profile keeps matching
    (10-RESEARCH.md, State of the Art). Removing a canonical field
    (Plan 02's tombstone) is already absent from `schema.fields` by the
    store's own structural filter, so it is absent here too with no extra
    filtering -- and the signature correctly CHANGES in that case, since a
    different target field set no longer matches an old profile (intended,
    not a bug).
    """
    return FieldSet(name=schema.name, fields=tuple(cf.field for cf in schema.fields))


def _vendor_agnostic_alias_index(schema: Schema) -> dict[str, str | None]:
    """normalised_header -> canonical_field_name, or `None` when the SAME
    normalised header maps to two DIFFERENT canonical fields across
    different vendors -- an unresolvable collision that must never guess
    which vendor is right (T-10-12).

    Unlike `_alias_index` (keyed `(vendor, header)`, meaningful only when a
    reconcile already has a chosen vendor), a PLAIN upload under the locked
    D-10-01 three-control UI has no vendor selector in the mapping path at
    all -- this is a genuinely new, vendor-agnostic index, not a call to
    `_alias_index` with a narrower key (10-RESEARCH.md Pattern 3).

    A tombstoned alias never appears here at all: it is already absent from
    `schema.fields[*].aliases` by the store's own structural filter
    (Plan 02) by the time this function ever sees it (T-10-13).
    """
    index: dict[str, str] = {}
    collided: set[str] = set()
    for canonical_field in schema.fields:
        for alias in canonical_field.aliases:
            key = _normalise_header(alias.source_column)
            if key in index and index[key] != canonical_field.field.name:
                collided.add(key)
            else:
                index[key] = canonical_field.field.name
    return {key: (None if key in collided else value) for key, value in index.items()}


@dataclass(frozen=True)
class VendorMemory:
    """What `recall_vendor` resolved, and how (10-09/INGEST-02).

    `vendor` is `None` whenever nothing may safely be pre-filled -- either no
    match was found at all, or (the load-bearing anti-guessing case) TWO OR
    MORE vendors' crosswalk aliases match the file's columns and the tool
    refuses to pick one. `source` names which stage resolved it
    (`"profile"`/`"crosswalk"`), or `None` alongside a `None` vendor.
    `candidates` is only ever non-empty in the ambiguous case -- every other
    outcome (a clean hit, or no match at all) carries an empty tuple.
    """

    vendor: str | None
    source: str | None
    candidates: tuple[str, ...]


def recall_vendor(
    table: RawTable,
    field_set: FieldSet,
    schema: Schema | None,
    store: ProfileStore | None,
) -> VendorMemory:
    """The remembered-vendor lookup (10-09/INGEST-02): the vendor is a human
    assertion, never derivable from the file itself, but once a column
    signature has been confirmed once asking again is friction this removes.

    Resolves in a FIXED escalation order, mirroring D-10-03's own shape --
    each stage only runs if the previous found nothing:

    1. Exact, learned, unambiguous. `store.find(field_set.signature,
       column_signature(table.headers))`. `ProfileRow`'s own
       `UniqueConstraint(field_set_signature, column_signature)` means this
       returns at most one row, so a hit here is unambiguous BY CONSTRUCTION
       -- the database guarantees it, no tie-break logic is needed or
       permitted. A hit with no recorded vendor (a profile saved before this
       plan, or one saved by the CLI) falls through to the crosswalk stage,
       exactly as a miss would.

    2. Crosswalk fallback. Only when (1) found nothing and a `schema` was
       targeted: the DISTINCT vendors whose alias source columns match this
       table's headers (tombstoned aliases are already absent from
       `schema.fields[*].aliases` by the store's own filter, D-10-15).
       Exactly one distinct vendor resolves cleanly; two or more is
       GENUINELY AMBIGUOUS and this function refuses to pick one -- no
       tie-break by alias count, recency, or match count, because every one
       of those is a guess wearing a heuristic's clothes, and a wrong vendor
       writes a wrong alias into a governed crosswalk that a later file then
       trusts at confidence 1.0. Both names are returned, sorted, for the
       human to choose from.

    3. Zero match anywhere -- an empty `VendorMemory`, exactly as if the
       field were asked fresh today.

    `store=None` or `schema=None` degrade gracefully to whichever stages
    remain meaningful, never raising -- mirrors `ProfileStore.find`'s own
    "never raises" contract.
    """
    if store is not None:
        profile = store.find(field_set.signature, column_signature(table.headers))
        if profile is not None and profile.vendor is not None:
            return VendorMemory(vendor=profile.vendor, source="profile", candidates=())

    if schema is None:
        return VendorMemory(vendor=None, source=None, candidates=())

    normalised_headers = {_normalise_header(h) for h in table.headers}
    vendors: set[str] = set()
    for canonical_field in schema.fields:
        for alias in canonical_field.aliases:
            if _normalise_header(alias.source_column) in normalised_headers:
                vendors.add(alias.vendor)

    if len(vendors) == 1:
        return VendorMemory(vendor=next(iter(vendors)), source="crosswalk", candidates=())
    if len(vendors) >= 2:
        return VendorMemory(vendor=None, source=None, candidates=tuple(sorted(vendors)))
    return VendorMemory(vendor=None, source=None, candidates=())


@dataclass(frozen=True)
class Escalation:
    """How many of a field set's fields the Python crosswalk pre-fill
    covered vs how many Claude was asked for -- the Review screen's own
    escalation line (a future plan renders it; `python=4, claude=2,
    total=6`)."""

    python_matched: int
    claude_matched: int
    total: int


def _prefill_coverage(
    table: RawTable, field_set: FieldSet, schema: Schema
) -> tuple[dict[str, FieldMapping], tuple[Field, ...]]:
    """The pure, no-LLM computation both `_python_first_prefill` (to build
    the real merged proposal) and `resolve_or_map` (to report `Escalation`
    counts without a second mapper call) share: which of `field_set`'s
    fields the vendor-agnostic crosswalk covers for THIS table's headers,
    and the reduced tuple of fields that remain uncovered.

    Matching uses column NAMES only (`table.headers`, never `table.rows`),
    so a `headers_only` table yields the identical result (T-08-04 mirrored
    for the plain-upload path)."""
    index = _vendor_agnostic_alias_index(schema)
    prefilled: dict[str, FieldMapping] = {}
    for header in table.headers:
        canonical_name = index.get(_normalise_header(header))
        if canonical_name is not None and canonical_name not in prefilled:
            prefilled[canonical_name] = FieldMapping(
                target_field=canonical_name,
                source_column=header,
                confidence=1.0,
                reasoning=f"pre-filled from the schema crosswalk for {header!r}",
                needs_confirmation=False,
            )
    remaining = tuple(f for f in field_set.fields if f.name not in prefilled)
    return prefilled, remaining


def _python_first_prefill(
    table: RawTable,
    field_set: FieldSet,
    schema: Schema,
    *,
    headers_only: bool,
    client=None,
    propose_mapping_fn=None,
) -> tuple[MappingProposal, Escalation]:
    """D-10-03/INGEST-02: the deterministic Python-first pass for a PLAIN
    upload (no reconcile, no chosen vendor) -- pre-fill every header whose
    normalised name matches the Schema's vendor-agnostic crosswalk at
    confidence 1.0 with `needs_confirmation=False`, then call the mapper
    ONLY on whatever remains -- or not at all, when every field is covered
    (the demo money shot: zero Claude calls).

    Mirrors `_reconcile_map`'s own pre-fill/reduce/merge loop almost
    verbatim (10-RESEARCH.md Pattern 3), swapping the vendor-scoped index
    for the vendor-agnostic one -- this is a NEW function, not a call to
    `_reconcile_map` itself, and `_reconcile_map`/`_alias_index` are never
    touched by this plan (D-07-04 augment-only invariant stays intact).

    Returns the merged `MappingProposal` plus an `Escalation` naming exactly
    how many fields Python matched vs how many Claude was asked for.
    """
    fn = propose_mapping_fn if propose_mapping_fn is not None else propose_mapping
    prefilled, remaining = _prefill_coverage(table, field_set, schema)

    mapped: dict[str, FieldMapping] = {}
    if remaining:
        reduced = FieldSet(name=field_set.name, fields=remaining)
        proposal = fn(table, reduced, client, headers_only=headers_only)
        mapped = {m.target_field: m for m in proposal.field_mappings}

    merged = [
        prefilled.get(name) or mapped[name]
        for name in field_set.field_names
        if name in prefilled or name in mapped
    ]
    escalation = Escalation(
        python_matched=len(prefilled), claude_matched=len(mapped), total=len(field_set.fields)
    )
    return (
        MappingProposal(source_columns=list(table.headers), field_mappings=merged),
        escalation,
    )
