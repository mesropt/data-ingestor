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
  /** The sheet row index `evidence_rows[0]` actually is. A header buried under
   * a cover block means the evidence starts partway down the sheet, and both the
   * row numbers shown and the row a click submits are offset by this. */
  evidence_first_row: number;
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

/** `api/wire.py::SheetSchemaProposalOut` -- one governed Schema scored
 * against ONE worksheet's headers, with the evidence that produced the score
 * (SHEET-05, D-11-03). `matched` is a list of pairs, not a bare count:
 * "6/7 canonical fields matched" is not checkable, but "compound_id <- 'CMP'"
 * is. `source: "claude"` (D-11-19's last-resort ranking) carries
 * `matched: []` and a `reason` INSTEAD of evidence -- the panel must label
 * it as such, because a human is entitled to know a proposal has nothing
 * behind it. There is deliberately NO score/confidence/threshold field
 * (D-11-06).
 *
 * `near_matches` are headers that MISSPELL a spelling the crosswalk knows
 * (`Tset` for `Test`). They are questions, not answers: never in `matched`,
 * never in `matched_count`, never applied without the curator confirming them.
 * `resembles` is the known spelling — the evidence the human checks against. */
export interface SheetSchemaProposal {
  schema_name: string;
  matched: { field: string; header: string }[];
  uncovered: string[];
  matched_count: number;
  total_fields: number;
  source: "profile" | "crosswalk" | "claude";
  reason: string | null;
  near_matches: { header: string; field: string; resembles: string }[];
}

/** Mirrors `parsing/structure/layout.py::LayoutKind` as `api/wire.py`'s
 * Literals spell it -- the parse gate's vocabulary (SHAPE-03, D-12-13). */
export type LayoutKind =
  | "row_per_record"
  | "key_value"
  | "wide_matrix"
  | "multiple_tables"
  | "not_a_table"
  | "unknown";

/** `api/wire.py::SheetLayoutOut` -- Claude's layout verdict as the BROWSER
 * consumes it (12-UI-SPEC Discretion §1). IT CARRIES NO INDEX, by design:
 * the server retains `key_value_blocks` and every row index on its own
 * manifest (they are the un-pivot's only input), and the browser needs
 * none of them -- everything a curator needs to CHECK the verdict, nothing
 * they could tamper with. `needs_confirmation` is the SERVER's gate,
 * always sent beside the raw confidence -- the client renders it, never
 * thresholds `confidence` itself (the exact division
 * `FieldMappingOut.needs_confirmation` already draws). `record_count` is
 * `null` for every kind but `key_value`. */
export interface SheetLayoutOut {
  kind: LayoutKind;
  confidence: number;
  reasoning: string;
  record_count: number | null;
  needs_confirmation: boolean;
}

/** `api/wire.py::SheetOut` -- one worksheet as the sheet-selection panel
 * must show it (SHEET-01). Headers are NOT redacted under `headers_only`
 * (a header is not a cell value, D-10-05). `proposals: []` IS the
 * propose-skip signal (D-11-06) -- the tick state reads THIS, never
 * `proposed_schema`, which is only the Select's pre-fill. `status` names
 * the structural gate the sheet passes or fails and is never a reason to
 * hide it: a gate-failing sheet is still described, still scored, and
 * still selectable (SHEET-04: marked, never dropped).
 *
 * `layout` (12-05) is Claude's structural VERDICT, a FIELD here rather
 * than a `status` member (12-RESEARCH Pitfall 7, binding): `status` keeps
 * GATE semantics, the layout kind travels on `layout.kind`. That is what
 * lets a key-value sheet be `status: "ok"` AND `layout.kind: "key_value"`
 * -- readable, tickable, its LABELS as headers. `null` when no verdict
 * exists at all -- honestly null, never a fabricated `row_per_record`. */
export interface SheetOut {
  sheet_name: string;
  row_count: number;
  headers: string[];
  column_signature: string;
  status: "ok" | "drawing_only" | "unsupported_shape" | "header_uncertain" | "layout_unknown";
  proposals: SheetSchemaProposal[];
  /** Which table of this sheet this entry is, when the sheet stacks several
   * (each panel of a lab report brings its own header row). `null` on an
   * ordinary one-table sheet. */
  table_index: number | null;
  /** How to find that table in the sheet: "rows 11-17". */
  table_label: string | null;
  /** What the table is CALLED — the sheet's own section heading above it
   * (`Electrloytes`, `Renal Function`). Read from the file, so it carries the
   * vendor's spelling; `null` when the table has no heading. */
  table_title: string | null;
  proposed_schema: string | null;
  tie: boolean;
  layout: SheetLayoutOut | null;
}

/** `api/wire.py::SheetQuestionResponse` -- the 5th `kind:"sheet_question"`
 * arm of `/api/upload`'s discriminated response (D-11-02), surfaced
 * whenever a workbook has more than one worksheet and no explicit `sheet=`
 * was given, REGARDLESS of whether a Schema was chosen (D-11-16). Bundles
 * EVERY worksheet into ONE question, exactly as `DateFormatQuestionResponse`
 * bundles every ambiguous column. */
export interface SheetQuestionResponse {
  kind: "sheet_question";
  upload_token: string;
  sheets: SheetOut[];
}

/** `api/wire.py::SchemaDraftFieldOut` -- one field of a DRAFTED Schema: the
 * file's own column header, the proposed field name, the proposed type and
 * requiredness, and the reason the type was proposed. Every one of these is a
 * pre-filled control in the draft form, never a decision: `reason` is what
 * lets a curator disagree with a type rather than merely accept it. */
export interface SchemaDraftField {
  source_header: string;
  name: string;
  type: FieldType;
  required: boolean;
  reason: string;
}

/** `api/wire.py::SchemaDraftResponse` -- a Schema that does NOT exist yet.
 * Nothing was created by the request that returned it; it becomes a Schema
 * only when the human posts it (edited or not) to `POST /api/schemas`. */
export interface SchemaDraftResponse {
  name: string;
  fields: SchemaDraftField[];
}

/** `api/wire.py::SheetSelectionIn` -- one sheet the human ticked, and the
 * Schema they chose for IT (SHEET-05: different sheets may legitimately
 * need different Schemas, so the Schema rides per selection). Both values
 * are validated server-side against the retained manifest / Schema store
 * (T-11-22) -- the client only ever chooses among options the server
 * already offered.
 *
 * `ask_layout` (12-05, 12-UI-SPEC Discretion §2) is the per-sheet disagree
 * flag: it routes THIS member to the layout question in its Review tab
 * instead of applying the server-retained verdict. It selects among
 * server-side behaviours only -- the layout itself still comes from the
 * SERVER-retained manifest, never from the client (T-12-17). Omitted
 * (never sent as `false`) when the human did not disagree, so the payload
 * stays byte-identical to Phase 11's. */
export interface SheetSelection {
  sheet_name: string;
  schema_name: string;
  /** Which table of that sheet, when the sheet stacks several. Omitted for an
   * ordinary one-table sheet, so a single-table payload is unchanged. */
  table_index?: number;
  ask_layout?: boolean;
}

/** `api/wire.py::SheetResolveRequest` -- `POST /api/sheets/resolve`'s body.
 * The manifest, the workbook, and the Schema objects are all server-retained
 * under the token, never re-sent by the client (T-08-08). An empty
 * `selections` list is a server-side 422 (fail closed); the panel's own
 * submit gating mirrors that refusal client-side. */
export interface SheetResolveRequest {
  upload_token: string;
  selections: SheetSelection[];
}

/** One member's arm inside a `sheet_group` -- `UploadResponse` minus the
 * two group kinds (the recursive arm, `api/wire.py::SheetMemberOut`'s
 * docstring): a member that still has a question reuses its EXISTING
 * panel verbatim, and a group can never nest inside a group. */
