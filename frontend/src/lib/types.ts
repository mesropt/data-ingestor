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
}

/** `api/wire.py::ConfirmResponse` (Plan 06). */
export interface ConfirmResponse {
  ready: boolean;
  manifest: Record<string, unknown>;
  profile_id: string | null;
  export: Record<string, string> | null;
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
