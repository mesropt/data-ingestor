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
  SheetMemberResponse,
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

/** The vendor gate's disabled reason (quick 260712) -- the vendor (source
 * label) is MANDATORY on confirm: the server rejects a blank one (P1), so
 * the Confirm button must never look enabled while this guard would reject
 * the click (the exact silent no-op that was already a reported bug once).
 * Whitespace-only is not a vendor, mirroring the server's own trim rule.
 * `null` means the vendor gate is satisfied. Pure so `ConfirmGate`'s
 * tooltip copy is testable under `environment: 'node'`. */
export function vendorBlockedReason(vendor: string): string | null {
  return vendor.trim() === ""
    ? "Enter the vendor (source label) before confirming — it records whose format this file was."
    : null;
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

// --- Phase 11-10: the tabbed group Review's pure derivations ---------------
// One sheet group = N INDEPENDENT datasets (D-11-08). Everything the tab
// strip and the group bar decide lives HERE as tested pure functions; the
// `ReviewGroupTabs` component renders these verdicts and decides nothing.

/** One member's client-side snapshot inside a sheet group: its CURRENT wire
 * arm (a question resolve can swap it in place), the LIVE mappings its own
 * `Review` reports up (the amber count must track the curator's work, not
 * the stale wire response), and whether its OWN confirm succeeded. There is
 * deliberately no group-level `ready` anywhere in this shape -- a member's
 * gate is its own (D-11-08) and nothing here aggregates readiness. */
export interface GroupMemberView {
  sheetName: string;
  response: SheetMemberResponse;
  mappings: FieldMappingOut[];
  confirmed: boolean;
}

/** One tab's status indicator, exactly the UI-SPEC's four states: a pending
 * question (amber dot), n amber fields to resolve (amber count badge),
 * ready (no glyph -- the member's own ConfirmGate carries that state), or
 * confirmed (green check). */
export type MemberStatus =
  | { kind: "question" }
  | { kind: "resolve"; count: number }
  | { kind: "ready" }
  | { kind: "confirmed" };

/** Derives ONE member's status from that member alone -- no sibling is ever
 * read, so no status can leak across tabs (the per-member gate discipline,
 * D-11-08). `confirmed` wins over everything: a confirmed member's
 * mappings are settled history. Any non-`mapping` arm is a pending
 * question (structural/date -- and defensively reconcile, which cannot
 * structurally arise for a member but is in the union). */
export function memberStatus(member: GroupMemberView): MemberStatus {
  if (member.confirmed) {
    return { kind: "confirmed" };
  }
  if (member.response.kind !== "mapping") {
    return { kind: "question" };
  }
  const amber = member.mappings.filter((m) => m.needs_confirmation).length;
  return amber > 0 ? { kind: "resolve", count: amber } : { kind: "ready" };
}

/** The group "Download All" bar's disabled reason -- a LOOKUP over the
 * per-member `confirmed` flags, never a new gate (T-11-38: the server
 * additionally refuses the archive while any member has no recorded run).
 * `null` means every member is confirmed and the archive may be offered.
 * While blocked, the reason names how many datasets are still unconfirmed
 * -- the UI-SPEC sentence alone (group size) when nothing is confirmed
 * yet, with the outstanding count appended once confirmations diverge from
 * the total (mirroring the server's own 409 detail, which names
 * "{n} of {total} still unconfirmed"). */
export function groupExportBlockedReason(members: GroupMemberView[]): string | null {
  const unconfirmed = members.filter((m) => !m.confirmed).length;
  if (unconfirmed === 0) {
    return null;
  }
  const base = `Confirm all ${members.length} datasets to download the archive.`;
  if (unconfirmed === members.length) {
    return base;
  }
  return `${base.slice(0, -1)} — ${unconfirmed} still unconfirmed.`;
}

/** SHEET-01's no-regression clause: a single-member group renders with NO
 * tab strip and NO group bar -- visually today's Review plus the
 * provenance line. The strip and the bar appear together, from two
 * members up. */
export function showTabStrip(members: readonly unknown[]): boolean {
  return members.length > 1;
}

/** T-11-37 (critical): the React key for one member's pane. It derives from
 * the member's OWN upload token and from nothing else -- this function
 * cannot even see which tab is active, so no tab switch can change a
 * member's key and remount its `Review` (whose local amber resolutions a
 * remount would silently destroy). A member whose question resolves gets a
 * FRESH token from the server, and the fresh key then remounts its Review
 * with fresh state -- exactly the existing `App.tsx` "keyed by
 * upload_token" contract, per member. */
export function memberPaneKey(member: GroupMemberView): string {
  return member.response.upload_token;
}

/** D-11-15: the Review header's provenance line -- "sheet {name}", mono,
 * on EVERY ingest. The worksheet title when the ingest has one (a group
 * member's tab), the source FILE's name when it does not (a CSV -- the
 * same fallback `service.confirm` itself writes into `__source_sheet`:
 * `table.origin_sheet or source_label`). `null` only when the wire carried
 * neither label (an old fixture): an empty "sheet " line would be a
 * provenance claim with nothing behind it. */
export function provenanceLine(
  sheetName: string | null | undefined,
  sourceName: string | null | undefined
): string | null {
  const name = sheetName?.trim() || sourceName?.trim();
  return name ? `sheet ${name}` : null;
}