export type SheetMemberResponse = Exclude<UploadResponse, SheetQuestionResponse | SheetGroupResponse>;

/** `api/wire.py::SheetMemberOut` -- one selected sheet's INDEPENDENT
 * dataset inside a `sheet_group`. */
export interface SheetMember {
  sheet_name: string;
  /** The Schema THIS dataset was resolved against, straight from the server.
   * The browser used to look this up in a sheet-name -> Schema map of its own;
   * once one sheet could yield four datasets, the member's name stopped being
   * the sheet's name and every lookup missed. One copy of the truth, server-side. */
  schema_name: string;
  response: SheetMemberResponse;
}

/** `api/wire.py::SheetGroupResponse` -- the 6th `kind:"sheet_group"` arm:
 * N selected sheets became N INDEPENDENT datasets (D-11-08). Nothing is
 * merged, anywhere; there is deliberately no group-level `ready`, no
 * group-level confirm, and no aggregate gate (a group gate would either
 * weaken or strengthen a member's amber gate, and both are wrong). */
export interface SheetGroupResponse {
  kind: "sheet_group";
  group_id: string;
  source_name: string | null;
  members: SheetMember[];
}

/** `/api/upload`'s full discriminated response shape -- `/api/structural-hint/
 * resolve`, `/api/reconcile/resolve`, and `/api/date-format/resolve` return
 * the SAME union, since a re-submitted answer can itself still be ambiguous
 * (Pattern 5). Adding `DateFormatQuestionResponse` here is what breaks
 * `Upload.tsx`'s `assertNever(response)` at compile time until Task 2 adds
 * the real case branch -- the safety net working as designed (10-RESEARCH
 * Pitfall 5), never routed around by widening a `default`. Phase 11 adds
 * the `sheet_question` / `sheet_group` pair (D-11-02) through exactly the
 * same compile-time gate. */
export type UploadResponse =
  | MappingResponse
  | StructuralQuestionResponse
  | ReconcileQuestionResponse
  | DateFormatQuestionResponse
  | SheetQuestionResponse
  | SheetGroupResponse;

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

/** `api/wire.py::KeyValueBlockIn` (12-05) -- one label/value block of the
 * human's CONFIRMED key-value answer. Selecting "Labels down the side"
 * submits confirmation of CLAUDE'S blocks, never indices the browser
 * invented -- the row-click on the evidence grid still sets only
 * `header_row_index`. Every index is re-validated server-side (ge=0 at the
 * wire, grid bounds at the route -- T-12-15, ASVS V5). */
export interface KeyValueBlockIn {
  label_column: number;
  value_columns: number[];
  first_row: number;
  last_row: number;
}

/** `api/wire.py::SheetLayoutIn` (12-05) -- the human's CONFIRMED layout
 * answer, indices INCLUDED, because a confirmed key-value answer must
 * carry the blocks Python un-pivots from (they are the transform's ONLY
 * input). This is what finally supersedes the write-only `table_shape`
 * (D-12-15). */
export interface SheetLayoutIn {
  kind: LayoutKind;
  confidence: number;
  reasoning?: string;
  header_row_index?: number | null;
  first_data_row?: number | null;
  last_data_row?: number | null;
  key_value_blocks?: KeyValueBlockIn[];
  one_record_per_value_column?: boolean;
}

/** `api/wire.py::StructuralHintIn` (Plan 05; `layout` added by 12-05).
 * `table_shape` stays only because saved learning profiles already
 * serialise it -- new code writes `layout`. */
export interface StructuralHintIn {
  sheet_name?: string | null;
  header_row_index?: number | null;
  delimiter?: string | null;
  decimal_separator?: string | null;
  data_region?: string | null;
  table_shape?: string | null;
  layout?: SheetLayoutIn | null;
}
