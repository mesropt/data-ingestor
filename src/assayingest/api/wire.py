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

from pydantic import BaseModel, Field, field_validator

from ..cli import proposal_to_dict
from ..domain.models import DateFormatQuestion, MappingProposal, ReconcileQuestion, Schema
from ..parsing.hint import StructureQuestion
from ..service import Escalation, VendorMemory

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

    @classmethod
    def from_proposal(
        cls,
        proposal: MappingProposal,
        provenance: str | None,
        upload_token: str,
        *,
        escalation: Escalation | None = None,
        vendor_memory: VendorMemory | None = None,
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


class StructuralHintIn(BaseModel):
    """`StructuralHint`'s wire shape (UI-02, D-04) -- every field optional,
    mirroring the domain dataclass exactly so the inline hint form can send
    only the one dimension in question."""

    sheet_name: str | None = None
    header_row_index: int | None = None
    delimiter: str | None = None
    decimal_separator: str | None = None
    data_region: str | None = None
    table_shape: str | None = None


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
