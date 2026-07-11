/**
 * The reconcile panel's choice model (D-08-06, P1) -- a pure module with no
 * React dependency, so vitest covers the default -> per-conflict edit -> resolve
 * payload flow without rendering anything, mirroring `state/upload.ts`'s own
 * "logic is tested, rendering is checker-validated" split.
 *
 * A reconcile question lists alias-target disagreements between an uploaded map
 * file and the master crosswalk; the human picks, per conflict, keep_master or
 * take_map_file. Every conflict defaults to `keep_master` -- the safe,
 * no-op-against-master default (P1/D-08-02): choosing nothing changes nothing
 * on the governed master. `buildResolvePayload` serializes exactly the
 * `/api/reconcile/resolve` body shape (mirrors `state/upload.ts::buildHintPayload`).
 */

import type { ReconcileChoice, ReconcileConflict, ReconcileDecision } from "../lib/types";

/** One `ReconcileChoice` per conflict, keyed for lookup by the exact
 * `(vendor, source_column)` identity the conflict is defined on (D-08-04). */
export type ReconcileChoiceState = ReconcileChoice[];

/** Every conflict defaults to `keep_master` -- the safe default that leaves the
 * governed master untouched unless the human deliberately takes the map file. */
export function initialReconcileChoices(conflicts: ReconcileConflict[]): ReconcileChoiceState {
  return conflicts.map((conflict) => ({
    vendor: conflict.vendor,
    source_column: conflict.source_column,
    decision: "keep_master" as ReconcileDecision,
  }));
}

/** Updates only the choice whose exact `(vendor, source_column)` pair matches;
 * returns a new array (never mutates the previous state) so React re-renders. */
export function setChoice(
  state: ReconcileChoiceState,
  sourceColumn: string,
  vendor: string,
  decision: ReconcileDecision
): ReconcileChoiceState {
  return state.map((choice) =>
    choice.source_column === sourceColumn && choice.vendor === vendor
      ? { ...choice, decision }
      : choice
  );
}

/** The full `POST /api/reconcile/resolve` request body -- mirrors
 * `api/wire.py::ReconcileResolveRequest`. */
export interface ReconcileResolvePayload {
  upload_token: string;
  choices: ReconcileChoice[];
}

/** Builds exactly the resolve body: the retained `upload_token` plus one
 * `{vendor, source_column, decision}` entry per conflict and no extras -- the
 * client only picks a side, never re-sends the server-retained envelope
 * (T-08-08). */
export function buildResolvePayload(
  uploadToken: string,
  choices: ReconcileChoiceState
): ReconcileResolvePayload {
  return {
    upload_token: uploadToken,
    choices: choices.map((choice) => ({
      vendor: choice.vendor,
      source_column: choice.source_column,
      decision: choice.decision,
    })),
  };
}
