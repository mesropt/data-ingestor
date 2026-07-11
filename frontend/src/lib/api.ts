/**
 * Fetch wrappers for the FastAPI backend (`src/assayingest/api/routes/*`).
 * Every function here calls a real endpoint through `fetch`, decodes the
 * JSON body, and raises a typed `ApiError` on any non-2xx response so a
 * caller (DefineFields.tsx, Plans 05/06's Upload/Review screens) can
 * branch on `error.status` without re-parsing a generic `Error.message`
 * string.
 */

import type {
  ConfirmRequest,
  ConfirmResponse,
  FieldSetPayload,
  FieldSetTemplate,
  StructuralHintIn,
  UploadResponse,
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
  sheet?: string
): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  body.append("field_set", JSON.stringify(fieldSet));
  body.append("headers_only", headersOnly ? "true" : "false");
  if (sheet !== undefined) {
    body.append("sheet", sheet);
  }

  const response = await fetch("/api/upload", { method: "POST", body });
  return parseResponse<UploadResponse>(response);
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

/**
 * `POST /api/confirm` -- filled in by Plan 06's Review screen (the P1
 * confirm gate).
 */
export function confirm(_body: ConfirmRequest): Promise<ConfirmResponse> {
  throw new Error("confirm is implemented in Plan 06 (Review screen)");
}
