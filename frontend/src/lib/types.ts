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

/** `api/wire.py::MappingResponse` -- the `kind: "mapping"` half of
 * `/api/upload`'s discriminated response. */
export interface MappingResponse {
  kind: "mapping";
  ready: boolean;
  source_columns: string[];
  field_mappings: FieldMappingOut[];
  provenance: string | null;
  upload_token: string;
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

/** `/api/upload`'s full discriminated response shape. */
export type UploadResponse = MappingResponse | StructuralQuestionResponse;

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
