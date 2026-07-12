/**
 * TypeScript mirrors of the backend's HTTP wire shapes
 * (`src/assayingest/api/wire.py` + `fields/models.py::Field.to_dict`/
 * `FieldSet.to_dict`). These are the browser's only notion of these
 * shapes -- `state/fieldSet.ts`'s `toFieldSetPayload()` must serialize
 * into exactly `FieldSetPayload`, byte-compatible with the server's
 * `FieldSet.to_dict()` / `fields.loader.from_dict()` (Plan 03), never a
 * second, hand-derived shape (PATTERNS.md wire<->domain discipline).
 */

/** Mirrors `fields/models.py::FIELD_TYPES`. */
export type FieldType = "number" | "integer" | "date" | "text";

/** Mirrors `fields/models.py::Field.to_dict()`. */
export interface FieldPayload {
  name: string;
  description: string | null;
  type: FieldType | null;
  allowed_values: string[] | null;
  unit: string | null;
  required: boolean;
  min: number | null;
  max: number | null;
  date_format: string | null;
}

/** Mirrors `fields/models.py::FieldSet.to_dict()` -- the shape
 * `POST /api/field-sets`'s `field_set` body key and `GET
 * /api/field-sets/{id}`'s response both use. */
export interface FieldSetPayload {
  name: string | null;
  fields: FieldPayload[];
}

/** One saved template, as `GET /api/field-sets` returns it
 * (`api/wire.py::FieldSetOut`). */
export interface FieldSetTemplate {
  id: string;
  name: string;
  field_set: FieldSetPayload;
}

/** `api/wire.py::AlternativeOut` -- one ranked-alternative column (D-02 chip UI). */
export interface AlternativeOut {
  source_column: string;
  confidence: number;
}

/** `api/wire.py::FieldMappingOut` -- one target field's resolution. */
export interface FieldMappingOut {
  target_field: string;
  source_column: string | null;
  confidence: number;
  reasoning: string;
  needs_confirmation: boolean;
  inferred_value: string | null;
  alternatives: AlternativeOut[];
  validator_note: string | null;
}

/** Mirrors `service.Escalation` as `wire.MappingResponse.escalation` puts it
 * on the wire (D-10-03/INGEST-02) -- how many of the target Schema's fields
 * the Python crosswalk pre-fill matched deterministically vs how many
 * needed a Claude call. The one visible proof of the Python-before-Claude
 * mapping order. */
export interface Escalation {
  python: number;
  claude: number;
  total: number;
}

/** `api/wire.py::MappingResponse` -- the `kind: "mapping"` half of
 * `/api/upload`'s discriminated response. `escalation` is `null` whenever no
 * Schema was targeted or the profile auto-apply already short-circuited
 * everything (`MappingResponse.escalation`'s own docstring) -- never a
 * misleading all-zero count on those paths.
 *
 * `remembered_vendor`/`remembered_vendor_source`/`vendor_candidates`
 * (10-09/INGEST-02) mirror `escalation`'s own additive-optional precedent:
 * `null`/`null`/`[]` on the legacy `field_set`/CLI path. `vendor_candidates`
 * is only ever non-empty in the genuinely-ambiguous case (two or more
 * vendors' aliases match the file's columns) -- `remembered_vendor` stays
 * `null` there too, since the tool never guesses which one. */
export interface MappingResponse {
  kind: "mapping";
  ready: boolean;
  source_columns: string[];
  field_mappings: FieldMappingOut[];
  provenance: string | null;
  upload_token: string;
  escalation: Escalation | null;
  remembered_vendor: string | null;
  remembered_vendor_source: string | null;
  vendor_candidates: string[];
  /** The uploaded file's original filename (quick 260712) -- what Review's
   * subheading shows instead of the raw upload token, which means nothing
   * to a curator. Optional so older fixtures/responses parse unchanged;
   * the server sends it on every mapping arm. */
  source_name?: string | null;
}

/** `api/wire.py::StructuralQuestionResponse` -- the
 * `kind: "structural_question"` half of `/api/upload`'s discriminated
 * response (D-04). */
export interface StructuralQuestionResponse {
  kind: "structural_question";
  unsure_about: string;
  reason: string;
  confidence: number;
  proposal: Record<string, unknown> | null;
  alternatives: Record<string, unknown>[];
  evidence_rows: string[][];
  answerable_by_hint: boolean;
  upload_token: string;
}

/** Mirrors `domain/models.py::ReconcileConflict.to_dict()` (Phase 08) -- one
 * alias-target disagreement between an uploaded map file and the master
 * crosswalk: the master already resolves `(vendor, source_column)` to
 * `master_field`, while the map file asserts the SAME pair resolves to
 * `map_file_field`. Identity is the exact `(vendor, source_column)` pair
 * (D-08-04, no fuzzy matching in v1). All four values are untrusted crosswalk
 * text -- rendered escape-by-default in the ReconcilePanel (T-08-11). */
export interface ReconcileConflict {
  vendor: string;
  source_column: string;
  master_field: string;
  map_file_field: string;
}

