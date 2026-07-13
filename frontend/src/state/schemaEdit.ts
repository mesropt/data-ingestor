/**
 * The Schemas page's pure logic (D-10-10/D-10-11, Plan 10-06) -- a NO-React
 * module (vitest runs in `environment: 'node'`, see `frontend/vite.config.ts`)
 * mirroring `state/fieldSet.ts`'s "logic is tested, rendering is
 * gsd-ui-checker-validated" split. `Schemas.tsx` and its sub-components are
 * the untested wiring seam over these functions, exactly as `Review.tsx` is
 * to `state/review.ts`.
 *
 * `SchemaFieldDraft` deliberately mirrors `state/fieldSet.ts::DraftField`
 * (minus its client-only `id`) -- `CanonicalField`'s constraints ARE
 * `Field`'s constraints (D-10-11), so `SchemaFieldConstraintsForm` reuses
 * `FieldEditorRow`'s exact grid against this same shape, never a re-derived
 * one. The serialization function below is written fresh in this file
 * (rather than importing `fieldSet.ts`'s private, unexported helper of the
 * same name) because `fieldSet.ts` is out of this plan's `files_modified`
 * scope -- both target the identical `FieldPayload` wire contract the
 * server's `fields.loader.from_dict` accepts, so this is not a second,
 * hand-derived SHAPE, only a second (small, intentional) implementation of
 * the same contract, bounded by the plan's own file list.
 */

import type { CanonicalFieldPayload, FieldPayload, FieldType, SchemaOut } from "../lib/types";

/** Mirrors `fields/loader.py::MAX_FIELDS` (UX cap only -- the server's
 * `add_schema_field` re-checks the SAME cap against the Schema's live field
 * count; this is never the authority, T-04-14 precedent). */
export const MAX_FIELDS = 50;

/** The UI's "no type declared" sentinel -- maps to `Field.type = None`
 * server-side, matching `state/fieldSet.ts::DraftFieldType`'s own convention. */
export type SchemaFieldDraftType = FieldType | "none";

/** One canonical field's in-progress constraints-form state -- the exact
 * shape `FieldEditorRow` edits, minus `state/fieldSet.ts::DraftField`'s
 * client-only `id` (the Schemas screen supplies its own stable id, since a
 * field's `name` itself is the editable rename target here, not a fixed key). */
export interface SchemaFieldDraft {
  name: string;
  description: string;
  type: SchemaFieldDraftType;
  allowedValues: string[];
  unit: string;
  required: boolean;
  min: number | null;
  max: number | null;
  dateFormat: string;
}

const NUMERIC_TYPES: ReadonlySet<SchemaFieldDraftType> = new Set(["number", "integer"]);

/**
 * Serializes a constraints-form draft into exactly the `FieldPayload` shape
 * the server's `fields.loader.from_dict` accepts (byte-compatible). Empty
 * strings become `null`, never `""`; `allowed_values` is `null` when empty,
 * never `[]`; min/max travel only for a numeric type, date_format only for a
 * date type -- a stray value left over from a since-changed type never leaks
 * into the payload.
 */
export function toFieldPayload(draft: SchemaFieldDraft): FieldPayload {
  const isNumeric = NUMERIC_TYPES.has(draft.type);
  const isDate = draft.type === "date";
  return {
    name: draft.name,
    description: draft.description ? draft.description : null,
    type: draft.type === "none" ? null : draft.type,
    allowed_values: draft.allowedValues.length > 0 ? draft.allowedValues : null,
    unit: draft.unit ? draft.unit : null,
    required: draft.required,
    min: isNumeric ? draft.min : null,
    max: isNumeric ? draft.max : null,
    date_format: isDate ? (draft.dateFormat ? draft.dateFormat : null) : null,
  };
}

/**
 * The inverse of `toFieldPayload` -- seeds a constraints-form draft from a
 * `CanonicalFieldPayload` (the server's authoritative post-edit state), so a
 * `SchemaFieldRow` expansion always shows the last-saved values, never a
 * stale local guess.
 */
export function fromCanonicalField(field: CanonicalFieldPayload): SchemaFieldDraft {
  return {
    name: field.name,
    description: field.description ?? "",
    type: field.type ?? "none",
    allowedValues: field.allowed_values ?? [],
    unit: field.unit ?? "",
    required: field.required,
    min: field.min,
    max: field.max,
    dateFormat: field.date_format ?? "",
  };
}

/** Pluralizes a bare count noun ("alias"/"vendor alias") -- `1` stays
 * singular, everything else (including `0`) is plural. */
function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

/**
 * The collapsed row's `Label/mono` summary (D-10-10): `type · unit ·
 * required · N alias(es)`, omitting every absent part cleanly -- a field
 * with no type/unit shows only `required · 0 aliases` (or just `0 aliases`
 * when also not required), never `null · null · ...`.
 */
export function fieldSummaryLine(field: CanonicalFieldPayload): string {
  const parts: string[] = [];
  if (field.type) {
    parts.push(field.type);
  }
  if (field.unit) {
    parts.push(field.unit);
  }
  if (field.required) {
    parts.push("required");
  }
  const aliasCount = field.aliases.length;
  parts.push(`${aliasCount} ${pluralize(aliasCount, "alias", "aliases")}`);
  return parts.join(" · ");
}

/** False at `MAX_FIELDS` (50) -- the "Add Field" field-cap tooltip state,
 * checked against the Schema's LIVE field count (`SchemaOut.fields` is
 * already tombstone-filtered by the server, D-10-15). UX cap only; the
 * server's `add_schema_field` independently enforces the same cap. */
export function canAddField(schema: SchemaOut): boolean {
  return schema.fields.length < MAX_FIELDS;
}

/**
 * The delete-canonical-field destructive confirmation's body copy (verbatim
 * per `10-UI-SPEC.md` § Copywriting Contract, minus the "Delete field:"
 * title prefix a caller renders separately as the `AlertDialogTitle`),
 * correctly pluralized for 0, 1, and N aliases.
 */
export function deleteFieldWarning(field: Pick<CanonicalFieldPayload, "name" | "aliases">): string {
  const aliasCount = field.aliases.length;
  const noun = pluralize(aliasCount, "vendor alias", "vendor aliases");
  return `This removes '${field.name}' and its ${aliasCount} ${noun} from the Schema. Files already mapped with it are unaffected. This can't be undone.`;
}
