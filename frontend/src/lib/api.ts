/**
 * Fetch wrappers for the FastAPI backend (`src/assayingest/api/routes/*`).
 * Every function here calls a real endpoint through `fetch`, decodes the
 * JSON body, and raises a typed `ApiError` on any non-2xx response so a
 * caller (DefineFields.tsx, Plans 05/06's Upload/Review screens) can
 * branch on `error.status` without re-parsing a generic `Error.message`
 * string.
 */

import type {
  AuthConfig,
  AuthUser,
  ConfirmRequest,
  ConfirmResponse,
  FieldPayload,
  FieldSetPayload,
  FieldSetTemplate,
  MasterMapEnvelope,
  ReconcileChoice,
  SchemaAliasIn,
  SchemaFieldIn,
  SchemaOut,
  SignInBody,
  SignUpAccepted,
  SignUpBody,
  StructuralHintIn,
  UploadResponse,
  VerifyResult,
} from "./types";

/** A non-2xx HTTP response, carrying the server's decoded body (usually
 * FastAPI's `{"detail": ...}` shape) as `detail` -- the caller renders the
 * server's own consequence-first message (UI-SPEC Copywriting Contract)
 * rather than inventing a second one. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Decodes a `fetch` `Response` and raises `ApiError` on any non-2xx status
 * -- shared by both `request` (JSON bodies) and `uploadFile` (a multipart
 * `FormData` body, which must never carry a hand-set `Content-Type`; the
 * browser derives the multipart boundary itself). */
async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : body;
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    // Send the HttpOnly `di_session` cookie on every request so the session
    // round-trips under the dev cross-origin path (ASSAYINGEST_DEV_CORS) --
    // harmless under the Vite proxy, required otherwise (06-RESEARCH Pitfall 5).
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  return parseResponse<T>(response);
}

/** `POST /api/field-sets` (UI-01, D-03) -- `name` is the saved template's
 * name, `fieldSet` is `toFieldSetPayload(state)`'s `{name, fields}` shape
 * (byte-compatible with `fields.loader.from_dict`). Returns the new
 * template's id. */
export function saveFieldSet(name: string, fieldSet: FieldSetPayload): Promise<{ id: string }> {
  return request<{ id: string }>("/api/field-sets", {
    method: "POST",
    body: JSON.stringify({ name, field_set: fieldSet }),
  });
}

/** `GET /api/field-sets` -- every saved template, for the FieldSetToolbar's
 * load-template dropdown. */
export function listFieldSets(): Promise<FieldSetTemplate[]> {
  return request<FieldSetTemplate[]>("/api/field-sets", { method: "GET" });
}

/** `GET /api/field-sets/{id}` -- one template's `FieldSet.to_dict()` body,
 * to reload into the editor. */
export function getFieldSet(templateId: string): Promise<FieldSetPayload> {
  return request<FieldSetPayload>(`/api/field-sets/${encodeURIComponent(templateId)}`, {
    method: "GET",
  });
}

/** `POST /api/schemas` (D-07-03, SCHEMA-01) -- promote a field set into a
 * named governed Schema. `name` is the Schema's domain identity, `fieldSet`
 * is `toFieldSetPayload(state)`'s `{name, fields}` shape (the same body key
 * `saveFieldSet` uses, byte-compatible with `fields.loader.from_dict`). The
 * `created_by` actor is the server-resolved session email, never sent here
 * (T-07-06). Gated server-side by `require_verified_user`; the session cookie
 * rides `request()`'s `credentials:"include"`. Returns the new `SchemaOut`. */
export function promoteSchema(name: string, fieldSet: FieldSetPayload): Promise<SchemaOut> {
  return request<SchemaOut>("/api/schemas", {
    method: "POST",
    body: JSON.stringify({ name, field_set: fieldSet }),
  });
}

/** `GET /api/schemas` -- every governed Schema, for the Schema selector. */
export function listSchemas(): Promise<SchemaOut[]> {
  return request<SchemaOut[]>("/api/schemas", { method: "GET" });
}

/** `POST /api/schemas/{name}/master-map` (D-07-04, SCHEMA-03) -- augment the
 * target Schema with a client-chosen master-map file's canonical fields +
 * aliases. The browser only parses the JSON for convenience; the server
 * re-validates every field name and enforces augment-only semantics -- a
 * malformed/hostile file cannot bypass the server guard (T-07-15). Gated by
 * `require_verified_user`. Returns the augmented `SchemaOut`. */
