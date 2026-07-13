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
  KeyValueBlockIn,
  LayoutKind,
  SheetLayoutIn,
  SheetOut,
  SheetQuestionResponse,
  SheetResolveRequest,
  SheetSchemaProposal,
  StructuralHintIn,
} from "../lib/types";

/** One sheet's answer-in-progress: the tick, the per-sheet Schema, and the
 * ask-me-instead disagree flag (12-UI-SPEC Discretion §2). The panel holds a
 * `SheetChoice[]` in local state; every derivation over it lives here. */
export interface SheetChoice {
  sheetName: string;
  /** Which table OF that sheet, when the sheet stacks several. `null` on an
   * ordinary one-table sheet. The sheet name stopped being an identity the
   * moment one worksheet could yield four datasets with four different header
   * rows — every lookup here keys on `sheetKey`, never on the name alone. */
  tableIndex: number | null;
  ticked: boolean;
  schemaName: string | null;
  askLayout: boolean;
}

/** The identity of one dataset on this screen: the sheet, plus its table when
 * the sheet holds more than one. Mirrors `routes/sheets.py::_selection_key`. */
export function sheetKey(item: { sheet_name: string; table_index?: number | null }): string;
export function sheetKey(item: SheetChoice): string;
export function sheetKey(item: { sheet_name?: string; sheetName?: string; table_index?: number | null; tableIndex?: number | null }): string {
  const name = item.sheet_name ?? item.sheetName ?? "";
  const table = item.table_index ?? item.tableIndex ?? null;
  return table === null ? name : `${name}#${table}`;
}

/** What to call this dataset on screen. Four tables of `Lab Results` must not
 * all read as `Lab Results` — and they must not read as row ranges either: the
 * curator knows this table as `Renal Function`, which is what the sheet calls
 * it. The row range is how they FIND it, not what they call it, so it goes
 * beside the name (`sheetSubtitle`), not in place of it. */
export function sheetTitle(sheet: SheetOut): string {
  const name = sheet.table_title ?? sheet.table_label ?? null;
  return name === null ? sheet.sheet_name : `${sheet.sheet_name} — ${name}`;
}

/** Where in the sheet this table is — shown only when the table has a name of
 * its own, since otherwise the name IS the row range and repeating it is noise. */
