/**
 * The Schema selector's state logic (D-07-07, SCHEMA-01/02/03) -- a pure
 * reducer + selectors over the governed-Schema list, with NO React import,
 * mirroring `state/auth.ts`/`state/review.ts`'s "logic is tested, rendering
 * is gsd-ui-checker-validated" split.
 *
 * This is only the browser's convenience mirror of `/api/schemas`: it holds
 * the last-loaded list and which Schema the curator has picked for the
 * confirm-time crosswalk accrual. The server remains authoritative for every
 * mutation (promote/import are re-checked by `require_verified_user`, P1).
 */

import type { SchemaSummary } from "../lib/types";

export interface SchemaSelectionState {
  schemas: SchemaSummary[];
  selected: string | null;
}

export const initialSchemaState: SchemaSelectionState = { schemas: [], selected: null };

export type SchemaAction =
  | { type: "LOADED"; schemas: SchemaSummary[] }
  | { type: "SELECT"; name: string }
  | { type: "RENAMED"; from: string; to: string }
  | { type: "CLEAR" };

export function schemaReducer(state: SchemaSelectionState, action: SchemaAction): SchemaSelectionState {
  switch (action.type) {
    case "LOADED": {
      // Reloading the list (e.g. after a promote) preserves the current
      // selection ONLY while that Schema still exists -- a selection that
      // vanished from the server list is dropped, never left dangling.
      const stillPresent = state.selected !== null && action.schemas.some((s) => s.name === state.selected);
      return { schemas: action.schemas, selected: stillPresent ? state.selected : null };
    }

    case "SELECT":
      return { ...state, selected: action.name };

    case "RENAMED": {
      // A rename moves only the label (the server keeps the id and every
      // field/alias): patch the list in place and follow the selection to
      // the new name, so the screen never briefly shows a dropped selection
      // while the authoritative list reloads.
      const schemas = state.schemas.map((s) => (s.name === action.from ? { ...s, name: action.to } : s));
      return { schemas, selected: state.selected === action.from ? action.to : state.selected };
    }

    case "CLEAR":
      return { ...state, selected: null };

    default:
      return state;
  }
}

/** The full summary for the currently-selected name, or `null` when nothing
 * is selected (or the selected name is somehow absent from the list). */
export function selectedSchema(state: SchemaSelectionState): SchemaSummary | null {
  if (state.selected === null) {
    return null;
  }
  return state.schemas.find((s) => s.name === state.selected) ?? null;
}
