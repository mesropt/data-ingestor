"""Orchestration used by both the CLI and the API — decides, never renders.

`cli.py`'s private, print-coupled orchestration (`_resolve_proposal`,
`_map_one`, `_save_profile_if_ready`, `_export_if_ready`) both *decided* what
to do and *rendered* the result to stdout in the same function. That mixing
is fine for a single CLI adapter, but `.claude/CLAUDE.md`'s own convention
("Public API is everything not prefixed with `_`") makes it a boundary
violation for a second adapter (a future `api/` package) to import a
`cli._foo` name directly — and several of those functions `print()`, which
is wrong for a function an HTTP endpoint calls.

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import canonical
from .canonical import CanonicalTable
from .domain.models import FieldMapping, MappingProposal
from .export.writers import build_manifest, write_csv, write_json, write_xlsx
from .fields.models import FieldSet
from .learning.profile import LearnedProfile
from .learning.reconstruct import reconstruct_proposal, stored_mapping_from
from .learning.signature import column_signature
from .learning.store import ProfileStore
from .mapping.mapper import propose_mapping
from .parsing.hint import StructuralHint, StructureQuestion
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


@dataclass(frozen=True)
class MapResult:
    """What the CLI prints and a future API returns as JSON -- identical
    data, two renderers. `profile_id` is set only on the auto-applied
    branch (the CLI's exact "applied saved profile {id} (no Claude call)"
    message needs it; the fresh-Claude branch has no profile to name)."""

    proposal: MappingProposal
    table: RawTable
    provenance: str
    profile_id: str | None = None


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
) -> tuple[MappingProposal, str, str | None]:
    """The per-table auto-apply/fresh-Claude decision (LEARN-03/04,
    D-05/D-08) -- decides, never renders. Mirrors `cli._resolve_proposal`'s
    exact logic (PATTERNS.md cli.py:490-533), copied almost unchanged.

    Returns `(proposal, provenance, profile_id)` -- `profile_id` is `None`
    on the fresh-Claude branch. Raises `MissingCredentialsError` instead of
    the old `(None, "missing-credentials")` sentinel, and `ValueError`
    verbatim (naming the consequence) when `field_set` is `None` and
    credentials ARE configured -- the "error names the consequence"
    convention (CLAUDE.md).

    Auto-apply constructs no Anthropic client and checks no credentials at
    all (Pattern 5/Pitfall 3): the credential check only ever runs on the
    miss branch, immediately before a Claude call is actually about to
    happen.

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
) -> MapResult | StructureQuestion:
    """The single seam a future `POST /api/upload` route calls: parse the
    file, return the human's structural question unchanged when the parser
    is unsure, otherwise resolve (auto-apply or fresh-Claude) and validate.
    Never prints; never called from `cli.run()`'s own flow in this plan --
    `cli.py` keeps its existing per-sheet `resolve_or_ask`/`_map_and_report`
    loop, wired through `resolve_table_mapping` instead (below).

    `validate()` runs here on BOTH branches (D-03) before the result is
    returned -- a profile's or Claude's own confidence never exempts a
    value from a declared constraint, matching the RESEARCH.md upload
    sequence ("validate() -- runs on both branches").
    """
    outcome = parse(path, sheet=sheet, hint=hint)
    if isinstance(outcome, StructureQuestion):
        return outcome
    table = outcome

    proposal, provenance, profile_id = resolve_table_mapping(
        table, field_set, store,
        headers_only=headers_only, client=client, propose_mapping_fn=propose_mapping_fn,
    )
    if field_set is not None:
        proposal = validate(table, proposal, field_set, strictness=strictness)
    return MapResult(proposal, table, provenance, profile_id)


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
) -> ConfirmResult:
    """The P1 server-side confirm gate (mirrors `cli._map_one`'s recompute
    order, PATTERNS.md cli.py:567-592): rebuild a FRESH `MappingProposal`
    from the human's edited column choices, re-run `validate()`, and read
    `is_ready` off the freshly-built object -- never off anything the caller
    claims. A tampered/stale `needs_confirmation=False` in `edited_mappings`
    cannot survive this recomputation (`reconstruct.py`'s "build fresh, then
    validate, never trust the source's readiness claim" idiom, applied to
    an HTTP body instead of a stored profile).

    Raises `NotReadyError` when any field is still yellow -- there is no
    "blocked" return value, so every caller is forced to handle the gate
    explicitly, never silently proceed on a partial mapping.
    """
    proposal = MappingProposal(
        source_columns=list(table.headers), field_mappings=list(edited_mappings)
    )
    proposal = validate(table, proposal, field_set, strictness=strictness)
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)

    tidy = canonical.assemble(table, proposal, field_set)
    manifest = build_manifest(
        field_set, table.headers, proposal, provenance=provenance, strictness=strictness
    )
    profile_id = None
    if save_profile:
        profile_id = save_profile_if_ready(store, field_set, table, proposal, hint)
    return ConfirmResult(proposal, tidy, manifest, profile_id)


def save_profile_if_ready(
    store: ProfileStore | None,
    field_set: FieldSet | None,
    table: RawTable,
    proposal: MappingProposal,
    hint: StructuralHint | None,
) -> str:
    """LEARN-02/06 (mirrors `cli._save_profile_if_ready`, PATTERNS.md
    cli.py:595-624): persist a confirmed mapping as a profile for future
    auto-apply. Blocked unless the mapping is fully clear -- a yellow
    field's column-to-field association is not yet a curator-confirmed
    fact. Any structural hint the file needed is persisted with the profile
    (D-07) so the same odd layout parses automatically next time.

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
    """
    if not proposal.is_ready:
        raise NotReadyError(proposal.unclear_fields)
    export_dir.mkdir(parents=True, exist_ok=True)
    write_csv(tidy, export_dir / "export.csv")
    write_xlsx(tidy, export_dir / "export.xlsx")
    write_json(tidy, export_dir / "export.json")
    manifest = build_manifest(
        field_set, table.headers, proposal, provenance=provenance, strictness=strictness
    )
    (export_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest
