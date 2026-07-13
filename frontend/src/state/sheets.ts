/**
 * The sheet-question panel's pure pre-selection/gating/payload/copy logic
 * (SHEET-01/05, D-11-06; layout verdicts per 12-UI-SPEC Discretion §1) --
 * a module with NO React import, so vitest covers it under the `node` test
 * environment, mirroring `state/dateFormat.ts`'s own "logic is tested,
 * rendering is gsd-ui-checker-validated" split. ALL panel decisions live
 * here; `SheetQuestionPanel` holds only the answers map and the submitting
 * flag.
 *
 * Five invariants this module enforces structurally:
 * - `proposals: []` IS the propose-skip signal (11-07's ruling) -- the tick
 *   state reads the proposal LIST, never `proposed_schema`, so the human's
 *   own Upload pick can fill the Select on a skip-proposed sheet WITHOUT
 *   the tool ticking it for them (D-11-16).
 * - A tie pre-fills NOTHING, and the Upload dropdown does not get to settle
 *   it either: a stale default is not evidence, and letting it break a
 *   genuine tie would be exactly the silent guess D-11-06 forbids.
 * - Unreadability is the VERDICT's, never the status's: only a sheet Claude
 *   read as `not_a_table` / `wide_matrix` / `multiple_tables` hides its
 *   headers and its Schema control. A `key_value` sheet is READABLE (its
 *   labels are its headers) and an `unknown` sheet is ANSWERABLE -- ticking
 *   it raises its own layout question in Review. Collapsing either into
 *   "unreadable" would rebuild the dead end D-12-15 just killed.
 * - Amber keys ONLY off the server-sent `needs_confirmation` flag (or the
 *   unknown state, which has no confidence at all) -- the client renders
 *   gates, it does not set them (T-12-20, the same division
 *   `FieldMapping.needs_confirmation` draws).
 * - `submitBlockedReason` mirrors the server's own fail-closed 422s (an
 *   empty selection, T-11-22's manifest validation) -- it never relies on
 *   the server alone to catch an empty or Schema-less submission.
 */

import type {
  LayoutKind,
  SheetOut,
  SheetQuestionResponse,
  SheetResolveRequest,
  SheetSchemaProposal,
} from "../lib/types";

/** One sheet's answer-in-progress: the tick, the per-sheet Schema, and the
 * ask-me-instead disagree flag (12-UI-SPEC Discretion §2). The panel holds a
 * `SheetChoice[]` in local state; every derivation over it lives here. */
export interface SheetChoice {
  sheetName: string;
  ticked: boolean;
  schemaName: string | null;
  askLayout: boolean;
}

/** Whether this sheet arrives pre-ticked (D-11-06, verbatim): a proposal
 * exists AND the structural gate passed. A gate-failed sheet (`drawing_only`
 * / `unsupported_shape` / `header_uncertain` / `layout_unknown`) arrives
 * UNTICKED however well it scores -- meridian's LEGEND honestly scores 1/7
 * (D-11-24) and no coverage threshold exists to suppress it, so the visible
 * coverage number is the only thing telling the human it is a legend. It
 * stays present and tickable: if the human insists, the failure surfaces as
 * that member's own structural question (SHEET-04: marked, never dropped,
 * never disabled away). A `key_value` sheet with matched labels is
 * `status: "ok"` and arrives TICKED -- readable is readable. */
function _isPreTicked(sheet: SheetOut): boolean {
  return sheet.status === "ok" && sheet.proposals.length > 0;
}

/** The verdict kinds the tool honestly cannot read -- and ONLY those.
 * `key_value` is deliberately absent (the phase's point: it is READ now,
 * un-pivoted by Python per Claude's confirmed blocks) and so is `unknown`
 * (answerable, not unreadable -- the human gets asked, never dead-ended). */
const _UNREADABLE_KINDS: ReadonlySet<LayoutKind> = new Set([
  "not_a_table",
  "wide_matrix",
  "multiple_tables",
]);

/** A sheet whose layout VERDICT says there is nothing here this tool can
 * read as a table: `not_a_table` (a banner/chart/notes sheet) or a matrix /
 * multiple-tables layout v1 does not reshape.
 *
 * Re-keyed from `status === "unsupported_shape"` to `layout.kind` in Phase
 * 12: the status keeps GATE semantics ("can this sheet be read?"), the kind
 * names WHAT the sheet is, and only the kind can tell a key-value sheet
 * (readable now) or an unknown one (answerable now) apart from a genuine
 * refusal. A null layout -- a stale pre-verdict response -- is never
 * unreadable: with no verdict there is no refusal to render, and the
 * fail-closed server gates cover the human's insistence. */