export function sheetSubtitle(sheet: SheetOut): string | null {
  return sheet.table_title && sheet.table_label ? sheet.table_label : null;
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
  // An EMPTY sheet is unreadable whatever the verdict calls it, and unlike an
  // `unknown` one it is NOT answerable: no answer a human could give would put
  // rows into a sheet that has none. So it takes the refusal treatment -- no
  // headers, no Schema select, one plain line -- rather than being offered a
  // question it is impossible to answer.
  if (sheet.row_count === 0) return true;
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
  if (isUnreadableShape(sheet) || sheet.headers.length === 0) return false;
  // The coverage table below already prints EVERY column of the file -- the ones
  // a field claimed, and the ones no field did -- beside the schema field each
  // one answers. The chips then said the same words a second time, with less
  // information (a bare `Tset` tells the curator nothing; `Tset` sitting in the
  // "no field in this Schema" row tells them what to do about it). So the chips
  // are shown ONLY when there is no table: a sheet no Schema scored at all still
  // has to show what is in it, or the curator is deciding blind.
  return sheet.proposals.length === 0;
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
    tableIndex: sheet.table_index ?? null,
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
        ...(choice.tableIndex === null ? {} : { table_index: choice.tableIndex }),
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
  // An EMPTY sheet is its own answer, said in the first four words — and said
  // whatever verdict came back for it, including no verdict at all. Claude's
  // reasoning for an empty sheet is technically correct and useless to read
  // ("Sheet reports 0 rows x 0 cols with no columns; there is no content to
  // interpret as any tabular structure"): a curator scanning eight sheets needs
  // to know instantly which one not to tick, not to parse a sentence.
  if (sheet.row_count === 0) {
    return "This sheet is empty — there is nothing to ingest. Proposed: skip it.";
  }

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

/** One sheet card's badge, or `null` when there is nothing to flag. The
 * TONE carries the meaning (12-UI-SPEC §Color): `secondary` is a readable,
 * positive fact (a key-value sheet is neither an alert nor an absence);
 * `amber` is "the tool is not sure, a human must act" (an unknown layout,
 * an unclear header); `muted` is a structural fact, not a warning to act on
 * (not a table, a layout v1 cannot read). The verdict's badge outranks the
 * status's -- the kind names WHAT the sheet is, the status only whether it
 * can be read -- but a stale `layout_unknown` status with no layout still
 * flags amber: the gate is the server's either way. */
export interface SheetBadgeSpec {
  label: string;
  tone: "secondary" | "amber" | "muted";
}

export function sheetBadge(sheet: SheetOut): SheetBadgeSpec | null {
  const kind = sheet.layout?.kind ?? null;
  // Empty outranks every other verdict: it is the one fact that settles the
  // sheet outright, and the curator should not have to read a sentence to
  // learn it. Muted, because an empty sheet is an absence, not a problem.
  if (sheet.row_count === 0) return { label: "empty", tone: "muted" };
  if (kind === "key_value") return { label: "labels down the side", tone: "secondary" };
  if (kind === "unknown" || sheet.status === "layout_unknown") {
    return { label: "layout unknown", tone: "amber" };
  }
  if (kind === "not_a_table") return { label: "not a table", tone: "muted" };
  if (kind === "wide_matrix" || kind === "multiple_tables") {
    return { label: "can't read this layout yet", tone: "muted" };
  }
  switch (sheet.status) {
    case "drawing_only":
      return { label: "no table found", tone: "muted" };
    case "unsupported_shape":
      return { label: "unsupported shape", tone: "muted" };
    case "header_uncertain":
      return { label: "header unclear", tone: "amber" };
    default:
      return null;
  }
}

/** Whether this sheet's layout line carries the "answer it yourself"
 * disagree action -- EVERY judged sheet, INCLUDING a confident
 * `row_per_record` (12-UI-SPEC Discretion §2): under `headers_only` the
 * judge is provably weakest exactly where a wrong `row_per_record` re-opens
 * the D-12-12 leak, and D-12-08 makes the human the ONLY check. Not for
 * `unknown` (that sheet already routes to the layout question -- its line
 * says so) and not for a null layout (no verdict, nothing to disagree
 * with). */
export function showsAskLayoutAction(sheet: SheetOut): boolean {
  return sheet.layout !== null && sheet.layout.kind !== "unknown";
}

/** The disagree text button on a judged sheet's layout line (Copywriting
 * Contract, verbatim). */
export const LAYOUT_DISAGREE_ACTION = "Not right? Answer the layout yourself";

/** The engaged state that REPLACES the layout line once the human has
 * disagreed -- rendered with the undo action beside it. */
export const LAYOUT_DISAGREE_ENGAGED_LINE =
  "You'll be asked about this sheet's layout in Review.";

/** The engaged state's undo action -- re-accepting Claude's read. */
export const LAYOUT_DISAGREE_UNDO_ACTION = "Use Claude's read instead";

/** The ONE workbook-level amber notice for the all-unknown state -- the
 * judge-failure story told once, never once per card. */
export const ALL_UNKNOWN_NOTICE =
  "The layout judge couldn't run, so no sheet's layout is known. Each ticked sheet will ask about its layout in Review before anything is mapped.";

/** True only when EVERY sheet's verdict is `unknown` -- the judge was
 * unreachable, a first-class state, not an edge case (D-12-16). Drives the
 * ONE workbook-level amber notice; the cards themselves stay quiet, because
 * repeating the judge-failure story eight times tells the human nothing the
 * notice did not. A null layout is NOT unknown -- a stale response is not a
 * judge failure -- and an empty manifest has no story to tell. */
export function allUnknown(sheets: SheetOut[]): boolean {
  return sheets.length > 0 && sheets.every((sheet) => sheet.layout?.kind === "unknown");
}

// --- The StructuralHintPanel's layout-question derivations (12-UI-SPEC
// Discretion §3: one answer surface, upgraded once, reached from both the
// single-sheet path and the sheet screen's ask_layout disagree path). ------

const _LAYOUT_KINDS: readonly LayoutKind[] = [
  "row_per_record",
  "key_value",
  "wide_matrix",
  "multiple_tables",
  "not_a_table",
  "unknown",
];

function _asNumberOrNull(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function _asBlock(value: unknown): KeyValueBlockIn | null {
  if (typeof value !== "object" || value === null) return null;
  const block = value as Record<string, unknown>;
  const labelColumn = block["label_column"];
  const valueColumns = block["value_columns"];
  const firstRow = block["first_row"];
  const lastRow = block["last_row"];
  if (
    typeof labelColumn !== "number" ||
    !Array.isArray(valueColumns) ||
    !valueColumns.every((column): column is number => typeof column === "number") ||
    typeof firstRow !== "number" ||
    typeof lastRow !== "number"
  ) {
    return null;
  }
  return {
    label_column: labelColumn,
    value_columns: valueColumns,
    first_row: firstRow,
    last_row: lastRow,
  };
}

/** Reads the layout VERDICT off a `StructureQuestion.proposal` wire dict --
 * `service.layout_question_for` sends the verdict riding `proposal.layout`
 * intact, blocks and indices included, because the blocks are the
 * un-pivot's ONLY input when the human confirms "labels down the side".
 * A non-null return is what makes a question a LAYOUT question -- the same
 * derive-controls-from-non-null-proposal-fields pattern the panel's other
 * controls already follow, never `unsure_about`'s free text. Defensive on
 * every field: an invented kind or a malformed block parses to `null`/
 * dropped, never a claim the wire vocabulary cannot make. */
export function proposalLayout(proposal: Record<string, unknown> | null): SheetLayoutIn | null {
  if (proposal === null) return null;
  const raw = proposal["layout"];
  if (typeof raw !== "object" || raw === null) return null;
  const layout = raw as Record<string, unknown>;
  const kind = layout["kind"];
  if (typeof kind !== "string" || !(_LAYOUT_KINDS as readonly string[]).includes(kind)) {
    return null;
  }
  const blocks = Array.isArray(layout["key_value_blocks"])
    ? layout["key_value_blocks"]
        .map(_asBlock)
        .filter((block): block is KeyValueBlockIn => block !== null)
    : [];
  return {
    kind: kind as LayoutKind,
    confidence: typeof layout["confidence"] === "number" ? layout["confidence"] : 0,
    reasoning: typeof layout["reasoning"] === "string" ? layout["reasoning"] : "",
    header_row_index: _asNumberOrNull(layout["header_row_index"]),
    first_data_row: _asNumberOrNull(layout["first_data_row"]),
    last_data_row: _asNumberOrNull(layout["last_data_row"]),
    key_value_blocks: blocks,
    one_record_per_value_column: layout["one_record_per_value_column"] === true,
  };
}

/** How many records a key-value verdict yields -- the client-side mirror of
 * `SheetLayout.record_count` (the wire dict carries the FIELDS, not the
 * property): one per value column when Claude proposed that reading, else
 * one record for the whole sheet. */
function _proposedRecordCount(layout: SheetLayoutIn): number {
  if (layout.one_record_per_value_column) {
    return (layout.key_value_blocks ?? []).reduce(
      (sum, block) => sum + block.value_columns.length,
      0
    );
  }
  return 1;
}

/** The hint panel's verdict block, in parts (Copywriting Contract,
 * verbatim when reassembled as `lead + kindPhrase + rest + confidence +
 * trailer`) -- same part scheme as `LayoutLine`, so the panel renders the
 * kind phrase strong and the confidence mono without composing copy.
 * `judged: false` is the honest no-verdict line -- an `unknown` verdict or
 * no verdict at all say the same thing, with no percentage theatre. */
export type HintVerdictLine =
  | { judged: true; lead: string; kindPhrase: string; rest: string; confidence: string; trailer: string }
  | { judged: false; text: string };

export function hintVerdictLine(layout: SheetLayoutIn | null): HintVerdictLine {
  if (layout === null || layout.kind === "unknown") {
    return { judged: false, text: "The tool couldn't judge this sheet's layout on its own." };
  }
  const confidence = `${Math.round(layout.confidence * 100)}% confident`;
  const reasoning = layout.reasoning ?? "";
  const kindPhrase = _KIND_PHRASE[layout.kind];
  if (layout.kind === "key_value") {
    return {
      judged: true,
      lead: "Claude read this sheet as ",
      kindPhrase,
      rest: ` — ${_proposedRecordCount(layout)} record(s). ${reasoning} (`,
      confidence,
      trailer: ")",
    };
  }
  return {
    judged: true,
    lead: "Claude read this sheet as ",
    kindPhrase,
    rest: `. ${reasoning} (`,
    confidence,
    trailer: ")",
  };
}

/** The "Labels found" chips -- the curator's CHECKING material, read from
 * the evidence grid per Claude's block indices exactly as Python's un-pivot
 * would read them: label column only, block order, `first_row..last_row`
 * clamped to the evidence actually sent, blanks skipped. `Patient Name,
 * MRN, Accession #` reading as field names IS the verdict being right; a
 * `TAYLOR, James` among them IS it being wrong -- this is how the human
 * checks without opening Excel. Never a value column (D-12-12). */
export function hintLabels(layout: SheetLayoutIn | null, evidenceRows: string[][]): string[] {
  if (layout === null || layout.kind !== "key_value") return [];
  const labels: string[] = [];
  for (const block of layout.key_value_blocks ?? []) {
    const lastRow = Math.min(block.last_row, evidenceRows.length - 1);
    for (let row = block.first_row; row <= lastRow; row++) {
      const label = (evidenceRows[row]?.[block.label_column] ?? "").trim();
      if (label !== "") labels.push(label);
    }
  }
  return labels;
}

/** The human's two possible layout answers -- the panel's option buttons. */
export type LayoutAnswer = "key_value" | "row_per_record";

/** "How is this sheet laid out?" (Copywriting Contract, verbatim). */
export const HINT_LAYOUT_QUESTION_LABEL = "How is this sheet laid out?";

/** The always-offered ordinary-table option -- selecting it reveals the
 * existing header-row control. */
export const ROW_PER_RECORD_OPTION_LABEL = "One row per record";

/** Submit blocked until an option is chosen -- the client-side mirror of
 * never guessing silently. */
export const HINT_LAYOUT_BLOCKED_LINE = "Choose how the sheet is laid out.";

/** The honest limit line when NO key-value proposal exists: without
 * Claude's blocks the tool cannot un-pivot (a kind without indices is
 * un-actionable, and the block editor is deferred), so the only offered
 * answer is "one row per record" -- and if the sheet is not that either,
 * the tool says so instead of guessing. */
export const HINT_NO_KEY_VALUE_LIMIT_LINE =
  "If this sheet is a labels-down-the-side layout, the tool needs Claude's read to find the labels — it couldn't get one this time. If it isn't one row per record either, reshape it to one row per record or try a different file.";

/** Which options the layout question offers, and which arrives selected
 * (12-UI-SPEC Discretion §3): the key-value option ONLY when the proposal
 * carries blocks, pre-selected when it does; a low-confidence
 * `row_per_record` pre-selects "One row per record" with its header row
 * pre-filled (the off-by-one fix path); an `unknown` verdict pre-selects
 * NOTHING -- the human chooses, or nothing proceeds. A confident
 * `row_per_record` never reaches this panel at all (D-12-15). */
export interface HintLayoutOptions {
  keyValueOptionLabel: string | null;
  preSelected: LayoutAnswer | null;
  headerRowPrefill: number | null;
}

export function hintLayoutOptions(layout: SheetLayoutIn | null): HintLayoutOptions {
  const hasBlocks =
    layout !== null && layout.kind === "key_value" && (layout.key_value_blocks ?? []).length > 0;
  const keyValueOptionLabel = hasBlocks
    ? `Labels down the side — ${_proposedRecordCount(layout)} record(s)`
    : null;
  const preSelected: LayoutAnswer | null = hasBlocks
    ? "key_value"
    : layout?.kind === "row_per_record"
      ? "row_per_record"
      : null;
  return {
    keyValueOptionLabel,
    preSelected,
    headerRowPrefill: layout?.header_row_index ?? null,
  };
}

/** Builds the `StructuralHintIn` the layout answer posts -- BOTH forms
 * exactly as 12-05 pinned them at the HTTP boundary
 * (`tests/api/test_structural_hint_context.py`):
 *
 * - "Labels down the side" submits CONFIRMATION of Claude's blocks via
 *   `hint.layout` -- the proposal's own `key_value_blocks` verbatim, never
 *   indices the browser invented (the human can accept or reject the block
 *   map, never edit it).
 * - "One row per record" submits `{kind, header_row_index}` -- the human's
 *   header row, from the number input or the grid row-click, which sets
 *   ONLY this field.
 *
 * Confidence is 1.0 with the curator's own provenance line, because a
 * human's confirmation is the one thing this tool treats as certain. An
 * unanswered header row and an unknown sheet name are OMITTED, mirroring
 * `buildHintPayload`'s only-what-the-human-decided discipline. */
export function toLayoutAnswerPayload(
  answer: LayoutAnswer,
  layout: SheetLayoutIn | null,
  headerRowIndex: number | undefined,
  sheetName: string | null
): StructuralHintIn {
  const hint: StructuralHintIn = {};
  if (sheetName !== null) hint.sheet_name = sheetName;
  if (answer === "key_value") {
    const confirmed: SheetLayoutIn = {
      kind: "key_value",
      confidence: 1.0,
      reasoning: "confirmed by the curator",
      key_value_blocks: layout?.key_value_blocks ?? [],
    };
    if (layout?.one_record_per_value_column) confirmed.one_record_per_value_column = true;
    hint.layout = confirmed;
    return hint;
  }
  const confirmed: SheetLayoutIn = {
    kind: "row_per_record",
    confidence: 1.0,
    reasoning: "confirmed by the curator",
  };
  if (headerRowIndex !== undefined) confirmed.header_row_index = headerRowIndex;
  hint.layout = confirmed;
  return hint;
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

/** ONE sentence naming the PRINCIPLE the Schema was chosen by, and the actual
 * evidence behind it — so the curator can judge the proposal rather than take
 * it on trust. A coverage score says WHAT the tool concluded; this says WHY,
 * and the two are not the same thing.
 *
 * The three arms are the escalation ladder itself (learned profile -> crosswalk
 * -> Claude), and they are deliberately NOT interchangeable in tone: the first
 * is remembered, the second is looked up, and the third is a guess with nothing
 * behind it. A sentence that made all three sound equally confident would be
 * the tool lying about how much it knows.
 *
 * `runnerUp` is the next-best proposal, when there is one. It is what turns
 * "5/6 matched" from a number into a decision: 5/6 against a runner-up of 2/7
 * is a clear win; 5/6 against 5/6 is a coin toss the human must settle. */
export function whyThisSchema(
  proposal: SheetSchemaProposal,
  runnerUp: SheetSchemaProposal | null
): string {
  const margin =
    runnerUp !== null
      ? ` — more than any other Schema (${runnerUp.schema_name} matched ${runnerUp.matched_count}/${runnerUp.total_fields})`
      : " — no other Schema matched anything";

  // The Schema is NAMED first, and only then referred to as "its". The sentence
  // sits under a coverage line and above a table that both talk about the same
  // Schema without ever saying which -- so on its own it read as though it were
  // explaining the file, not the choice.
  switch (proposal.source) {
    case "profile":
      return `Schema ${proposal.schema_name} was chosen because these exact columns were mapped to it before and a human confirmed that mapping — this is remembered, not guessed.`;
    case "crosswalk":
      return `Schema ${proposal.schema_name} was chosen because ${proposal.matched_count} of its ${proposal.total_fields} fields recognise a column header here by a spelling the crosswalk already knows (${proposal.matched
        .slice(0, 3)
        .map((pair) => `“${pair.header}” → ${pair.field}`)
        .join(", ")})${margin}.`;
    case "claude":
      return `Schema ${proposal.schema_name} was chosen by Claude reading the column headers alone, because no header matched a spelling any Schema knows — there is no evidence behind this one, so check it against the file before ingesting.`;
  }
}