/** `api/wire.py::ReconcileQuestionResponse` -- the `kind: "reconcile_question"`
 * third arm of `/api/upload`'s discriminated response (D-08-03), surfaced when
 * an uploaded map file disagrees with the master crosswalk. Reuses
 * `ReconcileQuestion.to_dict()`'s `conflicts` shape verbatim; `schema_name`/
 * `vendor` are the server-retained values the resolve step needs. Nothing is
 * augmented or mapped until the human resolves (P1). */
export interface ReconcileQuestionResponse {
  kind: "reconcile_question";
  upload_token: string;
  schema_name: string;
  vendor: string;
  conflicts: ReconcileConflict[];
}

/** Mirrors `api/wire.py::ReconcileChoiceIn::decision` -- `keep_master` keeps
 * the master's stored canonical field for a `(vendor, source_column)` pair,
 * `take_map_file` takes the map file's asserted field for this run. */
export type ReconcileDecision = "keep_master" | "take_map_file";

/** `api/wire.py::ReconcileChoiceIn` -- one human resolution of one conflict in
 * a `POST /api/reconcile/resolve` body. The choice only PICKS a per-conflict
 * side; the real map envelope/schema/vendor are server-retained under the
 * upload token, never re-sent by the client (T-08-08). */
export interface ReconcileChoice {
  vendor: string;
  source_column: string;
  decision: ReconcileDecision;
}

/** Mirrors `date_order.py`'s day_first/month_first order (D-10-07). Carries
 * NO strptime format string at all -- the client structurally cannot send
 * one (T-10-31); the server derives the concrete format itself. */
export type DateFormatOrder = "day_first" | "month_first";

/** `api/wire.py::DateFormatColumnOut` -- one date-typed mapped column Python
 * could not resolve the order of on its own. `example_values` is `[]` under
 * `headers_only` (server-side redaction, Plan 05's `from_question`) --
 * this type carries whatever the wire actually sent, never assumes
 * non-empty. */
export interface DateFormatColumn {
  target_field: string;
  source_column: string;
  day_first_format: string;
  month_first_format: string;
  example_values: string[];
  ambiguous_row_count: number;
}

/** `api/wire.py::DateFormatQuestionResponse` -- the 4th `kind:"date_question"`
 * arm of `/api/upload`'s discriminated response (D-10-07). Bundles EVERY
 * ambiguous column from one upload into ONE question -- never one question
 * per column. */
export interface DateFormatQuestionResponse {
  kind: "date_question";
  upload_token: string;
  columns: DateFormatColumn[];
}

/** `api/wire.py::DateFormatChoiceIn` -- one human resolution of one column
 * in a `POST /api/date-format/resolve` body. Carries NO `date_format` field
 * at all, by design (T-10-21/T-10-31): the server re-classifies the
 * retained column and derives the concrete strptime format itself. */
export interface DateFormatChoice {
  target_field: string;
  order: DateFormatOrder;
}

/** `/api/upload`'s full discriminated response shape -- `/api/structural-hint/
 * resolve`, `/api/reconcile/resolve`, and `/api/date-format/resolve` return
 * the SAME union, since a re-submitted answer can itself still be ambiguous
 * (Pattern 5). Adding `DateFormatQuestionResponse` here is what breaks
 * `Upload.tsx`'s `assertNever(response)` at compile time until Task 2 adds
 * the real case branch -- the safety net working as designed (10-RESEARCH
 * Pitfall 5), never routed around by widening a `default`. */
export type UploadResponse =
  | MappingResponse
  | StructuralQuestionResponse
  | ReconcileQuestionResponse
  | DateFormatQuestionResponse;

/** `api/wire.py::ConfirmFieldMappingIn` -- one edited field mapping in a
 * `POST /api/confirm` body (Plan 06). */
export interface ConfirmFieldMappingIn {
  target_field: string;
  source_column: string | null;
  confidence: number;
  reasoning: string;
  needs_confirmation: boolean;
  inferred_value?: string | null;
  alternatives?: AlternativeOut[];
}

/** `api/wire.py::ConfirmRequest` (Plan 06). */
export interface ConfirmRequest {
  upload_token: string;
  field_set: FieldSetPayload;
  field_mappings: ConfirmFieldMappingIn[];
  save_profile?: boolean;
  export?: boolean;
  provenance?: string;
  /** Additive Phase 07 crosswalk fields (mirror `api/wire.py::ConfirmRequest`
   * `schema_name`/`vendor`, both default `None`) -- present only when a target
   * Schema + vendor are selected; when omitted the payload is byte-identical
   * to Plan 06's and nothing is accreted (ALIAS-04). */
  schema_name?: string;
  vendor?: string;
}

/** Mirrors `domain/models.py::Alias.to_dict()` (Phase 07) -- one vendor's
 * raw column name for a canonical field, with immutable provenance
 * (`provenance_kind` is "manual" | "from_map_file"). `confidence`/`note`
 * appear only when set, matching the server's conditional serialization. */