export function importMasterMap(name: string, envelope: MasterMapEnvelope): Promise<SchemaOut> {
  return request<SchemaOut>(`/api/schemas/${encodeURIComponent(name)}/master-map`, {
    method: "POST",
    body: JSON.stringify(envelope),
  });
}

/** `GET /api/schemas/{name}/master-map` (D-09-02, REG-01/02) -- the versioned
 * `MasterMapEnvelope` (canonical fields + each field's aliases with provenance)
 * the Mapping Registry renders. A deliberately public read per D-09-05 (only
 * mutations are gated), so no auth branch; the session cookie still rides
 * `request()`'s `credentials:"include"` harmlessly. */
export function getMasterMap(name: string): Promise<MasterMapEnvelope> {
  return request<MasterMapEnvelope>(`/api/schemas/${encodeURIComponent(name)}/master-map`, {
    method: "GET",
  });
}

/** The `GET /api/schemas/{name}/master-map` path for a plain `<a download>`
 * (SCHEMA-02) -- mirrors `ExportBar`'s "the server already knows the URL, no
 * client-side file construction" pattern. The session cookie rides the
 * browser's own navigation, same as the export links. */
export function masterMapDownloadUrl(name: string): string {
  return `/api/schemas/${encodeURIComponent(name)}/master-map`;
}

/** `POST /api/schemas/{name}/fields` (D-10-12, Plan 10-06) -- adds a brand-new
 * canonical field to a governed Schema. `field` is a `FieldPayload` (the same
 * byte-compatible shape `fields.loader.from_dict` accepts). Gated by
 * `require_verified_user`; returns the Schema's full authoritative
 * post-edit `SchemaOut`, which the screen re-renders from rather than
 * patching a local copy. */
export function addSchemaField(name: string, field: FieldPayload): Promise<SchemaOut> {
  return request<SchemaOut>(`/api/schemas/${encodeURIComponent(name)}/fields`, {
    method: "POST",
    body: JSON.stringify({ field } satisfies SchemaFieldIn),
  });
}

/** `PATCH /api/schemas/{name}/fields/{field_name}` (D-10-12, Plan 10-06) --
 * edits an existing canonical field's constraints (the field's own `name` in
 * `field` may differ from `fieldName`, the rename affordance). Gated by
 * `require_verified_user`; returns the authoritative post-edit `SchemaOut`. */
export function updateSchemaField(name: string, fieldName: string, field: FieldPayload): Promise<SchemaOut> {
  return request<SchemaOut>(
    `/api/schemas/${encodeURIComponent(name)}/fields/${encodeURIComponent(fieldName)}`,
    { method: "PATCH", body: JSON.stringify({ field } satisfies SchemaFieldIn) }
  );
}

/** `DELETE /api/schemas/{name}/fields/{field_name}` (D-10-12/D-10-15, Plan
 * 10-06) -- tombstones a canonical field (soft delete, cascading a tombstone
 * to its own aliases server-side); the row never physically disappears from
 * the store, only from every live read path. Gated by `require_verified_user`;
 * returns the authoritative post-edit `SchemaOut`. */
export function deleteSchemaField(name: string, fieldName: string): Promise<SchemaOut> {
  return request<SchemaOut>(
    `/api/schemas/${encodeURIComponent(name)}/fields/${encodeURIComponent(fieldName)}`,
    { method: "DELETE" }
  );
}

/** `POST /api/schemas/{name}/fields/{field_name}/aliases` (D-10-12, Plan
 * 10-06) -- records a manual vendor alias; `provenance_kind: "manual"` and the
 * acting user are resolved server-side from the session, never sent in
 * `alias` (T-07-06). Gated by `require_verified_user`; returns the
 * authoritative post-edit `SchemaOut`. */
export function addSchemaAlias(name: string, fieldName: string, alias: SchemaAliasIn): Promise<SchemaOut> {
  return request<SchemaOut>(
    `/api/schemas/${encodeURIComponent(name)}/fields/${encodeURIComponent(fieldName)}/aliases`,
    { method: "POST", body: JSON.stringify(alias) }
  );
}

