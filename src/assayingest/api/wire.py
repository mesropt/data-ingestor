"""HTTP wire models -- the Pydantic siblings of `mapping/schema.py`'s
Claude-facing wire models, but for the browser instead of Claude (Pattern
4/5). These live at the HTTP boundary only; they are never mixed into
`domain/models.py` (the same wire<->domain discipline `mapping/schema.py`'s
own module docstring states, applied in the opposite direction).

`MappingResponse`/`FieldMappingOut` are populated FROM
`cli.proposal_to_dict()` (never a second, hand-derived shape) plus
`validator_note`, which that dict omits (PATTERNS.md api/wire.py notes) --
the one place this module extends rather than mirrors byte-for-byte.
`StructuralQuestionResponse` reuses `StructureQuestion.to_dict()` verbatim,
adding only `kind` and `upload_token` (Pattern 5).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..cli import proposal_to_dict
from ..domain.models import DateFormatQuestion, MappingProposal, ReconcileQuestion, Schema
from ..parsing.hint import StructureQuestion
from ..parsing.structure.layout import KeyValueBlock, LayoutKind, SheetLayout
from ..service import Escalation, SchemaProposal, SheetManifestEntry, VendorMemory

#: A deliberately minimal email sanity check (D-06-03: "do not over-engineer
#: policy", ASVS L1). A single `@` with non-empty local/domain parts is enough
#: to reject an obvious typo without adding an `email-validator` dependency for
#: a demo -- the store's UNIQUE(email) constraint owns true identity, not this.
_EMAIL_MIN_LEN = 3
_MIN_PASSWORD_LEN = 8  # D-06-03


class SignUpIn(BaseModel):
    """`POST /api/auth/signup`'s body -- a minimum-length password guard
    (D-06-03) is the ONLY strength rule; composition rules are deliberately
    out of scope (ASVS L1, "do not over-engineer")."""

    email: str
    password: str = Field(min_length=_MIN_PASSWORD_LEN)

    @field_validator("email")
    @classmethod
    def _email_has_at_sign(cls, value: str) -> str:
        local, sep, domain = value.partition("@")
        if not sep or not local or not domain:
            raise ValueError("email must contain a local part and a domain")
        return value


class SignInIn(BaseModel):
    """`POST /api/auth/login`'s body -- no length guard here: a wrong-length
    password is simply a failed credential check (401), never a 422, so an
    attacker learns nothing about stored password shape from the status code."""

    email: str
    password: str


class UserOut(BaseModel):
    """The signed-in user's public shape -- `password_hash` is NEVER a field
    here (it must never cross the wire), mirroring the wire<->domain
    discipline the module docstring states."""

    id: str
    email: str
    is_verified: bool
    auth_provider: str


class SignUpAcceptedOut(BaseModel):
    """`POST /api/auth/signup`'s 201 body -- the console-hint message telling
    the developer where the verification link was printed (D-06-04)."""

    message: str


class AuthConfigOut(BaseModel):
    """`GET /api/auth/config`'s body -- the single source of truth the
    frontend reads to decide whether to render the Google button (D-06-07)."""

    google_oauth_enabled: bool


class AlternativeOut(BaseModel):
    """Mirrors `mapping/schema.py::WireCandidate` -- the HTTP-facing shape
    for one ranked alternative column (D-02's chip UI)."""

    source_column: str
    confidence: float


class FieldMappingOut(BaseModel):
    """One target field's resolution -- field names identical to
    `cli._field_to_dict`'s dict keys, plus `validator_note` (that dict
    omits it; the wire model must add it, PATTERNS.md api/wire.py notes)."""

    target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[AlternativeOut]
    validator_note: str | None = None


class MappingResponse(BaseModel):
    """The `kind="mapping"` half of `/api/upload`'s discriminated response
    (Pattern 5). Built FROM `cli.proposal_to_dict()`'s dict so the CLI's
    JSON draft and this HTTP body never drift apart (Pattern 4).

    `escalation` (D-10-03/INGEST-02, additive, defaulted `None`) is the one
    visible proof of the Python-before-Claude mapping order: how many of the
    target Schema's fields the crosswalk pre-fill matched deterministically
    vs how many needed a Claude call. It is `None` whenever no Schema was
    targeted (the legacy `field_set`/CLI path) or the profile auto-apply
    already short-circuited everything (`service.MapResult.escalation`'s own
    docstring) -- never a misleading all-zero count on those paths.

    `remembered_vendor`/`remembered_vendor_source`/`vendor_candidates`
    (10-09/INGEST-02, additive, defaulted `None`/`None`/`[]`) mirror
    `escalation`'s own precedent exactly: the legacy `field_set`/CLI path
    returns them null/empty and nothing downstream breaks. `vendor_candidates`
    is only ever non-empty in the genuinely-ambiguous case (two or more
    vendors' aliases match) -- `remembered_vendor` is `None` in that case
    too, since the tool never picks one (`service.recall_vendor`'s own
    docstring)."""

    kind: str = "mapping"
    ready: bool
    source_columns: list[str]
    field_mappings: list[FieldMappingOut]
    provenance: str | None
    upload_token: str
    escalation: dict | None = None
    remembered_vendor: str | None = None
    remembered_vendor_source: str | None = None
    vendor_candidates: list[str] = []
    #: The uploaded file's ORIGINAL client filename (quick 260712) -- what
    #: the Review screen shows instead of the raw upload token, which means
    #: nothing to a curator. Sourced from the route's `UploadFile.filename`
    #: (or the retained `UploadEntry.source_file_name` on a resolve), never
    #: from `RawTable.source_name`, which is a tempfile's name on the API
    #: path. A display label only: nothing server-side keys on it.
    source_name: str | None = None

    @classmethod
    def from_proposal(
        cls,
        proposal: MappingProposal,
        provenance: str | None,
        upload_token: str,
        *,
        escalation: Escalation | None = None,
        vendor_memory: VendorMemory | None = None,
        source_name: str | None = None,
    ) -> "MappingResponse":
        base = proposal_to_dict(proposal, provenance)
        notes_by_field = {m.target_field: m.validator_note for m in proposal.field_mappings}
        field_mappings = [
            FieldMappingOut(**field_dict, validator_note=notes_by_field[field_dict["target_field"]])
            for field_dict in base["field_mappings"]
        ]
        escalation_out = (
            None
            if escalation is None
            else {
                "python": escalation.python_matched,
                "claude": escalation.claude_matched,
                "total": escalation.total,
            }
        )
        return cls(
            ready=base["ready"],
            source_columns=base["source_columns"],
            field_mappings=field_mappings,
            provenance=base["provenance"],
            upload_token=upload_token,
            escalation=escalation_out,
            remembered_vendor=vendor_memory.vendor if vendor_memory is not None else None,
            remembered_vendor_source=vendor_memory.source if vendor_memory is not None else None,
            vendor_candidates=list(vendor_memory.candidates) if vendor_memory is not None else [],
            source_name=source_name,
        )


class FieldSetIn(BaseModel):
    """`POST /api/field-sets`'s request body (UI-01, D-03) -- `field_set` is
    a raw JSON-safe dict (`FieldSet.to_dict()`'s shape), built into a
    validated domain `FieldSet` via `fields.loader.from_dict` at the route
    layer, never a hand-rolled parallel Pydantic re-derivation of `Field`'s
    own name/type/allowed_values guards (T-04-11)."""

    name: str
    field_set: dict


class FieldSetOut(BaseModel):
    """One saved template, as the browser's picker (UI-01) consumes it."""

    id: str
    name: str
    field_set: dict


class PromoteRequest(BaseModel):
    """`POST /api/schemas`'s request body (D-07-03, SCHEMA-01) -- `field_set`
    is a raw JSON-safe dict (`FieldSet.to_dict()`'s shape), built into a
    validated domain `FieldSet` via `fields.loader.from_dict` at the route
    (mirrors `FieldSetIn`, T-04-11), never a hand-rolled parallel Pydantic
    re-derivation. `name` is the Schema's domain identity.

    There is deliberately NO `created_by` field here BY DESIGN: the
    provenance actor is the server-resolved `user.email` from
    `require_verified_user`, never a client claim (T-07-06, mirrors confirm's
    AUTH-04 handling) -- a body attempt to set `created_by` is simply ignored
    (extra keys are dropped)."""

    name: str
    field_set: dict


class SchemaOut(BaseModel):
    """One governed Schema, as the browser's Schema selector + crosswalk view
    consume it (D-07-07): `id`, `name`, server-resolved `created_by`, and the
    canonical `fields` each with their embedded `aliases` -- exactly the
    `CanonicalField.to_dict()` shape inside `Schema.to_master_map()`, never a
    second hand-derived shape."""

    id: str
    name: str
    created_by: str | None
    fields: list[dict]

    @classmethod
    def from_schema(cls, schema: Schema) -> "SchemaOut":
        envelope = schema.to_master_map()
        return cls(
            id=envelope["id"],
            name=envelope["name"],
            created_by=envelope["created_by"],
            fields=envelope["fields"],
        )


class SchemaRenameIn(BaseModel):
    """The body of `PATCH /api/schemas/{name}` (quick 260712) -- the Schema's
    new name. Uniqueness and blankness are judged in `service.rename_schema`
    (the domain owns identity rules), not by a second Pydantic-level guard
    here; the route only maps the typed errors to HTTP."""

    name: str


class SchemaFieldIn(BaseModel):
    """The body of `POST /api/schemas/{name}/fields` and
    `PATCH /api/schemas/{name}/fields/{field_name}` (D-10-12, INGEST-05):
    `field` is a raw JSON-safe dict (`Field.to_dict()`'s shape), built into a
    validated domain `Field` via `fields.loader.from_dict` at the SERVICE
    layer (mirrors `FieldSetIn`/`PromoteRequest`'s T-04-11 discipline) --
    never a hand-rolled parallel Pydantic re-derivation of `Field`'s own
    name/type guards. On a PATCH, `field["name"]` may differ from the URL's
    `field_name` -- that is the rename affordance."""

    field: dict


class SchemaAliasIn(BaseModel):
    """The body of `POST /api/schemas/{name}/fields/{field_name}/aliases`
    (D-10-12) -- a manually-recorded vendor alias. There is deliberately NO
    `provenance_actor` field here BY DESIGN (T-07-06, mirrors
    `PromoteRequest`): the actor is always the server-resolved `user.email`
    from `require_verified_user`, never a client claim -- a body attempt to
    set it is simply ignored (extra keys are dropped). The DELETE-alias
    route takes `vendor`/`source_column` as query params instead (a DELETE
    with a body is awkward), so it needs no body model of its own."""

    vendor: str
    source_column: str


class ConfirmFieldMappingIn(BaseModel):
    """One edited field mapping in a `POST /api/confirm` body -- the human's
    column CHOICE is legitimately client-editable (D-02), so `target_field`/
    `source_column`/`confidence`/`reasoning`/`inferred_value`/`alternatives`
    are trusted as the curator's editorial input. `needs_confirmation` is
    accepted here only as the FRESH `MappingProposal`'s starting point
    (`service.confirm`'s docstring: "rebuild ... from the human's edited
    column choices") -- `validate()` re-runs immediately after and may only
    ever OR a violation back in, never trust this value as the final verdict
    (P1, `validation/validator.py`'s additive-only discipline). No top-level
    `ready`/`is_ready` field exists anywhere on this wire model or its parent
    `ConfirmRequest` BY DESIGN -- there is nothing for a tampered client to
    send that the gate could read."""

    target_field: str
    source_column: str | None
    confidence: float
    reasoning: str
    needs_confirmation: bool
    inferred_value: str | None = None
    alternatives: list[AlternativeOut] = []


class ConfirmRequest(BaseModel):
    """`POST /api/confirm`'s request body (API-02, P1). Deliberately holds
    NO `table`/`source_columns`/`headers` field and NO `signature` field --
    the server always rebuilds both from the ORIGINAL retained upload
    (`upload_token` -> `api.state.registry`), never from anything the client
    sends (Server-Side Gate table, RESEARCH.md). `field_set` is parsed only
    to prove the client still agrees with the server-retained field set (by
    signature); any drift is rejected (CR-01) -- the retained
    `entry.field_set` is what the gate actually validates/assembles
    against. `provenance` plays no role in the gate AND is no longer used
    for the audit manifest either (WR-04): the server retains the real
    provenance from upload/resolve time (`api.state.UploadEntry.provenance`)
    and writes that into the manifest, so a client cannot mislabel a
    fresh-Claude mapping as auto-applied (or vice versa) in the persisted
    audit record. This field is kept only for backward wire compatibility."""

    upload_token: str
    field_set: dict
    field_mappings: list[ConfirmFieldMappingIn]
    save_profile: bool = False
    export: bool = False
    provenance: str = "fresh-claude"
    #: ALIAS-04 (D-07-05/06, additive, default None -- fully backward
    #: compatible): the target governed Schema + the vendor label to accrete
    #: the crosswalk into. When BOTH are present the confirm route records each
    #: resolved source column as a `manual` alias whose provenance actor is the
    #: server-resolved `user.email` (never a body field, T-07-10); `vendor` is
    #: a free-text client label carrying no authority (D-07-06). When either is
    #: absent nothing is written -- the existing confirm contract is unchanged.
    schema_name: str | None = None
    vendor: str | None = None


class ConfirmResponse(BaseModel):
    """A successful `POST /api/confirm`'s 200 body -- `export` carries the
    four download URLs only when the request asked for `export=true`."""

    ready: bool = True
    manifest: dict
    profile_id: str | None = None
    export: dict[str, str] | None = None


class StructuralQuestionResponse(BaseModel):
    """The `kind="structural_question"` half of `/api/upload`'s
    discriminated response (Pattern 5) -- `StructureQuestion.to_dict()`'s
    shape plus `kind` and `upload_token`."""

    kind: str = "structural_question"
    unsure_about: str
    reason: str
    confidence: float
    proposal: dict | None
    alternatives: list[dict]
    evidence_rows: list[list[str]]
    answerable_by_hint: bool
    upload_token: str

    @classmethod
    def from_question(
        cls, question: StructureQuestion, upload_token: str
    ) -> "StructuralQuestionResponse":
        return cls(upload_token=upload_token, **question.to_dict())


class KeyValueBlockIn(BaseModel):
    """One label/value block of the human's CONFIRMED key-value answer
    (12-UI-SPEC Discretion 3): selecting "Labels down the side" submits
    confirmation of CLAUDE'S blocks, never indices the browser invented -- the
    row-click on the evidence grid still sets only `header_row_index`.

    Every index is `ge=0` at the boundary, because a negative index cannot be
    true of ANY grid: a client error is a 422 here (the `ReconcileChoiceIn.
    decision` Literal idiom -- "never a silent mis-apply"), never an
    `IndexError` surfacing from deep inside the un-pivot as a 500. That is the
    WR-02 bug class -- a client input error dressed as a server error -- fixed
    once and deliberately not reintroduced (T-12-15, ASVS V5).

    Whether an index is true of THIS file's grid cannot be known here (the grid
    is not open yet): that is the route's own bounds check, against the
    re-parsed file, before any allocation. Two closures, neither redundant --
    this one refuses what is impossible anywhere, that one refuses what is
    merely false here."""

    label_column: int = Field(ge=0)
    value_columns: list[int] = Field(min_length=1)
    first_row: int = Field(ge=0)
    last_row: int = Field(ge=0)

    @field_validator("value_columns")
    @classmethod
    def _columns_are_non_negative(cls, value: list[int]) -> list[int]:
        if any(column < 0 for column in value):
            raise ValueError("a value column index cannot be negative")
        return value

    @model_validator(mode="after")
    def _rows_are_in_order(self) -> "KeyValueBlockIn":
        if self.first_row > self.last_row:
            raise ValueError("a block's first_row cannot come after its last_row")
        return self


class SheetLayoutIn(BaseModel):
    """The human's CONFIRMED layout answer, mirroring the domain `SheetLayout`
    exactly -- indices included, because a confirmed key-value answer must carry
    the blocks Python un-pivots from (they are the transform's ONLY input).

    `kind` is a `Literal` over the real `LayoutKind` values, derived from the
    enum itself so the two vocabularies cannot drift: an invented kind is a 422
    AT THE BOUNDARY, never a `ValueError` from `LayoutKind(...)` surfacing as a
    500. Sign and internal order are judged here; grid bounds are the route's
    (see `KeyValueBlockIn`).

    This is what finally supersedes `table_shape`, which was WRITE-ONLY (two
    writes, zero reads) and is why the old shape question had to advertise
    itself as unanswerable (D-12-15)."""

    kind: Literal[
        "row_per_record", "key_value", "wide_matrix", "multiple_tables", "not_a_table", "unknown"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    header_row_index: int | None = Field(default=None, ge=0)
    first_data_row: int | None = Field(default=None, ge=0)
    last_data_row: int | None = Field(default=None, ge=0)
    key_value_blocks: list[KeyValueBlockIn] = []
    one_record_per_value_column: bool = False

    @model_validator(mode="after")
    def _data_rows_are_in_order(self) -> "SheetLayoutIn":
        if (
            self.first_data_row is not None
            and self.last_data_row is not None
            and self.first_data_row > self.last_data_row
        ):
            raise ValueError("first_data_row cannot come after last_data_row")
        return self

    def to_domain(self) -> SheetLayout:
        return SheetLayout(
            kind=LayoutKind(self.kind),
            confidence=self.confidence,
            reasoning=self.reasoning,
            header_row_index=self.header_row_index,
            first_data_row=self.first_data_row,
            last_data_row=self.last_data_row,
            key_value_blocks=tuple(
                KeyValueBlock(
                    label_column=block.label_column,
                    value_columns=tuple(block.value_columns),
                    first_row=block.first_row,
                    last_row=block.last_row,
                )
                for block in self.key_value_blocks
            ),
            one_record_per_value_column=self.one_record_per_value_column,
        )


class StructuralHintIn(BaseModel):
    """`StructuralHint`'s wire shape (UI-02, D-04) -- every field optional,
    mirroring the domain dataclass exactly so the inline hint form can send
    only the one dimension in question.

    `layout` (12-05) is the human's answer to the layout question, and the
    round trip that makes `answerable_by_hint=True` finally MEAN something: it
    re-enters `parse()` as a validated hint, `parse()` reads it, and the sheet
    maps. `table_shape` stays only because saved learning profiles already
    serialise it; new code writes `layout`."""

    sheet_name: str | None = None
    header_row_index: int | None = None
    delimiter: str | None = None
    decimal_separator: str | None = None
    data_region: str | None = None
    table_shape: str | None = None
    layout: SheetLayoutIn | None = None


class StructuralHintResolveRequest(BaseModel):
    """`POST /api/structural-hint/resolve`'s request body -- `upload_token`
    finds the retained temp file (`api.state.registry`); `hint` is the
    human's answer to re-parse with (Pattern 5)."""

    upload_token: str
    hint: StructuralHintIn


class ReconcileQuestionResponse(BaseModel):
    """The `kind="reconcile_question"` third arm of `/api/upload`'s
    discriminated response (Pattern 5, D-08-03) -- surfaced when an uploaded
    map file disagrees with the master crosswalk. Reuses
    `ReconcileQuestion.to_dict()`'s `conflicts` shape VERBATIM (mirroring
    `StructuralQuestionResponse.from_question`), adding only `kind`,
    `upload_token`, and the retained `schema_name`/`vendor` the resolve step
    needs -- never a second hand-derived conflict shape."""

    kind: str = "reconcile_question"
    upload_token: str
    schema_name: str
    vendor: str
    conflicts: list[dict]

    @classmethod
    def from_question(
        cls,
        question: ReconcileQuestion,
        upload_token: str,
        schema_name: str,
        vendor: str,
    ) -> "ReconcileQuestionResponse":
        return cls(
            upload_token=upload_token,
            schema_name=schema_name,
            vendor=vendor,
            conflicts=question.to_dict()["conflicts"],
        )


class ReconcileChoiceIn(BaseModel):
    """One human resolution of one conflict in a `POST /api/reconcile/resolve`
    body. `decision` is a Literal so an invalid value is a 422 AT THE BOUNDARY
    (never a silent mis-apply): `keep_master` keeps the master's stored
    canonical field for this `(vendor, source_column)` pair, `take_map_file`
    takes the map file's asserted field for THIS run (D-08-02 step 2). `vendor`
    is a free-text source label carrying no authority (D-07-06)."""

    vendor: str
    source_column: str
    decision: Literal["keep_master", "take_map_file"]


class ReconcileResolveRequest(BaseModel):
    """`POST /api/reconcile/resolve`'s request body (D-08-03) -- `upload_token`
    finds the retained map envelope + target Schema + vendor + temp file
    (`api.state.registry`, mirroring `StructuralHintResolveRequest`); `choices`
    is the human's per-conflict answer. The choices only PICK a per-conflict
    side; the real map envelope/schema/vendor are server-retained under the
    token, never re-sent by the client (T-08-08)."""

    upload_token: str
    choices: list[ReconcileChoiceIn]


class DateFormatColumnOut(BaseModel):
    """One date-typed field whose mapped column Python could not resolve on
    its own -- `DateFormatConflict.to_dict()`'s shape verbatim (D-10-07)."""

    target_field: str
    source_column: str
    day_first_format: str
    month_first_format: str
    example_values: list[str]
    ambiguous_row_count: int


class DateFormatQuestionResponse(BaseModel):
    """The `kind="date_question"` 4th arm of `/api/upload`'s discriminated
    response (Pattern 5, D-10-07) -- surfaced when one or more mapped
    date-typed columns are genuinely order-ambiguous and no declared format
    covers them. Bundles EVERY ambiguous column from this upload into ONE
    question (Discretion #2, `10-UI-SPEC.md`) -- never one question per
    column.

    `from_question`'s `headers_only` kwarg is where D-10-05's privacy rule
    becomes concrete AT THE WIRE BOUNDARY, in exactly ONE place: the domain
    `DateFormatConflict` always carries its raw `example_values` (detection
    itself is unaffected by `headers_only`, D-10-05) -- redaction is never
    the detector's job, never the panel's job, only this classmethod's.
    `ambiguous_row_count` is never redacted: it is the one honest thing the
    review panel can still say under headers_only, mirroring
    `StructuralHintPanel`'s existing evidence-grid redaction rule."""

    kind: str = "date_question"
    upload_token: str
    columns: list[DateFormatColumnOut]

    @classmethod
    def from_question(
        cls, question: DateFormatQuestion, upload_token: str, *, headers_only: bool
    ) -> "DateFormatQuestionResponse":
        columns = []
        for conflict in question.conflicts:
            raw = conflict.to_dict()
            if headers_only:
                raw["example_values"] = []
            columns.append(DateFormatColumnOut(**raw))
        return cls(upload_token=upload_token, columns=columns)


class DateFormatChoiceIn(BaseModel):
    """One human resolution of one ambiguous date column in a
    `POST /api/date-format/resolve` body (D-10-07). `order` is a Literal so
    an invalid value is a 422 AT THE BOUNDARY (mirrors `ReconcileChoiceIn.
    decision`).

    There is deliberately NO `date_format` field here BY DESIGN (T-10-21):
    mirrors `ConfirmRequest`'s "there is nothing for a tampered client to
    send that the gate could read" -- the server re-classifies the retained
    column and derives the concrete strptime format for the chosen order
    itself (`service.resolve_date_formats` -> `date_order.format_for_order`),
    exactly as it did on the first pass. A client that sends an extra
    `date_format` key gets it silently dropped (Pydantic's default `extra`
    behavior); it is never read anywhere on this path."""

    target_field: str
    order: Literal["day_first", "month_first"]


class DateFormatResolveRequest(BaseModel):
    """`POST /api/date-format/resolve`'s request body (D-10-07) --
    `upload_token` finds the retained `RawTable` + resolved `MappingProposal`
    + `FieldSet` (`api.state.registry`, mirroring
    `StructuralHintResolveRequest`/`ReconcileResolveRequest`); `choices` is
    the human's per-column order answer. The real table/proposal/field set
    are server-retained under the token, never re-sent by the client
    (T-08-08, T-10-24)."""

    upload_token: str
    choices: list[DateFormatChoiceIn]


class SheetSchemaProposalOut(BaseModel):
    """One governed Schema, scored against ONE worksheet's headers, with the
    evidence that produced the score (SHEET-05, D-11-03) --
    `service.SchemaProposal`'s wire shape.

    `matched` is the whole point, and it is a LIST OF PAIRS rather than a bare
    count: "6/7 canonical fields matched" is not checkable, but "compound_id <-
    'CMP'" is. The human is being asked to check the tool's reasoning, and
    cannot check what is not shown. `uncovered` names the remainder, so "4/7" is
    never a mystery about WHICH four.

    `total_fields` counts the Schema's LIVE canonical fields only -- a
    tombstoned field is gone, not missing, and must neither inflate the
    denominator nor appear as something this sheet failed to cover (D-10-15,
    D-11-23; the filter is structural, one layer down in the store).

    `source` says WHERE the proposal came from, and the label is load-bearing:
    `profile` is a mapping a curator already confirmed for exactly these
    columns; `crosswalk` is deterministic alias coverage; `claude` is D-11-19's
    last-resort ranking, which by construction carries `matched == []` and a
    `reason` INSTEAD of evidence -- the panel renders "No crosswalk match --
    Claude suggests {schema}. Check it before ingesting." A human is entitled to
    know a proposal has nothing behind it.

    There is deliberately NO `selected`, NO `confident`, and NO `score`
    threshold field here. The scorer ranks and shows; a human disposes
    (D-11-06)."""

    schema_name: str
    matched: list[dict[str, str]]
    uncovered: list[str]
    matched_count: int
    total_fields: int
    source: Literal["profile", "crosswalk", "claude"]
    reason: str | None = None

    @classmethod
    def from_proposal(cls, proposal: SchemaProposal) -> "SheetSchemaProposalOut":
        return cls(
            schema_name=proposal.schema_name,
            matched=[
                {"field": field, "header": header} for field, header in proposal.matched.items()
            ],
            uncovered=list(proposal.uncovered),
            matched_count=len(proposal.matched),
            total_fields=proposal.total,
            source=proposal.source,
            reason=proposal.reason,
        )


class SheetLayoutOut(BaseModel):
    """The layout verdict, as the BROWSER consumes it (12-UI-SPEC Discretion 1).

    IT CARRIES NO INDEX, and that is the whole design. `SheetManifestEntry.
    layout` retains the FULL verdict server-side -- `key_value_blocks` and every
    row index included, because they are the un-pivot's only input when the
    human ticks the sheet -- but the browser needs none of them: it renders the
    kind, Claude's one-sentence `reasoning`, the confidence, how many records
    the layout yields, and the gate. Everything a curator needs to CHECK the
    verdict; nothing they could tamper with. "Server-side" means retained on the
    server and withheld from the browser, never discarded -- and the smallest
    untrusted-input surface is the one that does not exist.

    `needs_confirmation` is the SERVER's gate, computed from the verdict's own
    confidence (`SheetLayout.needs_confirmation`, 12-01) and always sent BESIDE
    the raw confidence -- never a bare number for the browser to threshold for
    itself. The client renders gates; it does not set them (the exact division
    `FieldMapping.needs_confirmation` already draws).

    `record_count` is `None` for every kind but `key_value`: a row-per-record
    table's row count is not the layout's to know (it is `row_count`, one field
    up), and inventing one here would be a claim the verdict cannot support."""

    kind: str
    confidence: float
    reasoning: str
    record_count: int | None
    needs_confirmation: bool

    @classmethod
    def from_layout(cls, layout: SheetLayout) -> "SheetLayoutOut":
        return cls(
            kind=layout.kind.value,
            confidence=layout.confidence,
            reasoning=layout.reasoning,
            record_count=layout.record_count,
            needs_confirmation=layout.needs_confirmation,
        )


class SheetOut(BaseModel):
    """One worksheet, as the sheet-selection screen must show it (SHEET-01) --
    `service.SheetManifestEntry`'s wire shape.

    HEADERS ARE NOT REDACTED UNDER `headers_only`, and that is deliberate: a
    header is not a cell value (D-10-05). `headers_only` restricts what CLAUDE
    sees, never what the server reads or what the panel may show the curator --
    and this manifest carries no cell values at all, so unlike
    `DateFormatQuestionResponse` (whose `example_values` ARE cell values) there
    is nothing here to redact and no redaction hook to add.

    `proposals` is EMPTY when no Schema fits. That absence IS the "propose skip"
    answer (D-11-06): the scorer returns no zero-scored candidate waiting to be
    mistaken for one, and the panel reads THIS -- never `proposed_schema` -- to
    decide the sheet arrives unticked.

    `proposed_schema` is only the Select's pre-fill, and `tie` is why it may be
    empty even though proposals exist: two Schemas with equal coverage are BOTH
    shown, and the tool breaks the tie for nobody.

    `status` names the structural gate this sheet passes or fails -- and is
    never a reason to hide it. A gate-failing sheet is still described, still
    scored, and still selectable; if the human insists, `parse(path, sheet=X)`
    raises that sheet's OWN question in its own member (SHEET-04: marked, never
    dropped).

    `layout` (12-05) is Claude's structural VERDICT for this sheet, and it is a
    FIELD here rather than a `status` member (12-RESEARCH Pitfall 7, binding):
    `status` keeps GATE semantics ("can this sheet be read?"), the layout kind
    travels on `layout.kind`. That is what lets a key-value sheet be
    `status: "ok"` AND `layout.kind: "key_value"` -- readable, tickable, with
    its LABELS as headers and its Schema control intact. Collapsing the two
    would rebuild the very refusal this phase exists to remove. `None` when no
    verdict exists at all -- honestly null, never a fabricated `row_per_record`
    (the one default D-12-14 forbids everywhere it appears)."""

    sheet_name: str
    row_count: int
    headers: list[str]
    column_signature: str
    status: Literal[
        "ok", "drawing_only", "unsupported_shape", "header_uncertain", "layout_unknown"
    ]
    proposals: list[SheetSchemaProposalOut]
    proposed_schema: str | None
    tie: bool
    layout: SheetLayoutOut | None = None


class SheetQuestionResponse(BaseModel):
    """The `kind="sheet_question"` 5th arm of `/api/upload`'s discriminated
    response (Pattern 5, D-11-02) -- surfaced whenever a workbook has MORE THAN
    ONE worksheet and no explicit `sheet=` was given, REGARDLESS of whether a
    Schema was chosen (D-11-16).

    That trigger is the phase's load-bearing correction. The browser ALWAYS
    sends `schema_name` (`Upload.tsx` blocks submit until one is picked), so
    firing only on "a multi-sheet workbook arriving WITHOUT a Schema" -- the
    original D-11-01 wording -- would have made SHEET-01/03/04/05 unreachable
    from the UI. A Schema picked in the dropdown is a DEFAULT PRE-SELECTION, and
    a default never suppresses the question.

    Bundles EVERY worksheet into ONE question, exactly as
    `DateFormatQuestionResponse` bundles every ambiguous column -- never one
    question per sheet. `from_manifest` holds ALL domain->wire conversion so the
    route stays a thin adapter.

    It kills two silent guesses at once. Today `_resolve_sheet` ranks the
    worksheets, takes the winner, and DISCARDS every other sheet without a word
    (meridian's LEGEND, right now); and the human must pick a Schema before
    upload, with the file unparsed and no header yet seen. Here the file is
    described first, every sheet is shown with its evidence, and the human
    confirms."""

    kind: str = "sheet_question"
    upload_token: str
    sheets: list[SheetOut]

    @classmethod
    def from_manifest(
        cls,
        manifest: tuple[SheetManifestEntry, ...],
        upload_token: str,
        *,
        default_schema: str | None,
    ) -> "SheetQuestionResponse":
        return cls(
            upload_token=upload_token,
            sheets=[_sheet_out(entry, default_schema) for entry in manifest],
        )


def _sheet_out(entry: SheetManifestEntry, default_schema: str | None) -> SheetOut:
    proposals = [SheetSchemaProposalOut.from_proposal(p) for p in entry.proposals]
    tie = _is_tie(entry.proposals)
    return SheetOut(
        sheet_name=entry.name,
        row_count=entry.row_count,
        headers=entry.headers,
        column_signature=entry.column_signature,
        status=entry.status,
        proposals=proposals,
        proposed_schema=_pre_selection(entry, tie, default_schema),
        tie=tie,
        layout=(
            SheetLayoutOut.from_layout(entry.layout) if entry.layout is not None else None
        ),
    )


def _is_tie(proposals: tuple[SchemaProposal, ...]) -> bool:
    """True when the top two proposals are INDISTINGUISHABLE to the scorer's own
    ordering -- same provenance rank, same coverage.

    Both halves matter. A learned-profile hit outranks every crosswalk match
    whatever its raw coverage (D-11-05: a human's confirmation for exactly these
    columns is stronger evidence than any number of matched spellings), so a
    profile hit scoring 4/7 above a crosswalk hit scoring 4/7 is a WINNER, not a
    tie. Two crosswalk hits at 4/7 are a genuine tie, and the tool says so."""
    if len(proposals) < 2:
        return False
    first, second = proposals[0], proposals[1]
    return (first.source == "profile") == (second.source == "profile") and first.score == second.score


def _pre_selection(
    entry: SheetManifestEntry, tie: bool, default_schema: str | None
) -> str | None:
    """Which Schema the sheet's Select arrives pre-filled with (D-11-06/16).

    The precedence, and the three refusals inside it:

      1. THE SCORER'S TOP PROPOSAL -- evidence, shown alongside it.
      2. ELSE THE SCHEMA THE HUMAN PICKED ON UPLOAD, if any. Not a guess: their
         own stated intent. It fills the Select ONLY -- the sheet is still
         proposed as skip, because an empty `proposals` list is what the tick
         state reads, and this never touches that.
      3. ELSE NOTHING.

    A TIE PRE-FILLS NOTHING, and the Upload dropdown does not get to settle it
    either: a stale default is not evidence, and letting it break a genuine tie
    would be exactly the silent guess D-11-06 exists to forbid. The human
    chooses, or the sheet is not ingested.

    A SHEET WHOSE SHAPE THE TOOL CANNOT READ PRE-FILLS NOTHING EITHER, and rung 2
    is where that had to be said. Such a sheet has no headers (`sheets.py`
    suppresses them -- it is not a table, so it has no columns) and therefore no
    coverage and no proposals, so it fell through to the default and arrived
    carrying a Schema for a sheet the tool had just proposed to SKIP. Rung 2 is a
    pre-selection, and a pre-selection needs something to select FROM; here there
    is nothing to go on at all, and nothing would map even if the human insisted.

    This is NOT the same as `header_uncertain`, which also reaches rung 2 with no
    proposals and MUST keep the default. That sheet's failure is answerable: the
    human points at the header row, it maps normally, and the Schema they chose on
    Upload is exactly the right pre-fill for it. An unreadable shape is answerable
    by nobody -- the shape, not the location, is the problem, which is what
    `table.py::_shape_unsupported_question` means by `answerable_by_hint=False`."""
    if tie:
        return None
    if entry.proposals:
        return entry.proposals[0].schema_name
    if entry.status == "unsupported_shape":
        return None
    return default_schema


class SheetSelectionIn(BaseModel):
    """One sheet the human ticked, and the Schema they chose for IT (SHEET-05).

    Different sheets may legitimately need DIFFERENT Schemas -- orion's
    `Summary` and `Raw timepoints` are not the same kind of table -- so the
    Schema rides per selection, never once per request.

    Both fields are UNTRUSTED input reaching `parse()` and the Schema store
    (T-11-22): `sheet_name` is validated against the SERVER-RETAINED manifest
    (422, never a `ValueError` surfacing as a 500) and `schema_name` through
    `SchemaStore.get_schema` (404), both BEFORE any filesystem access.

    `ask_layout` (12-05, 12-UI-SPEC Discretion 2 -- the per-sheet disagree
    path) routes THIS member to the layout StructureQuestion in its Review tab
    instead of applying the server-retained verdict: one answer surface
    (`StructuralHintPanel`), reached from both paths, never a second inline
    editor. It selects among server-side behaviours only -- the layout itself
    still comes from the SERVER-retained manifest, never from the client
    (T-12-17)."""

    sheet_name: str
    schema_name: str
    ask_layout: bool = False


class SheetResolveRequest(BaseModel):
    """`POST /api/sheets/resolve`'s request body (D-11-08) -- `upload_token`
    finds the retained temp file + sheet manifest (`api.state.registry`,
    mirroring `StructuralHintResolveRequest`/`DateFormatResolveRequest`);
    `selections` is the human's answer.

    The manifest, the workbook, and the Schema objects are all server-retained
    under the token and NEVER re-sent by the client (T-08-08) -- the client only
    ever chooses among options the server already offered it.

    An EMPTY `selections` list is a 422, not a no-op: nothing would be ingested,
    and a request that ingests nothing is a mistake worth naming rather than a
    success worth returning (fail closed)."""

    upload_token: str
    selections: list[SheetSelectionIn]


class SheetMemberOut(BaseModel):
    """One selected sheet's INDEPENDENT dataset inside a `sheet_group`.

    `response` is one of the FOUR EXISTING arms (`mapping`,
    `structural_question`, `reconcile_question`, `date_question`), serialized
    whole. The recursive shape is deliberate and is the point: it is the only
    shape honest about a member that STILL HAS A QUESTION. A sheet whose header
    is uncertain raises its own structural question inside its own member
    (SHEET-04) and the browser renders `StructuralHintPanel` verbatim inside
    that member's tab -- no new panel, no new arm, and no dropped sheet."""

    sheet_name: str
    response: dict


class SheetGroupResponse(BaseModel):
    """The `kind="sheet_group"` 6th arm -- `POST /api/sheets/resolve`'s answer:
    N selected sheets became N INDEPENDENT DATASETS (D-11-08).

    NOTHING IS MERGED, ANYWHERE. SHEET-02 is struck from the PRODUCT, not
    deferred: each member has its own Schema, its own mapping, its own amber
    gate, its own confirm and its own export, and no path in this codebase
    combines records across sheets. There is deliberately no group-level
    `ready`, no group-level confirm, and no aggregate gate here for anything
    downstream to mistake for one -- a group gate would either weaken or
    strengthen a member's amber gate, and both are wrong.

    `group_id` is a server-minted uuid4 owning N ORDINARY `upload_token`s
    (D-11-20, Option A). That is why `service.confirm`, `service.export`,
    `_is_review_ready`, the `pending_uploads` round-trip,
    `GET /api/export/{run_id}/{fmt}`, `MappingResponse` and `date_format.py` are
    all UNCHANGED by this phase: every member is an ordinary upload that happens
    to know which group it belongs to."""

    kind: str = "sheet_group"
    group_id: str
    source_name: str | None
    members: list[SheetMemberOut]
