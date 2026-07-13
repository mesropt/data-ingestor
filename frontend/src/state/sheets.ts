/**
 * The sheet-question panel's pure pre-selection/gating/payload/copy logic
 * (SHEET-01/05, D-11-06) -- a module with NO React import, so vitest covers
 * it under the `node` test environment, mirroring `state/dateFormat.ts`'s
 * own "logic is tested, rendering is gsd-ui-checker-validated" split. ALL
 * panel decisions live here; `SheetQuestionPanel` holds only the answers
 * map and the submitting flag.
 *
 * Three invariants this module enforces structurally:
 * - `proposals: []` IS the propose-skip signal (11-07's ruling) -- the tick
 *   state reads the proposal LIST, never `proposed_schema`, so the human's
 *   own Upload pick can fill the Select on a skip-proposed sheet WITHOUT
 *   the tool ticking it for them (D-11-16).
 * - A tie pre-fills NOTHING, and the Upload dropdown does not get to settle
 *   it either: a stale default is not evidence, and letting it break a
 *   genuine tie would be exactly the silent guess D-11-06 forbids.
 * - `submitBlockedReason` mirrors the server's own fail-closed 422s (an
 *   empty selection, T-11-22's manifest validation) -- it never relies on
 *   the server alone to catch an empty or Schema-less submission.
 */

import type {
  SheetOut,
  SheetQuestionResponse,
  SheetResolveRequest,
  SheetSchemaProposal,
} from "../lib/types";

/** One sheet's answer-in-progress: the tick and the per-sheet Schema. The
 * panel holds a `SheetChoice[]` in local state; every derivation over it
 * lives here. */
export interface SheetChoice {
  sheetName: string;
  ticked: boolean;
  schemaName: string | null;
}

/** Whether this sheet arrives pre-ticked (D-11-06, verbatim): a proposal
 * exists AND the structural gate passed. A gate-failed sheet (`drawing_only`
 * / `unsupported_shape` / `header_uncertain`) arrives UNTICKED however well
 * it scores -- meridian's LEGEND honestly scores 1/7 (D-11-24) and no
 * coverage threshold exists to suppress it, so the visible coverage number
 * is the only thing telling the human it is a legend. It stays present and
 * tickable: if the human insists, the failure surfaces as that member's own
 * structural question (SHEET-04: marked, never dropped, never disabled
 * away). */
function _isPreTicked(sheet: SheetOut): boolean {
  return sheet.status === "ok" && sheet.proposals.length > 0;
}

/** Which Schema this sheet's Select arrives pre-filled with. A tie leaves
 * it EMPTY -- hard short-circuit, above every fallback. Otherwise the
 * server's own precedence (`wire.py::_pre_selection`: scorer's top proposal
 * -> the human's Upload pick -> nothing) is trusted first, with
 * `defaultSchema` as the client-side D-11-16 fallback for responses that
 * predate the server-side default. */
function _preSelectedSchema(sheet: SheetOut, defaultSchema: string | null): string | null {
  if (sheet.tie) return null;
  return sheet.proposed_schema ?? defaultSchema;
}

/** Derives the panel's initial `SheetChoice[]` from the wire manifest, in
 * manifest order -- the four pre-selection states of D-11-06 exactly:
 * proposal -> ticked + that Schema; zero coverage -> unticked + skip; tie ->
 * ticked + EMPTY Select; gate-failed -> unticked but still selectable. */
export function initialSelections(
  response: SheetQuestionResponse,
  defaultSchema: string | null
): SheetChoice[] {
  return response.sheets.map((sheet) => ({
    sheetName: sheet.sheet_name,
    ticked: _isPreTicked(sheet),
    schemaName: _preSelectedSchema(sheet, defaultSchema),
  }));
}

/** The submit button's disabled reason (UI-SPEC Copywriting Contract,
 * verbatim), or `null` when ready. Fail-closed in the same two places the
 * server refuses: nothing ticked (the wire's empty-selections 422) and a
 * ticked sheet with no Schema chosen (a tie the tool refuses to break, or
 * a zero-proposal override the human started but did not finish). */
export function submitBlockedReason(selections: SheetChoice[]): string | null {
  const ticked = selections.filter((choice) => choice.ticked);
  if (ticked.length === 0) {
    return "Tick at least one sheet to ingest.";
  }
  const missingSchema = ticked.find((choice) => choice.schemaName === null);
  if (missingSchema !== undefined) {
    return `Choose a Schema for '${missingSchema.sheetName}' — ties aren't broken automatically.`;
  }
  return null;
}

/** Builds exactly `api/wire.py::SheetResolveRequest` -- ONLY ticked sheets,
 * each with its chosen Schema. An unticked sheet is simply absent: skipping
 * modifies nothing and sends nothing (T-08-08 -- the client only ever
 * chooses among options the server already offered). */
export function toResolvePayload(uploadToken: string, selections: SheetChoice[]): SheetResolveRequest {
  return {
    upload_token: uploadToken,
    selections: selections
      .filter((choice) => choice.ticked && choice.schemaName !== null)
      .map((choice) => ({
        sheet_name: choice.sheetName,
        schema_name: choice.schemaName as string,
      })),
  };
}

/** The coverage line above the matched pairs (UI-SPEC Copywriting Contract,
 * verbatim per source). The `claude` arm reads as a warning, not a score,
 * because it IS one: D-11-19's last-resort ranking carries no crosswalk
 * evidence at all, and a human is entitled to know a proposal has nothing
 * behind it. */
export function coverageLine(proposal: SheetSchemaProposal): string {
  switch (proposal.source) {
    case "profile":
      return `${proposal.matched_count}/${proposal.total_fields} canonical fields matched · learned profile`;
    case "crosswalk":
      return `${proposal.matched_count}/${proposal.total_fields} canonical fields matched · crosswalk`;
    case "claude":
      return `No crosswalk match — Claude suggests ${proposal.schema_name}. Check it before ingesting.`;
  }
}
