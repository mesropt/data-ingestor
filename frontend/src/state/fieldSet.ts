/**
 * The field-set editor's state -- pure reducer/helper functions with no
 * React dependency, so vitest covers the add/remove/edit/serialize logic
 * without rendering anything (Task 2's own framing: "the visual rendering
 * is validated by gsd-ui-checker against 04-UI-SPEC.md, not by fabricated
 * pixel unit tests").
 *
 * `MAX_FIELDS`/`MAX_NAME_LENGTH` mirror `src/assayingest/fields/loader.py`'s
 * `MAX_FIELDS`/`_MAX_NAME_LENGTH` for UX only -- the server's
 * `fields.loader.from_dict` is the ONLY authoritative gate (T-04-14); a
 * client-side block here is pure convenience, never trusted as the check.
 */

import type { FieldPayload, FieldSetPayload, FieldType } from "../lib/types";

/** Mirrors `fields/loader.py::MAX_FIELDS` (UX cap only, not the gate). */
export const MAX_FIELDS = 50;

/** Mirrors `fields/loader.py::_MAX_NAME_LENGTH` (UX cap only, not the gate). */
export const MAX_NAME_LENGTH = 64;

/** The UI's "no type declared" sentinel -- maps to `Field.type = None`
 * server-side (`fields/models.py::Field.type` defaults to `None`). */
export type DraftFieldType = FieldType | "none";

/** One field's in-progress declaration in the editor. `id` is a
 * client-only identity (never sent to the server) so React can key/edit a
 * row stably even before it has a name. */
export interface DraftField {
  id: string;
  name: string;
  description: string;
  type: DraftFieldType;
  allowedValues: string[];
  unit: string;
  required: boolean;
  min: number | null;
  max: number | null;
  dateFormat: string;
}

/** The whole field set being edited -- `name` is both the saved
 * template's name (`FieldSetIn.name`) and the domain `FieldSet.name`
 * (`FieldSet.to_dict()`'s own `name` key); this app has one name input,
 * not two divergent concepts. */
export interface FieldSetDraftState {
  name: string;
  fields: DraftField[];
}

let _nextId = 0;

/** A monotonic client-only id -- stable across renders, never round-tripped
 * to the server (Field has no id of its own). */
function newFieldId(): string {
  _nextId += 1;
  return `field-${_nextId}`;
}

export function createEmptyFieldSetDraft(): FieldSetDraftState {
  return { name: "", fields: [] };
}

function createDefaultField(): DraftField {
  return {
    id: newFieldId(),
    name: "",
    description: "",
    type: "none",
    allowedValues: [],
    unit: "",
    required: true,
    min: null,
    max: null,
    dateFormat: "",
  };
}

/** Appends a default field (required=true, type="none"). Refuses beyond
 * `MAX_FIELDS` -- returns the state unchanged rather than throwing, so a
 * caller can just re-render the same (now at-cap) state. */
export function addField(state: FieldSetDraftState): FieldSetDraftState {
  if (state.fields.length >= MAX_FIELDS) {
    return state;
  }
  return { ...state, fields: [...state.fields, createDefaultField()] };
}

export function removeField(state: FieldSetDraftState, id: string): FieldSetDraftState {
  return { ...state, fields: state.fields.filter((field) => field.id !== id) };
}

/** Updates a single field's attribute(s) immutably -- every other field
 * (and the field object itself, if `id` doesn't match) is left untouched. */
export function editField(
  state: FieldSetDraftState,
  id: string,
  patch: Partial<Omit<DraftField, "id">>
): FieldSetDraftState {
  return {
    ...state,
    fields: state.fields.map((field) => (field.id === id ? { ...field, ...patch } : field)),
  };
}

const NUMERIC_TYPES: ReadonlySet<DraftFieldType> = new Set(["number", "integer"]);

function toFieldPayload(field: DraftField): FieldPayload {
  const isNumeric = NUMERIC_TYPES.has(field.type);
  const isDate = field.type === "date";
  return {
    name: field.name,
    description: field.description ? field.description : null,
    type: field.type === "none" ? null : field.type,
    allowed_values: field.allowedValues.length > 0 ? field.allowedValues : null,
    unit: field.unit ? field.unit : null,
    required: field.required,
    // Type-dependent serialization (Task 2 behavior): min/max only travel
    // for number/integer, date_format only for date -- a stray value left
    // in draft state from a since-changed type never leaks into the payload.
    min: isNumeric ? field.min : null,
    max: isNumeric ? field.max : null,
    date_format: isDate ? (field.dateFormat ? field.dateFormat : null) : null,
  };
}

/** Produces exactly the `{name, fields:[...]}` shape
 * `fields/models.py::FieldSet.to_dict()` returns -- the `/api/field-sets`
 * POST body's `field_set` key and `/api/upload`'s `field_set` both expect
 * this byte-compatible shape (Plan 03's `fields.loader.from_dict`). */
export function toFieldSetPayload(state: FieldSetDraftState): FieldSetPayload {
  return {
    name: state.name ? state.name : null,
    fields: state.fields.map(toFieldPayload),
  };
}