/** `DELETE /api/schemas/{name}/fields/{field_name}/aliases?vendor=&source_column=`
 * (D-10-12/D-10-15, Plan 10-06) -- tombstones one vendor alias, identified by
 * the exact `(vendor, source_column)` pair (D-08-04, no fuzzy matching). Both
 * query values are untrusted crosswalk text, `encodeURIComponent`-ed
 * individually (T-10-28). Gated by `require_verified_user`; returns the
 * authoritative post-edit `SchemaOut`. */
export function deleteSchemaAlias(
  name: string,
  fieldName: string,
  vendor: string,
  sourceColumn: string
): Promise<SchemaOut> {
  const query = `vendor=${encodeURIComponent(vendor)}&source_column=${encodeURIComponent(sourceColumn)}`;
  return request<SchemaOut>(
    `/api/schemas/${encodeURIComponent(name)}/fields/${encodeURIComponent(fieldName)}/aliases?${query}`,
    { method: "DELETE" }
  );
}

/**
 * `POST /api/upload` (API-01/03, UI-02) -- multipart: the file, the
 * `FieldSet.to_dict()` JSON body under `field_set` (byte-compatible with
 * `fields.loader.from_dict`, matching `api/routes/upload.py::upload`'s
 * `Form(...)` params exactly), the P2 `headers_only` toggle, and an
 * optional `sheet` name. Returns the discriminated `UploadResponse`
 * (`kind: "mapping" | "structural_question"`). Never sets `Content-Type`
 * itself -- `FormData` needs the browser to generate the multipart
 * boundary, which a hand-set header would break.
 */
export async function uploadFile(
  file: File,
  fieldSet: FieldSetPayload,
  headersOnly: boolean,
  sheet?: string,
  options?: { mapFile?: File; schemaName?: string; vendor?: string }
): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  body.append("field_set", JSON.stringify(fieldSet));
  body.append("headers_only", headersOnly ? "true" : "false");
  if (sheet !== undefined) {
    body.append("sheet", sheet);
  }
  // Phase 08 reconcile ingress (D-08-01): the optional map file + its
  // schema/vendor are appended ONLY when a map file is attached, so a plain
  // upload's multipart body stays byte-identical to Plan 05's (regression
  // guard). The augmenting path is server-gated on a verified user (T-08-06).
  if (options?.mapFile) {
    body.append("map_file", options.mapFile);
    body.append("schema_name", options.schemaName ?? "");
    body.append("vendor", options.vendor ?? "");
  }

  const response = await fetch("/api/upload", { method: "POST", body, credentials: "include" });
  return parseResponse<UploadResponse>(response);
}

/**
 * `POST /api/reconcile/resolve` (RECON-02, D-08-03) -- applies the human's
 * per-conflict keep-master / take-map-file `choices` to the retained upload
 * (found server-side by `upload_token`), then augments + maps. Returns the SAME
 * discriminated `UploadResponse` `uploadFile` does, since a resolution can
 * itself still surface a follow-up state defensively (mirrors `resolveHint`).
 * The choices only PICK a side; the real map envelope/schema/vendor stay
 * server-retained under the token, never re-sent (T-08-08). Server-gated on a
 * verified user (the augment always mutates governed state, D-08-05); the
 * session cookie rides `request()`'s `credentials:"include"`.
 */
export function resolveReconcile(uploadToken: string, choices: ReconcileChoice[]): Promise<UploadResponse> {
  return request<UploadResponse>("/api/reconcile/resolve", {
    method: "POST",
    body: JSON.stringify({ upload_token: uploadToken, choices }),
  });
}

/**
 * `POST /api/structural-hint/resolve` (UI-02, D-04) -- re-parses the
 * retained upload (found server-side by `upload_token`) with the human's
 * `StructuralHintIn` answer; returns the SAME discriminated shape
 * `uploadFile` does, since a re-submitted hint can itself still be
 * ambiguous (`api/wire.py::StructuralHintResolveRequest`).
 */
export function resolveHint(uploadToken: string, hint: StructuralHintIn): Promise<UploadResponse> {
  return request<UploadResponse>("/api/structural-hint/resolve", {
    method: "POST",
    body: JSON.stringify({ upload_token: uploadToken, hint }),
  });
}

/** A `POST /api/confirm` 422 -- the server-side P1 gate rejected the
 * request (a stale client state, a race, or a genuine bug -- never trusted
 * as impossible). Carries the target fields the server itself flagged
 * (`{"unclear_fields": [...]}`) so the Review screen can point at exactly
 * what to fix, and so it can distinguish "the gate rejected me" from any
 * other `ApiError` -- a 422 must never unlock export (UI-05, T-04-18). */