export function isUnreadableShape(sheet: SheetOut): boolean {
  return sheet.layout !== null && _UNREADABLE_KINDS.has(sheet.layout.kind);
}

/** Whether to render the detected headers/labels chip list. Never for a
 * sheet whose VERDICT is unreadable: on a grid that is not a table, any
 * "header" would be a cell VALUE dressed as a column -- that is how a
 * patient's name (`TAYLOR, James`) once reached a curator as a column
 * header. That leak is closed at the SOURCE now: `describe_workbook` keys
 * every manifest header off the judge's verdict (12-04), so a `key_value`
 * sheet's headers ARE its labels and an unjudged sheet sends `headers: []`.
 * This predicate remains the second lock on the same door -- a stale or
 * replayed response cannot reopen it. */
export function showsDetectedHeaders(sheet: SheetOut): boolean {
  return !isUnreadableShape(sheet) && sheet.headers.length > 0;
}

/** The chip list's caption: a `key_value` sheet's chips are its LABELS --
 * the field names Claude read down the side -- and calling them "headers"
 * would misdescribe the very thing the curator is checking (12-UI-SPEC
 * Copywriting Contract). */
export function detectedHeadersCaption(sheet: SheetOut): string {
  return sheet.layout?.kind === "key_value" ? "Detected labels" : "Detected headers";
}

/** Whether to render the per-sheet Schema `Select`. Never for a sheet whose
 * VERDICT is unreadable: choosing a Schema for it would answer a question
 * the tool has just said it cannot ask. Every other sheet keeps the control
 * -- including a `key_value` sheet (it maps like any table once confirmed)
 * and an `unknown` one (a ticked unknown sheet still needs its Schema
 * chosen NOW; mapping runs after its layout question resolves). */
export function showsSchemaSelect(sheet: SheetOut): boolean {
  return !isUnreadableShape(sheet);
}

/** Which Schema this sheet's Select arrives pre-filled with. A tie leaves
 * it EMPTY -- hard short-circuit, above every fallback. An unreadable
 * VERDICT leaves it empty too, and the `defaultSchema` fallback below is
 * exactly why that has to be said HERE as well as on the wire:
 * `proposed_schema ?? defaultSchema` would cheerfully re-fill from the
 * Upload dropdown the very Schema `wire.py::_pre_selection` just refused to
 * send. Otherwise the server's own precedence (scorer's top proposal -> the
 * human's Upload pick -> nothing) is trusted first, with `defaultSchema` as
 * the client-side D-11-16 fallback for responses that predate the
 * server-side default. */
function _preSelectedSchema(sheet: SheetOut, defaultSchema: string | null): string | null {
  if (sheet.tie) return null;
  if (isUnreadableShape(sheet)) return null;
  return sheet.proposed_schema ?? defaultSchema;
}

/** Derives the panel's initial `SheetChoice[]` from the wire manifest, in
 * manifest order -- the four pre-selection states of D-11-06 exactly:
 * proposal -> ticked + that Schema; zero coverage -> unticked + skip; tie ->
 * ticked + EMPTY Select; gate-failed -> unticked but still selectable.
 * `askLayout` arrives false everywhere: disagreement is the human's move,
 * never a default. */
