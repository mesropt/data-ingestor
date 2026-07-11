/**
 * The Review screen's state logic (UI-03/04/05/06) -- pure functions over
 * `FieldMappingOut[]`, no React import, mirroring `state/fieldSet.ts`/
 * `state/upload.ts`'s own "logic is tested, rendering is
 * gsd-ui-checker-validated" split.
 *
 * `isReady` mirrors `domain/models.py::MappingProposal.is_ready` EXACTLY --
 * every field clear (no `needs_confirmation` left) AND at least one field
 * exists (an empty mapping is never "ready", the same guard the domain
 * property documents against Python's `all([]) == True` trap). This is the
 * ONLY thing `ConfirmGate`'s disabled state derives from (UI-05, T-04-19) --
 * never a separately-computed client heuristic. The server independently
 * re-validates on `/api/confirm` regardless (P1) -- this module's job is a
 * UX mirror, not the authority.
 *
 * The three `resolveBy*` functions are the D-02 a/b/c resolution paths;
 * each updates exactly one field's resolution state immutably (a fresh
 * array, a fresh object for the touched field) and leaves every other
 * field's object reference untouched.
 */

import type {
  AlternativeOut,
  ConfirmFieldMappingIn,
  ConfirmRequest,
  FieldMappingOut,
  FieldSetPayload,
} from "../lib/types";

/** Mirrors `domain/models.py::MappingProposal.is_ready`. */
export function isReady(mappings: FieldMappingOut[]): boolean {
  return mappings.length > 0 && mappings.every((m) => !m.needs_confirmation);
}

export interface ResolutionProgress {
  clear: number;
  total: number;
}

/** "{clear} of {total} resolved" -- the ConfirmGate's progress text. */
export function resolutionProgress(mappings: FieldMappingOut[]): ResolutionProgress {
  return {
    clear: mappings.filter((m) => !m.needs_confirmation).length,
    total: mappings.length,
  };
}

function updateField(
  mappings: FieldMappingOut[],
  targetField: string,
  patch: Partial<FieldMappingOut>
): FieldMappingOut[] {
  return mappings.map((m) => (m.target_field === targetField ? { ...m, ...patch } : m));
}

/** D-02a: clicking a ranked-alternative chip resolves the field to that
 * column, adopting the chip's own confidence (the alternative the human
 * just picked, not the stale top-proposal confidence). Clears amber for
 * that field only. */
export function resolveByChip(
  mappings: FieldMappingOut[],
  targetField: string,
  candidate: AlternativeOut
): FieldMappingOut[] {
  return updateField(mappings, targetField, {
    source_column: candidate.source_column,
    confidence: candidate.confidence,
    needs_confirmation: false,
  });
}

/** D-02b: "Accept" keeps the `FieldMapping` exactly as Claude proposed it
 * (whether that is a real `source_column` or a null-column
 * `inferred_value`, MAP-02) -- it only clears amber. */
export function resolveByAccept(mappings: FieldMappingOut[], targetField: string): FieldMappingOut[] {
  return updateField(mappings, targetField, { needs_confirmation: false });
}

/** D-02c: the manual full-column dropdown -- the guaranteed escape hatch
 * when the correct column isn't among Claude's ranked alternatives.
 * Confidence is set to 1.0: a human explicitly chose this column, so
 * there is no meaningful "Claude confidence" left to show. */
export function resolveByDropdown(
  mappings: FieldMappingOut[],
  targetField: string,
  column: string
): FieldMappingOut[] {
  return updateField(mappings, targetField, {
    source_column: column,
    confidence: 1.0,
    needs_confirmation: false,
  });
}

export interface ConfirmOptions {
  saveProfile: boolean;
  export: boolean;
  provenance?: string;
}

/** The wire (edited field mapping) boundary -- drops `validator_note`
 * (`ConfirmFieldMappingIn` has no such field; it is the no-LLM validator's
 * own read-only annotation, never something the client edits or resends). */
function toConfirmFieldMapping(mapping: FieldMappingOut): ConfirmFieldMappingIn {
  return {
    target_field: mapping.target_field,
    source_column: mapping.source_column,
    confidence: mapping.confidence,
    reasoning: mapping.reasoning,
    needs_confirmation: mapping.needs_confirmation,
    inferred_value: mapping.inferred_value,
    alternatives: mapping.alternatives,
  };
}

/** Builds exactly the `/api/confirm` request shape the server rebuilds and
 * re-validates (P1) -- the client never sends a trusted `ready` flag as
 * the decision; `ConfirmRequest` has no such field to send at all.
 *
 * `field_set` is still sent (IN-01), but as of the CR-01 fix the server
 * treats it as informational only: it re-derives the field set's signature
 * and compares it against the one the upload was ACTUALLY resolved
 * against (`api.state.UploadEntry.field_set`), rejecting on any mismatch.
 * The retained field set -- never this payload's copy -- is what the gate
 * validates and assembles against. */
export function toConfirmPayload(
  uploadToken: string,
  fieldSet: FieldSetPayload,
  mappings: FieldMappingOut[],
  options: ConfirmOptions
): ConfirmRequest {
  return {
    upload_token: uploadToken,
    field_set: fieldSet,
    field_mappings: mappings.map(toConfirmFieldMapping),
    save_profile: options.saveProfile,
    export: options.export,
    ...(options.provenance !== undefined ? { provenance: options.provenance } : {}),
  };
}

/** UI-06 money shot: the `ProfileAppliedBanner` shows only when the
 * server's `/api/upload` (or `/api/structural-hint/resolve`) response
 * itself reports the auto-apply provenance -- a direct read of the
 * server's own claim, never a client-side guess. */
export function isAutoApplied(provenance: string | null): boolean {
  return provenance === "auto-applied-from-profile";
}
