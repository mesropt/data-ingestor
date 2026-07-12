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
  UnclearDetail,
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

/** Re-edit a resolved (green) field -- flips it back to
 * `needs_confirmation: true` so `FieldRow` renders the D-02 resolution
 * controls (chips/Accept/dropdown) again, WITHOUT losing the field's
 * current `source_column`/`alternatives`/`confidence` -- the user is
 * re-opening a choice they already made, not starting from a blank slate.
 * Picking a chip/Accept/dropdown option afterward goes through the
 * existing `resolveBy*` functions exactly as it would for any amber
 * field. Every other field's object reference is left untouched. */
export function reopenField(mappings: FieldMappingOut[], targetField: string): FieldMappingOut[] {
  return updateField(mappings, targetField, { needs_confirmation: true });
}

/** The client-side mirror of the server's P1 confirm gate rejecting a
 * request (`api.ts::GateRejected.unclearFields`, sourced from either
 * `NotReadyError`'s `{unclear_fields}` or `FieldCoverageError`'s
 * `{missing_fields}` 422 body). Re-flags exactly the named fields back to
 * `needs_confirmation: true` -- turning the confirm dead-end into a
 * resolvable state: those fields become amber again, reveal their
 * controls, and the user can re-map them and re-confirm. Fields not named
 * are left completely untouched (same object reference), matching
 * `reopenField`'s "never lose what's already resolved" contract. */
export function applyGateRejection(mappings: FieldMappingOut[], unclearFieldNames: string[]): FieldMappingOut[] {
  const rejected = new Set(unclearFieldNames);
  return mappings.map((m) => (rejected.has(m.target_field) ? { ...m, needs_confirmation: true } : m));
}

/** One rejected field's line in the Review alert -- `reason` is `null` when
 * the no-LLM validator recorded none (VAL-03), and a null reason must
 * still be rendered with its `name` (never dropped). */
export interface GateRejectionField {
  name: string;
  reason: string | null;
}

/** The Review screen's confirm-error state: a plain string for every
 * non-gate failure (unchanged today's shape), or the structured shape a
 * gate rejection produces -- never a newline-concatenated string, so the
 * screen can render a real list instead of guessing where to split one. */
export type ConfirmError = string | { fields: GateRejectionField[] };

/** The PURE message-shaping function for a gate rejection (this is what
 * makes the Review alert testable under `environment: 'node'` -- no React,
 * no DOM). Maps each `GateRejected.unclearDetails` entry to `{name,
 * reason}`, preserving order and NEVER dropping a null-reason entry: a
 * field the server named is always named back to the human, reason or no
 * reason. */
export function gateRejection(details: UnclearDetail[]): ConfirmError {
  return { fields: details.map((d) => ({ name: d.field, reason: d.reason })) };
}

export interface ConfirmOptions {
  saveProfile: boolean;
  export: boolean;
  provenance?: string;
  /** Additive Phase 07 crosswalk carry (ALIAS-04): when BOTH a target Schema
   * name and a vendor are supplied, the confirm accretes each resolved
   * (canonical field <- source column) as a manual, user-attributed alias on
   * that Schema. When omitted, the payload is byte-identical to Plan 06's and
   * nothing is written (the server no-ops without them). */
  schemaName?: string;
  vendor?: string;
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
    ...(options.schemaName !== undefined ? { schema_name: options.schemaName } : {}),
    ...(options.vendor !== undefined ? { vendor: options.vendor } : {}),
  };
}

/** The Review header's subject line (quick 260712): "what file, onto what
 * Schema" -- `{source file} — {Schema}`, or just the Schema when the wire
 * carried no filename (an older server, a fixture). NEVER the raw upload
 * token: a UUID means nothing to a curator and stays out of the UI
 * entirely. Pure so the copy is testable under `environment: 'node'`. */
export function reviewSubject(sourceName: string | null | undefined, schemaName: string): string {
  const file = sourceName?.trim();
  return file ? `${file} — ${schemaName}` : schemaName;
}

/** UI-06 money shot: the `ProfileAppliedBanner` shows only when the
 * server's `/api/upload` (or `/api/structural-hint/resolve`) response
 * itself reports the auto-apply provenance -- a direct read of the
 * server's own claim, never a client-side guess. */
export function isAutoApplied(provenance: string | null): boolean {
  return provenance === "auto-applied-from-profile";
}