export class GateRejected extends Error {
  readonly unclearFields: string[];

  constructor(unclearFields: string[]) {
    super("The server's confirm gate rejected this request.");
    this.name = "GateRejected";
    this.unclearFields = unclearFields;
  }
}

function stringArrayField(detail: object, key: string): string[] {
  if (!(key in detail)) {
    return [];
  }
  const value = (detail as Record<string, unknown>)[key];
  return Array.isArray(value) ? value.filter((f): f is string => typeof f === "string") : [];
}

/** Reads the target-field names off EITHER 422 shape the server's confirm
 * gate can raise: `NotReadyError`'s `{unclear_fields}` (a covered field
 * still amber) or `FieldCoverageError`'s `{missing_fields}` (a field the
 * client's request dropped entirely, CR-02) -- both name fields that must
 * come back amber on the client (`state/review.ts::applyGateRejection`),
 * so both feed the same `GateRejected.unclearFields`. */
function unclearFieldsFrom(detail: unknown): string[] {
  if (!detail || typeof detail !== "object") {
    return [];
  }
  return [...stringArrayField(detail, "unclear_fields"), ...stringArrayField(detail, "missing_fields")];
}

/**
 * `POST /api/confirm` (API-02, P1, Plan 06) -- the server independently
 * rebuilds a fresh `MappingProposal` from the retained `upload_token` +
 * the human's edited `field_mappings` and re-validates; it never trusts
 * this request's own `needs_confirmation` values as the final verdict. A
 * 422 means the server's OWN gate rejected the request -- mapped here to a
 * typed `GateRejected(unclearFields)` (never a bare `ApiError`) so the
 * Review screen can show the rejection state without ever unlocking
 * export on its own client-side `isReady` mirror.
 */
export async function confirm(body: ConfirmRequest): Promise<ConfirmResponse> {
  try {
    return await request<ConfirmResponse>("/api/confirm", {
      method: "POST",
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      throw new GateRejected(unclearFieldsFrom(err.detail));
    }
    throw err;
  }
}

/** `POST /api/auth/signup` (AUTH-01/03, plan 06-02) -- creates an unverified
 * password account and (in this dev build) logs the `/verify?token=...` link
 * to the server console. A duplicate email surfaces as an `ApiError` (409)
 * the Sign Up screen renders inline. */
export function signUp(body: SignUpBody): Promise<SignUpAccepted> {
  return request<SignUpAccepted>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** `POST /api/auth/login` (AUTH-01) -- verifies the password and sets the
 * HttpOnly `di_session` cookie server-side; the returned `AuthUser` is the
 * session identity. Wrong credentials surface as an `ApiError` (401) with no
 * cookie set. An unverified user may still sign in (D-06-04). */
export function signIn(body: SignInBody): Promise<AuthUser> {
  return request<AuthUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** `POST /api/auth/logout` -- clears the session cookie server-side. The
 * body is ignored; the resolved promise just signals the cookie is gone. */
export function signOut(): Promise<void> {
  return request<void>("/api/auth/logout", { method: "POST" });
}

/** `GET /api/auth/me` -- the current session's `AuthUser`. A 401 surfaces as
 * an `ApiError` the caller treats as "signed out" (the mount-time session
 * probe dispatches SESSION_RESOLVED(null) on it). */
export function getMe(): Promise<AuthUser> {
  return request<AuthUser>("/api/auth/me", { method: "GET" });
}

/** `GET /api/auth/verify?token=...` (AUTH-03) -- consumes the console-printed
 * verification token; `{status:"verified"}` on success, `{status:"expired"}`
 * on any invalid/expired/tampered token (VerifyLanding branches on it). */
export function verifyEmail(token: string): Promise<VerifyResult> {
  return request<VerifyResult>(`/api/auth/verify?token=${encodeURIComponent(token)}`, {
    method: "GET",
  });
}

/** `GET /api/auth/config` (AUTH-02, D-06-05) -- the public auth feature
 * flags; `google_oauth_enabled` gates whether the "Continue with Google"
 * button is rendered at all (off by default). */
export function getAuthConfig(): Promise<AuthConfig> {
  return request<AuthConfig>("/api/auth/config", { method: "GET" });
}
