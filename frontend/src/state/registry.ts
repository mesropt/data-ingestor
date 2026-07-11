/**
 * Pure data-shaping for the Mapping Registry (REG-01, REG-02, D-09-03) -- a
 * NO-React module (vitest runs in the `node` environment, mirroring
 * `state/schema.ts`) that turns a `MasterMapEnvelope` into per-canonical-field
 * alias rows the presentational `RegistryTable` renders verbatim.
 *
 * Provenance is returned as STRUCTURED fields (label + actor + when as separate
 * strings), never pre-concatenated markup, so the React layer escapes each part
 * by default -- the crosswalk carries untrusted vendor / source / actor text
 * (T-09-01). Timestamps humanise to a fixed, locale-independent absolute UTC
 * form so tests stay deterministic (no relative "3 hours ago").
 */

import type { AliasPayload, MasterMapEnvelope } from "../lib/types";

/** The quiet metadata shown under a canonical field name (D-09-03) -- the
 * subset of `CanonicalFieldPayload` the registry surfaces as mono constraints,
 * renamed to the browser's camelCase view. */
export interface FieldMetadata {
  type: string | null;
  unit: string | null;
  allowedValues: string[] | null;
  min: number | null;
  max: number | null;
}

/** One canonical field's registry row: its identity + quiet metadata on the
 * left, its vendor aliases (verbatim from the envelope) on the right, and a
 * `hasAliases` flag driving the per-field "no vendor aliases recorded yet"
 * empty state -- a field is never dropped just because it has no aliases. */
export interface FieldRow {
  name: string;
  description: string | null;
  required: boolean;
  metadata: FieldMetadata;
  aliases: AliasPayload[];
  hasAliases: boolean;
}

/** A structured, escape-ready view of one alias's provenance (REG-02) -- the
 * component renders `label`, `actor`, and `when` as separate escaped text
 * spans; this shape is never HTML. */
export interface Provenance {
  kind: string;
  label: string;
  actor: string;
  when: string;
}

/** The known provenance kinds the backend records (`domain/models.py::Alias`)
 * mapped to their human labels. An unknown kind falls back to its own raw text
 * so a future/unexpected kind renders legibly instead of throwing. */
const PROVENANCE_LABELS: Record<string, string> = {
  manual: "manual",
  from_map_file: "from map file",
};

/**
 * One row per canonical field IN THE ENVELOPE'S FIELD ORDER (never re-sorted),
 * carrying the field's quiet metadata + its aliases verbatim. A field with an
 * empty aliases array yields `hasAliases: false` and is kept in the list.
 */
export function groupFieldRows(envelope: MasterMapEnvelope): FieldRow[] {
  return envelope.fields.map((field) => ({
    name: field.name,
    description: field.description,
    required: field.required,
    metadata: {
      type: field.type,
      unit: field.unit,
      allowedValues: field.allowed_values,
      min: field.min,
      max: field.max,
    },
    aliases: field.aliases,
    hasAliases: field.aliases.length > 0,
  }));
}

/**
 * The structured provenance for one alias: `manual` -> the acting user's email,
 * `from_map_file` -> the source map file's name (both carried in
 * `provenance_actor`). An unknown kind renders its own raw text as the label so
 * nothing throws or silently disappears.
 */
export function formatProvenance(alias: AliasPayload): Provenance {
  const label = PROVENANCE_LABELS[alias.provenance_kind] ?? alias.provenance_kind;
  return {
    kind: alias.provenance_kind,
    label,
    actor: alias.provenance_actor,
    when: formatWhen(alias.created_at),
  };
}

const TWO_DIGITS = (value: number): string => String(value).padStart(2, "0");

/**
 * Humanise an ISO-8601 `created_at` to a stable, locale-independent absolute
 * UTC form (e.g. `2026-07-11 14:32 UTC`). An empty or unparseable value yields
 * `"unknown date"` -- this never throws, so a malformed timestamp can't blank
 * or crash the registry.
 */
export function formatWhen(createdAt: string): string {
  if (!createdAt) {
    return "unknown date";
  }
  const at = new Date(createdAt);
  if (Number.isNaN(at.getTime())) {
    return "unknown date";
  }
  const date = `${at.getUTCFullYear()}-${TWO_DIGITS(at.getUTCMonth() + 1)}-${TWO_DIGITS(at.getUTCDate())}`;
  const time = `${TWO_DIGITS(at.getUTCHours())}:${TWO_DIGITS(at.getUTCMinutes())}`;
  return `${date} ${time} UTC`;
}

/**
 * True when the whole Schema has nothing to show yet: zero canonical fields, or
 * every field carries zero aliases (drives the whole-Schema empty state, D-09-03).
 */
export function isSchemaEmpty(envelope: MasterMapEnvelope): boolean {
  if (envelope.fields.length === 0) {
    return true;
  }
  return envelope.fields.every((field) => field.aliases.length === 0);
}