export interface AliasPayload {
  vendor: string;
  source_column: string;
  provenance_kind: string;
  provenance_actor: string;
  created_at: string;
  confidence?: number;
  note?: string;
}

/** Mirrors `domain/models.py::CanonicalField.to_dict()` -- a `FieldPayload`
 * with an embedded `aliases` list (the per-field shape inside a Schema's
 * master-map envelope and `SchemaOut.fields`). */
export type CanonicalFieldPayload = FieldPayload & {
  aliases: AliasPayload[];
};

/** `api/wire.py::SchemaFieldIn` (Plan 10-04) -- the body of
 * `POST /api/schemas/{name}/fields` and `PATCH .../fields/{field_name}`
 * (Plan 10-06). Wraps a raw `FieldPayload` dict; the server routes it through
 * the SAME `fields.loader.from_dict` guard a CLI-loaded or promoted field
 * gets, never a second, weaker route-layer check. */
export interface SchemaFieldIn {
  field: FieldPayload;
}

/** `api/wire.py::SchemaAliasIn` (Plan 10-04) -- the body of
 * `POST /api/schemas/{name}/fields/{field_name}/aliases` (Plan 10-06). Carries
 * no actor field, by design (T-07-06) -- the server resolves the acting user
 * from the session, never a client-supplied value. */
export interface SchemaAliasIn {
  vendor: string;
  source_column: string;
}

/** Mirrors `api/wire.py::SchemaOut` (Plan 07-02) -- one governed Schema as
 * the browser's selector + import controls consume it: `id`, `name`,
 * server-resolved `created_by`, and the canonical `fields` each with their
 * embedded aliases (the `CanonicalField.to_dict()` shape). */
export interface SchemaOut {
  id: string;
  name: string;
  created_by: string | null;
  fields: CanonicalFieldPayload[];
}

/** The lighter view the schema selector reducer holds (`state/schema.ts`):
 * `GET /api/schemas` returns full `SchemaOut[]`, which is structurally a
 * `SchemaSummary[]`. The selector only needs identity to render + select. */
export interface SchemaSummary {
  id: string;
  name: string;
  created_by: string | null;
}

/** Mirrors `domain/models.py::Schema.to_master_map()` -- the versioned JSON
 * envelope that IS the downloadable master-map file (SCHEMA-02/03). The
 * browser reads a chosen file into this shape before POSTing it back; the
 * server re-validates every field name + augment semantic (never trusts the
 * client parse, T-07-15). */
export interface MasterMapEnvelope {
  schema_version: number;
  id: string;
  name: string;
  created_by: string | null;
  created_at: string;
  fields: CanonicalFieldPayload[];
}

/** The client-side view of one `NotReadyError.unclear_fields` entry, as
 * `/api/confirm`'s 422 `detail.unclear_details` (added alongside the
 * unchanged `unclear_fields` name list, see `api/routes/confirm.py`)
 * carries it. `reason` is the no-LLM validator's own `validator_note`,
 * `null` when the validator recorded none. Read defensively at the
 * boundary in `api.ts` -- this interface documents the trusted SHAPE
 * once parsing has already dropped anything malformed. */
export interface UnclearDetail {
  field: string;
  reason: string | null;
  sourceColumn: string | null;
}

/** `api/wire.py::ConfirmResponse` (Plan 06). */
export interface ConfirmResponse {
  ready: boolean;
  manifest: Record<string, unknown>;
  profile_id: string | null;
  export: Record<string, string> | null;
}

/** Mirrors `api/wire.py::UserOut` (Plan 06-02) -- the server's public view
 * of a user; `password_hash` is never exposed. `auth_provider` is
 * "password" or "google". */
export interface AuthUser {
  id: string;
  email: string;
  is_verified: boolean;
  auth_provider: string;
}

/** Mirrors `api/wire.py::AuthConfigOut` -- whether the flag-gated Google
 * OAuth surface is live (off by default; the "Continue with Google" button
 * renders only when true). */
export interface AuthConfig {
  google_oauth_enabled: boolean;
}

/** `POST /api/auth/signup` body (mirrors `api/wire.py::SignUpIn`). */
export interface SignUpBody {
  email: string;
  password: string;
}

/** `POST /api/auth/login` body (mirrors `api/wire.py::SignInIn`). */
export interface SignInBody {
  email: string;
  password: string;
}

/** `GET /api/auth/verify` response -- `verified` on success, `expired` on
 * any invalid/expired/tampered token (the SPA branches on this). */
export interface VerifyResult {
  status: "verified" | "expired";
}

/** `POST /api/auth/signup` 201 response (mirrors
 * `api/wire.py::SignUpAcceptedOut`) -- the "check your server console"
 * message; the dev build logs the verification link rather than emailing. */
export interface SignUpAccepted {
  message: string;
}

/** `api/wire.py::StructuralHintIn` (Plan 05). */
export interface StructuralHintIn {
  sheet_name?: string | null;
  header_row_index?: number | null;
  delimiter?: string | null;
  decimal_separator?: string | null;
  data_region?: string | null;
  table_shape?: string | null;
}
