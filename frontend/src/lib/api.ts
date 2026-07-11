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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : body;
    throw new ApiError(response.status, detail);
  }
  return body as T;
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
 * `POST /api/upload` -- filled in by Plan 05's Upload screen. Typed now so
 * `lib/api.ts` is the one place every screen imports from, but not called
 * until that plan wires the dropzone/hint flow to it.
 */
export function uploadFile(
  _file: File,
  _fieldSetId: string,
  _headersOnly: boolean
): Promise<UploadResponse> {
  throw new Error("uploadFile is implemented in Plan 05 (Upload screen)");
}

/**
 * `POST /api/structural-hint/resolve` -- filled in by Plan 05's
 * StructuralHintPanel (D-04).
 */
export function resolveStructuralHint(
  _uploadToken: string,
  _hint: StructuralHintIn
): Promise<UploadResponse> {
  throw new Error("resolveStructuralHint is implemented in Plan 05 (Upload screen)");
}

/**
 * `POST /api/confirm` -- filled in by Plan 06's Review screen (the P1
 * confirm gate).
 */
export function confirm(_body: ConfirmRequest): Promise<ConfirmResponse> {
  throw new Error("confirm is implemented in Plan 06 (Review screen)");
}