export function initialSelections(
  response: SheetQuestionResponse,
  defaultSchema: string | null
): SheetChoice[] {
  return response.sheets.map((sheet) => ({
    sheetName: sheet.sheet_name,
    ticked: _isPreTicked(sheet),
    schemaName: _preSelectedSchema(sheet, defaultSchema),
    askLayout: false,
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
 * chooses among options the server already offered). `ask_layout` rides a
 * selection ONLY when the human disagreed with that sheet's verdict
 * (12-UI-SPEC Discretion §2) -- omitted otherwise, never sent as `false`,
 * so an undisputed payload stays byte-identical to Phase 11's. */
export function toResolvePayload(uploadToken: string, selections: SheetChoice[]): SheetResolveRequest {
  return {
    upload_token: uploadToken,
    selections: selections
      .filter((choice) => choice.ticked && choice.schemaName !== null)
      .map((choice) => ({
        sheet_name: choice.sheetName,
        schema_name: choice.schemaName as string,
        ...(choice.askLayout ? { ask_layout: true } : {}),
      })),
  };
}

/** The verdict-kind phrases of the 12-UI-SPEC Copywriting Contract -- one
 * vocabulary for the sheet cards and the hint panel, so the two surfaces can
 * never drift apart on what a kind is CALLED. */
const _KIND_PHRASE: Record<Exclude<LayoutKind, "unknown">, string> = {
  row_per_record: "one row per record",
  key_value: "labels down the side",
  wide_matrix: "a matrix layout",
  multiple_tables: "multiple tables on one sheet",
  not_a_table: "not a table",
};

/** One sheet card's layout line, in parts (12-UI-SPEC Copywriting Contract,
 * verbatim when reassembled as `lead + kindPhrase + rest + confidence +
 * trailer`). The parts exist only so the panel can render the kind phrase
 * strong and the confidence mono/tabular-nums without composing any copy
 * itself. `judged: false` is the `unknown` line -- no reasoning and no
 * confidence, because there is none, and printing "0% confident" would be
 * theatre. `amber` is the server-sent `needs_confirmation` gate (or the
 * unknown state) -- never a client-side confidence threshold (T-12-20). */
export type LayoutLine =
  | {
      judged: true;
      lead: string;
      kindPhrase: string;
      rest: string;
      confidence: string;
      trailer: string;
      amber: boolean;
    }
  | { judged: false; text: string; amber: true };

/** The per-sheet layout verdict line, or `null` when no verdict exists at
 * all (a stale pre-verdict response has no claim to render -- and no line
 * beats a fabricated one, D-12-14). */
export function layoutLine(sheet: SheetOut): LayoutLine | null {
  const layout = sheet.layout;
  if (layout === null) return null;
  if (layout.kind === "unknown") {
    return {
      judged: false,
      amber: true,
      text: "The tool couldn't judge this sheet's layout. Tick it and you'll be asked about it in Review before anything is mapped.",
    };
  }
  const confidence = `${Math.round(layout.confidence * 100)}% confident`;
  const amber = layout.needs_confirmation;
  const kindPhrase = _KIND_PHRASE[layout.kind];
  switch (layout.kind) {
    case "key_value": {
      const records =
        layout.record_count !== null && layout.record_count > 1
          ? `${layout.record_count} records, one per value column`
          : "one record";
      return {
        judged: true,
        lead: "Read as: ",
        kindPhrase,
        rest: ` — ${records}. ${layout.reasoning} · `,
        confidence,
        trailer: "",
        amber,
      };
    }
    case "wide_matrix":
    case "multiple_tables":
      return {
        judged: true,
        lead: "Read as: ",
        kindPhrase,
        rest: ` — ${layout.reasoning} · `,
        confidence,
        trailer: ". The tool can't read this layout yet.",
        amber,
      };
    default:
      // row_per_record and not_a_table share the plain contract form.
      return {
        judged: true,
        lead: "Read as: ",
        kindPhrase,
        rest: ` — ${layout.reasoning} · `,
        confidence,
        trailer: "",
        amber,
      };
  }
}

/** The honest line shown IN PLACE OF the headers and the Schema control for
 * a sheet whose VERDICT is unreadable -- per kind, per the Copywriting
 * Contract, replacing Phase 11's single `UNREADABLE_SHAPE_LINE` (whose
 * "un-pivoting is PARSE-V2-01, deliberately not v1" story is now history:
 * the key-value half of that limit is exactly what this phase shipped, so
 * only the three genuinely unreadable kinds refuse, and each names its own
 * limit instead of one line claiming them all).
 *
 * The sheet stays visible and stays tickable regardless: if the human
 * insists, the mapping finds nothing, every field goes amber, and the
 * confirm gate blocks the export. Fail-closed already covers the
 * insistence. `null` for every readable or answerable sheet. */
export function refusalLine(sheet: SheetOut): string | null {
  const layout = sheet.layout;
  if (layout === null || !isUnreadableShape(sheet)) return null;
  switch (layout.kind) {
    case "not_a_table":
      return `Claude read this sheet as not a table — ${layout.reasoning}. There are no headers to show and nothing to map. Proposed: skip this sheet.`;
    case "wide_matrix":
      return "This sheet is laid out as a matrix, and the tool can't read that layout yet — reshape it to one row per record, or skip it.";
    case "multiple_tables":
      return "This sheet is laid out as multiple tables, and the tool can't read that layout yet — reshape it to one row per record, or skip it.";
    default:
      return null;
  }
}

/** True only when EVERY sheet's verdict is `unknown` -- the judge was
 * unreachable, a first-class state, not an edge case (D-12-16). Drives the
 * ONE workbook-level amber notice; the cards themselves stay quiet, because
 * repeating the judge-failure story eight times tells the human nothing the
 * notice did not. A null layout is NOT unknown -- a stale response is not a
 * judge failure -- and an empty manifest has no story to tell. */
export function allUnknown(sheets: SheetOut[]): boolean {
  return sheets.length > 0 && sheets.every((sheet) => sheet.layout?.kind === "unknown");
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
