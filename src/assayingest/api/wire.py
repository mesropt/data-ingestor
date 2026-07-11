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

from pydantic import BaseModel, Field, field_validator

from ..cli import proposal_to_dict
from ..domain.models import MappingProposal, Schema
from ..parsing.hint import StructureQuestion

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
    JSON draft and this HTTP body never drift apart (Pattern 4)."""

    kind: str = "mapping"
    ready: bool
    source_columns: list[str]
    field_mappings: list[FieldMappingOut]
    provenance: str | None
    upload_token: str

    @classmethod
    def from_proposal(
        cls, proposal: MappingProposal, provenance: str | None, upload_token: str
    ) -> "MappingResponse":
        base = proposal_to_dict(proposal, provenance)
        notes_by_field = {m.target_field: m.validator_note for m in proposal.field_mappings}
        field_mappings = [
            FieldMappingOut(**field_dict, validator_note=notes_by_field[field_dict["target_field"]])
            for field_dict in base["field_mappings"]
        ]
        return cls(
            ready=base["ready"],
            source_columns=base["source_columns"],
            field_mappings=field_mappings,
            provenance=base["provenance"],
            upload_token=upload_token,
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
