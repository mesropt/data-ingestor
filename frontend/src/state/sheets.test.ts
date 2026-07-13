import { describe, expect, it } from "vitest";

import {
  ALL_UNKNOWN_NOTICE,
  HINT_LAYOUT_BLOCKED_LINE,
  HINT_LAYOUT_QUESTION_LABEL,
  HINT_NO_KEY_VALUE_LIMIT_LINE,
  LAYOUT_DISAGREE_ACTION,
  LAYOUT_DISAGREE_ENGAGED_LINE,
  LAYOUT_DISAGREE_UNDO_ACTION,
  ROW_PER_RECORD_OPTION_LABEL,
  allUnknown,
  coverageLine,
  detectedHeadersCaption,
  hintLabels,
  hintLayoutOptions,
  hintVerdictLine,
  initialSelections,
  isUnreadableShape,
  layoutLine,
  proposalLayout,
  refusalLine,
  sheetBadge,
  showsAskLayoutAction,
  showsDetectedHeaders,
  showsSchemaSelect,
  submitBlockedReason,
  toLayoutAnswerPayload,
  toResolvePayload,
} from "./sheets";
import type { HintVerdictLine, LayoutLine, SheetChoice } from "./sheets";
import type {
  SheetLayoutIn,
  SheetLayoutOut,
  SheetOut,
  SheetQuestionResponse,
  SheetSchemaProposal,
} from "../lib/types";

/** A confident crosswalk proposal -- the DATA-sheet case (meridian 7/7,
 * zephyr 6/7). `matched` is pairs, not a bare count: the human checks the
 * tool's reasoning and cannot check what is not shown (D-11-03). */
const crosswalkProposal: SheetSchemaProposal = {
  schema_name: "assay-potency",
  matched: [
    { field: "compound_id", header: "Cmpd ID" },
    { field: "value", header: "IC50 (uM)" },
  ],
  uncovered: ["assay_date"],
  matched_count: 6,
  total_fields: 7,
  near_matches: [],
  source: "crosswalk",
  reason: null,
};

const profileProposal: SheetSchemaProposal = {
  ...crosswalkProposal,
  matched_count: 7,
  uncovered: [],
  source: "profile",
};

/** D-11-19's last-resort stage: by construction `matched == []` and a
 * `reason` INSTEAD of evidence -- the panel must label it as such, because
 * a human is entitled to know a proposal has nothing behind it. */
const claudeProposal: SheetSchemaProposal = {
  schema_name: "assay-potency",
  matched: [],
  uncovered: ["compound_id", "value", "unit"],
  matched_count: 0,
  total_fields: 3,
  near_matches: [],
  source: "claude",
  reason: "column names resemble potency readouts",
};

/** The judge's verdict as `api/wire.py::SheetLayoutOut` sends it -- no index
 * ever crosses to the browser (12-UI-SPEC Discretion §1). `needs_confirmation`
 * is the SERVER's gate, always beside the raw confidence. */
function verdict(overrides: Partial<SheetLayoutOut> = {}): SheetLayoutOut {
  return {
    kind: "row_per_record",
    confidence: 0.97,
    reasoning: "a header row of field names over homogeneous rows",
    record_count: null,
    needs_confirmation: false,
    ...overrides,
  };
}

function sheet(overrides: Partial<SheetOut>): SheetOut {
  return {
    sheet_name: "DATA",
    row_count: 12,
    headers: ["Cmpd ID", "IC50 (uM)"],
    column_signature: "sig-1",
    table_index: null,
    table_label: null,
      table_title: null,
    status: "ok",
    proposals: [crosswalkProposal],
    proposed_schema: "assay-potency",
    tie: false,
    layout: null,
    ...overrides,
  };
}

function question(sheets: SheetOut[]): SheetQuestionResponse {
  return { kind: "sheet_question", upload_token: "token-s", sheets };
}

/** Reassembles a judged layout line into the one string the Copywriting
 * Contract writes -- the parts exist only so the panel can render the kind
 * phrase strong and the confidence mono without composing copy itself. */
function fullLine(line: LayoutLine | null): string | null {
  if (line === null) return null;
  if (!line.judged) return line.text;
  return line.lead + line.kindPhrase + line.rest + line.confidence + line.trailer;
}

describe("initialSelections", () => {
  it("pre-ticks a sheet with a proposal and pre-selects that Schema (D-11-06: pre-fill, never auto-apply)", () => {
    const selections = initialSelections(question([sheet({})]), null);

    expect(selections).toEqual([
      { sheetName: "DATA", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
    ]);
  });

  it("pre-unticks a zero-coverage sheet -- `proposals == []` IS the propose-skip signal, never `proposed_schema`", () => {
    const skip = sheet({
      sheet_name: "Notes",
      proposals: [],
      proposed_schema: null,
    });

    const selections = initialSelections(question([skip]), null);

    expect(selections).toEqual([
      { sheetName: "Notes", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
    ]);
  });

  it("falls back to the Upload dropdown's Schema for the Select when the scorer proposed none (D-11-16) -- WITHOUT ticking the sheet", () => {
    const skip = sheet({ sheet_name: "Notes", proposals: [], proposed_schema: null });

    const selections = initialSelections(question([skip]), "assay-potency");

    expect(selections).toEqual([
      { sheetName: "Notes", tableIndex: null, ticked: false, schemaName: "assay-potency", askLayout: false },
    ]);
  });

  it("shows a tie AS a tie: ticked, but the Select left EMPTY -- the tool breaks ties for nobody", () => {
    const tied = sheet({
      proposals: [crosswalkProposal, { ...crosswalkProposal, schema_name: "assay-binding" }],
      proposed_schema: null,
      tie: true,
    });

    const selections = initialSelections(question([tied]), null);

    expect(selections).toEqual([
      { sheetName: "DATA", tableIndex: null, ticked: true, schemaName: null, askLayout: false },
    ]);
  });

  it("never lets the Upload dropdown settle a tie either -- a stale default is not evidence (11-07 hard short-circuit)", () => {
    const tied = sheet({
      proposals: [crosswalkProposal, { ...crosswalkProposal, schema_name: "assay-binding" }],
      proposed_schema: null,
      tie: true,
    });

    const selections = initialSelections(question([tied]), "assay-potency");

    expect(selections[0].schemaName).toBeNull();
    expect(selections[0].ticked).toBe(true);
  });

  it("pre-unticks a gate-failed sheet but keeps it present and selectable (SHEET-04: marked, never dropped)", () => {
    const drawing = sheet({
      sheet_name: "Chart",
      status: "drawing_only",
      proposals: [],
      proposed_schema: null,
    });
    const badShape = sheet({
      sheet_name: "Pivot",
      status: "unsupported_shape",
      proposals: [],
      proposed_schema: null,
    });

    const selections = initialSelections(question([drawing, badShape]), null);

    expect(selections).toEqual([
      { sheetName: "Chart", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
      { sheetName: "Pivot", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
    ]);
  });

  it("pre-unticks a header-uncertain sheet even when it carries a real proposal (meridian's LEGEND at 1/7) -- the coverage number, kept visible, is what tells the human it is a legend (D-11-24)", () => {
    const legend = sheet({
      sheet_name: "LEGEND",
      status: "header_uncertain",
      proposals: [
        {
          ...crosswalkProposal,
          matched: [{ field: "compound_id", header: "CMP" }],
          matched_count: 1,
          uncovered: ["assay_type", "value", "unit", "target", "n_replicates", "assay_date"],
        },
      ],
      proposed_schema: "assay-potency",
    });

    const selections = initialSelections(question([legend]), null);

    // Unticked (the gate failed), but the Select still pre-fills -- the human
    // may insist, and the failure then surfaces as that member's own question.
    expect(selections).toEqual([
      { sheetName: "LEGEND", tableIndex: null, ticked: false, schemaName: "assay-potency", askLayout: false },
    ]);
  });

  it("preserves the manifest's sheet order", () => {
    const selections = initialSelections(
      question([sheet({ sheet_name: "Week 1" }), sheet({ sheet_name: "Week 2" }), sheet({ sheet_name: "Week 3" })]),
      null
    );

    expect(selections.map((s) => s.sheetName)).toEqual(["Week 1", "Week 2", "Week 3"]);
  });
});

describe("isUnreadableShape is re-keyed on the VERDICT, not the status (12-UI-SPEC Discretion §1)", () => {
  it.each(["not_a_table", "wide_matrix", "multiple_tables"] as const)(
    "is true for a %s verdict -- the three layouts the tool honestly cannot read",
    (kind) => {
      const unreadable = sheet({
        status: "unsupported_shape",
        headers: [],
        proposals: [],
        proposed_schema: null,
        layout: verdict({ kind, confidence: 0.95, reasoning: "a banner and freeform notes" }),
      });

      expect(isUnreadableShape(unreadable)).toBe(true);
    }
  );

  it("key_value is never unreadable -- the phase's point: a key-value sheet is READ now, not refused", () => {
    const keyValue = sheet({
      layout: verdict({ kind: "key_value", confidence: 0.92, record_count: 1 }),
    });

    expect(isUnreadableShape(keyValue)).toBe(false);
  });

  it("unknown is not unreadable -- an unknown sheet is ANSWERABLE, and collapsing the two would rebuild the dead end D-12-15 just killed", () => {
    const unknown = sheet({
      status: "layout_unknown",
      headers: [],
      proposals: [],
      proposed_schema: null,
      layout: verdict({ kind: "unknown", confidence: 0.0, reasoning: "", needs_confirmation: true }),
    });

    expect(isUnreadableShape(unknown)).toBe(false);
  });

  it("is false for a confident row_per_record and for a null layout -- a stale pre-verdict response never renders as unreadable", () => {
    expect(isUnreadableShape(sheet({ layout: verdict({}) }))).toBe(false);
    expect(isUnreadableShape(sheet({ status: "unsupported_shape", layout: null }))).toBe(false);
  });
});

/** A verdict-refused sheet as the wire now sends it: the judge named the kind,
 * the backend suppressed the headers and proposals, and the status gate
 * closed. The panel must not invent any of them back. */
const unreadableShape = (): SheetOut =>
  sheet({
    sheet_name: "Summary",
    status: "unsupported_shape",
    headers: [],
    proposals: [],
    proposed_schema: null,
    layout: verdict({
      kind: "not_a_table",
      confidence: 0.96,
      reasoning: "a report banner and contact details, no data grid",
    }),
  });

describe("an unreadable VERDICT shows no answer, because the tool has none", () => {
  it("renders NO detected-headers list -- any header it named would be a cell value dressed as a column", () => {
    expect(showsDetectedHeaders(unreadableShape())).toBe(false);
  });

  it("renders NO Schema control -- a Schema for a sheet the tool has just proposed to skip is an answer to a question it cannot answer", () => {
    expect(showsSchemaSelect(unreadableShape())).toBe(false);
  });

  it("pre-selects NO Schema, and the Upload dropdown does not get to fill it either -- `proposed_schema ?? defaultSchema` is what put `assay-potency` on the screen", () => {
    const selections = initialSelections(question([unreadableShape()]), "assay-potency");

    expect(selections).toEqual([
      { sheetName: "Summary", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
    ]);
  });

  it("stays present and stays TICKABLE -- marked, never dropped, never disabled away (SHEET-04)", () => {
    const selections = initialSelections(
      question([unreadableShape(), sheet({ sheet_name: "IgE Results" })]),
      null
    );

    expect(selections.map((s) => s.sheetName)).toEqual(["Summary", "IgE Results"]);
    // Unticked is a PROPOSAL, not a lock: the human may still tick it, and
    // `submitBlockedReason` then makes them choose a Schema for it themselves.
    expect(
      submitBlockedReason([
        { sheetName: "Summary", tableIndex: null, ticked: true, schemaName: null, askLayout: false },
      ])
    ).toBe("Choose a Schema for 'Summary' — ties aren't broken automatically.");
  });
});

describe("a key_value sheet is a first-class readable citizen (D-12-12's UI half)", () => {
  const keyValue = () =>
    sheet({
      sheet_name: "Patient Info",
      headers: ["Name", "MRN", "Accession #"],
      layout: verdict({
        kind: "key_value",
        confidence: 0.92,
        reasoning: "field names down column A with one value beside each",
        record_count: 1,
        needs_confirmation: false,
      }),
    });

  it("shows its LABELS as the chip list -- the caption reads 'Detected labels', never 'Detected headers'", () => {
    expect(showsDetectedHeaders(keyValue())).toBe(true);
    expect(detectedHeadersCaption(keyValue())).toBe("Detected labels");
  });

  it("keeps the 'Detected headers' caption for every non-key-value sheet", () => {
    expect(detectedHeadersCaption(sheet({}))).toBe("Detected headers");
    expect(detectedHeadersCaption(sheet({ layout: verdict({}) }))).toBe("Detected headers");
  });

  it("keeps its Schema select", () => {
    expect(showsSchemaSelect(keyValue())).toBe(true);
  });

  it("arrives TICKED when its labels matched a Schema -- status ok + proposals exist, the unchanged _isPreTicked rule", () => {
    const selections = initialSelections(question([keyValue()]), null);

    expect(selections).toEqual([
      { sheetName: "Patient Info", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
    ]);
  });
});

describe("an unknown sheet is ANSWERABLE -- unticked, Schema still choosable", () => {
  const unknownSheet = () =>
    sheet({
      sheet_name: "Mystery",
      status: "layout_unknown",
      headers: [],
      proposals: [],
      proposed_schema: null,
      layout: verdict({ kind: "unknown", confidence: 0.0, reasoning: "", needs_confirmation: true }),
    });

  it("keeps its Schema select -- a ticked unknown sheet still needs its Schema chosen NOW; mapping runs after its layout question resolves", () => {
    expect(showsSchemaSelect(unknownSheet())).toBe(true);
  });

  it("arrives UNTICKED -- `layout_unknown` is not `ok`, so the unchanged _isPreTicked rule leaves it to the human", () => {
    const selections = initialSelections(question([unknownSheet()]), null);

    expect(selections[0].ticked).toBe(false);
  });

  it("pre-fills its Select from the Upload dropdown -- answerable, so rung-2 default treatment, exactly like header_uncertain", () => {
    const selections = initialSelections(question([unknownSheet()]), "assay-potency");

    expect(selections[0].schemaName).toBe("assay-potency");
  });
});

describe("layoutLine -- the Copywriting Contract, verbatim", () => {
  it("renders a row_per_record verdict as a quiet fact", () => {
    const line = layoutLine(sheet({ layout: verdict({}) }));

    expect(fullLine(line)).toBe(
      "Read as: one row per record — a header row of field names over homogeneous rows · 97% confident"
    );
    expect(line).toMatchObject({ judged: true, kindPhrase: "one row per record", amber: false });
  });

  it("renders a one-record key_value verdict", () => {
    const line = layoutLine(
      sheet({
        layout: verdict({
          kind: "key_value",
          confidence: 0.92,
          reasoning: "field names down column A with one value beside each",
          record_count: 1,
        }),
      })
    );

    expect(fullLine(line)).toBe(
      "Read as: labels down the side — one record. field names down column A with one value beside each · 92% confident"
    );
    expect(line).toMatchObject({ judged: true, kindPhrase: "labels down the side" });
  });

  it("renders the N-records key_value variant off record_count (one_record_per_value_column)", () => {
    const line = layoutLine(
      sheet({
        layout: verdict({
          kind: "key_value",
          confidence: 0.91,
          reasoning: "three visit columns beside one label column",
          record_count: 3,
        }),
      })
    );

    expect(fullLine(line)).toBe(
      "Read as: labels down the side — 3 records, one per value column. three visit columns beside one label column · 91% confident"
    );
  });

  it("renders a not_a_table verdict", () => {
    const line = layoutLine(
      sheet({
        layout: verdict({
          kind: "not_a_table",
          confidence: 0.96,
          reasoning: "a report banner and contact details, no data grid",
        }),
      })
    );

    expect(fullLine(line)).toBe(
      "Read as: not a table — a report banner and contact details, no data grid · 96% confident"
    );
  });

  it("renders wide_matrix and multiple_tables with the honest limit trailer", () => {
    const matrix = layoutLine(
      sheet({
        layout: verdict({ kind: "wide_matrix", confidence: 0.88, reasoning: "plates across the top", needs_confirmation: true }),
      })
    );
    const multiple = layoutLine(
      sheet({
        layout: verdict({ kind: "multiple_tables", confidence: 0.9, reasoning: "two grids separated by blank rows" }),
      })
    );

    expect(fullLine(matrix)).toBe(
      "Read as: a matrix layout — plates across the top · 88% confident. The tool can't read this layout yet."
    );
    expect(fullLine(multiple)).toBe(
      "Read as: multiple tables on one sheet — two grids separated by blank rows · 90% confident. The tool can't read this layout yet."
    );
  });

  it("renders the unknown line with NO confidence and NO reasoning -- printing '0% confident' would be theatre", () => {
    const line = layoutLine(
      sheet({
        layout: verdict({ kind: "unknown", confidence: 0.0, reasoning: "", needs_confirmation: true }),
      })
    );

    expect(fullLine(line)).toBe(
      "The tool couldn't judge this sheet's layout. Tick it and you'll be asked about it in Review before anything is mapped."
    );
    expect(fullLine(line)).not.toContain("%");
    expect(line).toMatchObject({ judged: false, amber: true });
  });

  it("keys amber ONLY off the server-sent needs_confirmation flag -- the client renders gates, it does not set them (T-12-20)", () => {
    const lowButUngated = layoutLine(
      sheet({ layout: verdict({ confidence: 0.55, needs_confirmation: false }) })
    );
    const gated = layoutLine(
      sheet({ layout: verdict({ confidence: 0.85, needs_confirmation: true }) })
    );

    expect(lowButUngated?.amber).toBe(false);
    expect(gated?.amber).toBe(true);
  });

  it("renders NO layout line at all for a null layout -- a stale pre-verdict response has no verdict to show", () => {
    expect(layoutLine(sheet({ layout: null }))).toBeNull();
  });
});

describe("refusalLine -- the per-kind honest refusals that replace UNREADABLE_SHAPE_LINE", () => {
  it("names the not_a_table verdict with Claude's own reasoning", () => {
    expect(refusalLine(unreadableShape())).toBe(
      "Claude read this sheet as not a table — a report banner and contact details, no data grid. There are no headers to show and nothing to map. Proposed: skip this sheet."
    );
  });

  it("names the matrix and multiple-tables limits without pretending they are absences", () => {
    const matrix = sheet({ layout: verdict({ kind: "wide_matrix", confidence: 0.9 }) });
    const multiple = sheet({ layout: verdict({ kind: "multiple_tables", confidence: 0.9 }) });

    expect(refusalLine(matrix)).toBe(
      "This sheet is laid out as a matrix, and the tool can't read that layout yet — reshape it to one row per record, or skip it."
    );
    expect(refusalLine(multiple)).toBe(
      "This sheet is laid out as multiple tables, and the tool can't read that layout yet — reshape it to one row per record, or skip it."
    );
  });

  it("returns null for every readable or answerable sheet -- key_value, unknown, row_per_record, and a null layout", () => {
    expect(refusalLine(sheet({ layout: verdict({ kind: "key_value", record_count: 1 }) }))).toBeNull();
    expect(refusalLine(sheet({ layout: verdict({ kind: "unknown", confidence: 0 }) }))).toBeNull();
    expect(refusalLine(sheet({ layout: verdict({}) }))).toBeNull();
    expect(refusalLine(sheet({ layout: null }))).toBeNull();
  });
});

describe("allUnknown -- the judge-was-unreachable workbook state, first-class (D-12-16)", () => {
  const unknownVerdict = () =>
    verdict({ kind: "unknown", confidence: 0.0, reasoning: "", needs_confirmation: true });

  it("is true only when EVERY sheet's layout kind is unknown", () => {
    const sheets = [
      sheet({ sheet_name: "A", status: "layout_unknown", layout: unknownVerdict() }),
      sheet({ sheet_name: "B", status: "layout_unknown", layout: unknownVerdict() }),
    ];

    expect(allUnknown(sheets)).toBe(true);
  });

  it("is false the moment one sheet carries a judged verdict", () => {
    const sheets = [
      sheet({ sheet_name: "A", status: "layout_unknown", layout: unknownVerdict() }),
      sheet({ sheet_name: "B", layout: verdict({}) }),
    ];

    expect(allUnknown(sheets)).toBe(false);
  });

  it("is false when a sheet has no layout at all -- a stale response is not a judge failure", () => {
    const sheets = [
      sheet({ sheet_name: "A", status: "layout_unknown", layout: unknownVerdict() }),
      sheet({ sheet_name: "B", layout: null }),
    ];

    expect(allUnknown(sheets)).toBe(false);
  });

  it("is false for an empty manifest", () => {
    expect(allUnknown([])).toBe(false);
  });
});

describe("every other sheet is untouched -- only the unreadable VERDICTS are suppressed", () => {
  it("an `ok` sheet still shows its headers and its Schema control", () => {
    const ok = sheet({});

    expect(showsDetectedHeaders(ok)).toBe(true);
    expect(showsSchemaSelect(ok)).toBe(true);
  });

  it("a `header_uncertain` sheet still shows both -- an uncertain header ROW is a question the human CAN answer, unlike a shape", () => {
    const legend = sheet({
      sheet_name: "LEGEND",
      status: "header_uncertain",
      headers: ["CMP", "compound identifier"],
      proposed_schema: "assay-potency",
    });

    expect(showsDetectedHeaders(legend)).toBe(true);
    expect(showsSchemaSelect(legend)).toBe(true);
    expect(initialSelections(question([legend]), null)[0].schemaName).toBe("assay-potency");
  });

  it("a `drawing_only` sheet has no headers to list, but its Schema control stays -- the human may still insist, and its own question then explains why it cannot be read", () => {
    const drawing = sheet({
      sheet_name: "Chart",
      status: "drawing_only",
      headers: [],
      proposals: [],
      proposed_schema: null,
    });

    // Nothing to render: an empty header list renders as no chips either way.
    expect(showsDetectedHeaders(drawing)).toBe(false);
    expect(showsSchemaSelect(drawing)).toBe(true);
  });
});

describe("submitBlockedReason", () => {
  it("blocks at 0 ticked with the UI-SPEC's exact copy", () => {
    const selections: SheetChoice[] = [
      { sheetName: "DATA", tableIndex: null, ticked: false, schemaName: "assay-potency", askLayout: false },
      { sheetName: "Notes", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
    ];

    expect(submitBlockedReason(selections)).toBe("Tick at least one sheet to ingest.");
  });

  it("blocks while any ticked sheet has no Schema, naming that sheet", () => {
    const selections: SheetChoice[] = [
      { sheetName: "DATA", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
      { sheetName: "Week 2", tableIndex: null, ticked: true, schemaName: null, askLayout: false },
    ];

    expect(submitBlockedReason(selections)).toBe(
      "Choose a Schema for 'Week 2' — ties aren't broken automatically."
    );
  });

  it("returns null when at least one sheet is ticked and every ticked sheet has a Schema", () => {
    const selections: SheetChoice[] = [
      { sheetName: "DATA", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
      { sheetName: "Notes", tableIndex: null, ticked: false, schemaName: null, askLayout: false },
    ];

    expect(submitBlockedReason(selections)).toBeNull();
  });
});

describe("toResolvePayload", () => {
  it("includes ONLY ticked sheets, each with its chosen Schema, matching SheetResolveRequest", () => {
    const selections: SheetChoice[] = [
      { sheetName: "Week 1", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
      { sheetName: "Notes", tableIndex: null, ticked: false, schemaName: "assay-potency", askLayout: false },
      { sheetName: "Week 2", tableIndex: null, ticked: true, schemaName: "assay-binding", askLayout: false },
    ];

    const payload = toResolvePayload("token-s", selections);

    expect(payload).toEqual({
      upload_token: "token-s",
      selections: [
        { sheet_name: "Week 1", schema_name: "assay-potency" },
        { sheet_name: "Week 2", schema_name: "assay-binding" },
      ],
    });
    // Pin the exact wire keys: the client only ever chooses among options the
    // server already offered (T-08-08) -- nothing else rides along.
    expect(Object.keys(payload)).toEqual(["upload_token", "selections"]);
    expect(Object.keys(payload.selections[0])).toEqual(["sheet_name", "schema_name"]);
  });
});

describe("the ask-me-instead flag rides the resolve payload (12-UI-SPEC Discretion §2)", () => {
  it("arrives false on every initial selection -- disagreement is the human's move, never a default", () => {
    const selections = initialSelections(question([sheet({ layout: verdict({}) })]), null);

    expect(selections[0].askLayout).toBe(false);
  });

  it("sends `ask_layout: true` for a ticked sheet the human disagreed on -- 12-05's recorded wire field name, verbatim", () => {
    const selections: SheetChoice[] = [
      { sheetName: "Week 1", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: true },
    ];

    expect(toResolvePayload("token-s", selections).selections).toEqual([
      { sheet_name: "Week 1", schema_name: "assay-potency", ask_layout: true },
    ]);
  });

  it("OMITS the key entirely when the human did not disagree -- the payload stays byte-identical to Phase 11's", () => {
    const selections: SheetChoice[] = [
      { sheetName: "Week 1", tableIndex: null, ticked: true, schemaName: "assay-potency", askLayout: false },
    ];

    const payload = toResolvePayload("token-s", selections);

    expect(Object.keys(payload.selections[0])).toEqual(["sheet_name", "schema_name"]);
  });

  it("an asked but UNTICKED sheet stays absent -- skipping modifies nothing and sends nothing (T-08-08)", () => {
    const selections: SheetChoice[] = [
      { sheetName: "Week 1", tableIndex: null, ticked: false, schemaName: "assay-potency", askLayout: true },
      { sheetName: "Week 2", tableIndex: null, ticked: true, schemaName: "assay-binding", askLayout: false },
    ];

    expect(toResolvePayload("token-s", selections).selections).toEqual([
      { sheet_name: "Week 2", schema_name: "assay-binding" },
    ]);
  });
});

describe("sheetBadge -- muted structural facts vs the amber act-on-this (12-UI-SPEC §Color)", () => {
  it("badges a key_value sheet 'labels down the side' -- a readable, positive fact: secondary, never amber, never muted", () => {
    const badge = sheetBadge(sheet({ layout: verdict({ kind: "key_value", record_count: 1 }) }));

    expect(badge).toEqual({ label: "labels down the side", tone: "secondary" });
  });

  it("badges an unknown verdict 'layout unknown' in amber -- the tool is not sure, a human must act", () => {
    const badge = sheetBadge(
      sheet({
        status: "layout_unknown",
        layout: verdict({ kind: "unknown", confidence: 0, reasoning: "", needs_confirmation: true }),
      })
    );

    expect(badge).toEqual({ label: "layout unknown", tone: "amber" });
  });

  it("badges a stale layout_unknown status with NO layout the same way -- the gate is the server's either way", () => {
    expect(sheetBadge(sheet({ status: "layout_unknown", layout: null }))).toEqual({
      label: "layout unknown",
      tone: "amber",
    });
  });

  it("badges not_a_table and the two can't-read kinds as muted facts, not warnings to act on", () => {
    expect(sheetBadge(sheet({ layout: verdict({ kind: "not_a_table" }) }))).toEqual({
      label: "not a table",
      tone: "muted",
    });
    expect(sheetBadge(sheet({ layout: verdict({ kind: "wide_matrix" }) }))).toEqual({
      label: "can't read this layout yet",
      tone: "muted",
    });
    expect(sheetBadge(sheet({ layout: verdict({ kind: "multiple_tables" }) }))).toEqual({
      label: "can't read this layout yet",
      tone: "muted",
    });
  });

  it("shows NO badge for a confident row_per_record on an ok sheet -- a clean verdict is a quiet fact, not an achievement", () => {
    expect(sheetBadge(sheet({ layout: verdict({}) }))).toBeNull();
  });

  it("keeps the status badges for a row_per_record verdict and for pre-verdict responses -- the gate still shows", () => {
    expect(
      sheetBadge(sheet({ status: "header_uncertain", layout: verdict({ needs_confirmation: true }) }))
    ).toEqual({ label: "header unclear", tone: "amber" });
    expect(sheetBadge(sheet({ status: "drawing_only", layout: null }))).toEqual({
      label: "no table found",
      tone: "muted",
    });
    expect(sheetBadge(sheet({ status: "unsupported_shape", layout: null }))).toEqual({
      label: "unsupported shape",
      tone: "muted",
    });
    expect(sheetBadge(sheet({}))).toBeNull();
  });
});

describe("the disagree action appears on EVERY judged sheet (D-12-08: the human is the only check)", () => {
  it("shows on a CONFIDENT row_per_record -- under headers_only the judge is weakest exactly where a wrong row_per_record re-opens the leak", () => {
    expect(showsAskLayoutAction(sheet({ layout: verdict({ confidence: 0.99 }) }))).toBe(true);
  });

  it.each(["key_value", "not_a_table", "wide_matrix", "multiple_tables"] as const)(
    "shows on a %s verdict -- every claim the tool makes is one the human can reject",
    (kind) => {
      expect(showsAskLayoutAction(sheet({ layout: verdict({ kind }) }))).toBe(true);
    }
  );

  it("does NOT show for unknown or a null layout -- an unknown sheet already routes to the layout question; no verdict, nothing to disagree with", () => {
    expect(
      showsAskLayoutAction(sheet({ layout: verdict({ kind: "unknown", confidence: 0 }) }))
    ).toBe(false);
    expect(showsAskLayoutAction(sheet({ layout: null }))).toBe(false);
  });

  it("carries the Copywriting Contract's exact action, engaged, and undo copy", () => {
    expect(LAYOUT_DISAGREE_ACTION).toBe("Not right? Answer the layout yourself");
    expect(LAYOUT_DISAGREE_ENGAGED_LINE).toBe("You'll be asked about this sheet's layout in Review.");
    expect(LAYOUT_DISAGREE_UNDO_ACTION).toBe("Use Claude's read instead");
  });
});

describe("the all-unknown workbook notice", () => {
  it("says the judge couldn't run ONCE, at workbook level, in the contract's exact words", () => {
    expect(ALL_UNKNOWN_NOTICE).toBe(
      "The layout judge couldn't run, so no sheet's layout is known. Each ticked sheet will ask about its layout in Review before anything is mapped."
    );
  });
});

/** The layout question's `proposal` exactly as the wire sends it --
 * `StructuralHint.to_dict()` with `layout` = `SheetLayout`'s JSON (12-05's
 * `service.layout_question_for`): the verdict rides intact, blocks and
 * indices included, because the blocks are the un-pivot's ONLY input. */
const kvLayoutDict = {
  kind: "key_value",
  confidence: 0.92,
  reasoning: "field names down column A with one value beside each",
  header_row_index: null,
  first_data_row: null,
  last_data_row: null,
  key_value_blocks: [
    { label_column: 0, value_columns: [1], first_row: 1, last_row: 10 },
    { label_column: 3, value_columns: [4], first_row: 1, last_row: 10 },
  ],
  one_record_per_value_column: false,
};

const kvProposal: Record<string, unknown> = {
  sheet_name: "Patient Info",
  header_row_index: null,
  delimiter: null,
  decimal_separator: null,
  data_region: null,
  table_shape: null,
  layout: kvLayoutDict,
};

/** The cascade `Patient Info` grid's first rows, as `evidence_rows` carries
 * them: labels in columns 0 and 3, VALUES beside them. The chips must read
 * the label columns only -- a `TAYLOR, James` among the chips is the verdict
 * being WRONG, and that is exactly what the chips exist to reveal. */
const kvEvidence: string[][] = [
  ["PATIENT INFORMATION", "", "", "", ""],
  ["Name", "TAYLOR, James", "", "Accession #", "CS-2026-698392"],
  ["MRN", "3809217", "", "Ordering Provider", "Dr. R. Okafor"],
  ["Date of Birth", "1961-03-14", "", "Specimen Type", "Serum"],
  ["", "", "", "Collected", "2026-06-30"],
  ["Sex", "M", "", "Received", "2026-07-01"],
];

function fullVerdict(line: HintVerdictLine): string {
  if (!line.judged) return line.text;
  return line.lead + line.kindPhrase + line.rest + line.confidence + line.trailer;
}

describe("proposalLayout -- reading the verdict off the layout question's proposal", () => {
  it("parses the wire dict into the SheetLayoutIn shape, blocks and indices intact", () => {
    const layout = proposalLayout(kvProposal);

    expect(layout).toEqual({
      kind: "key_value",
      confidence: 0.92,
      reasoning: "field names down column A with one value beside each",
      header_row_index: null,
      first_data_row: null,
      last_data_row: null,
      key_value_blocks: [
        { label_column: 0, value_columns: [1], first_row: 1, last_row: 10 },
        { label_column: 3, value_columns: [4], first_row: 1, last_row: 10 },
      ],
      one_record_per_value_column: false,
    });
  });

  it("returns null for a null proposal and for a proposal without a layout -- a delimiter question is not a layout question", () => {
    expect(proposalLayout(null)).toBeNull();
    expect(proposalLayout({ delimiter: ";", layout: null })).toBeNull();
  });

  it("returns null for an invented kind -- the client never renders a claim the wire vocabulary cannot make", () => {
    expect(proposalLayout({ layout: { ...kvLayoutDict, kind: "diagonal" } })).toBeNull();
  });
});

describe("hintVerdictLine -- the verdict block, in the contract's exact words", () => {
  it("renders a key_value verdict with its record count", () => {
    const line = hintVerdictLine(proposalLayout(kvProposal));

    expect(fullVerdict(line)).toBe(
      "Claude read this sheet as labels down the side — 1 record(s). field names down column A with one value beside each (92% confident)"
    );
    expect(line).toMatchObject({ judged: true, kindPhrase: "labels down the side" });
  });

  it("renders a low-confidence row_per_record verdict -- the off-by-one fix path DOES reach this panel", () => {
    const layout: SheetLayoutIn = {
      kind: "row_per_record",
      confidence: 0.72,
      reasoning: "banner rows above a plausible header",
      header_row_index: 4,
    };

    expect(fullVerdict(hintVerdictLine(layout))).toBe(
      "Claude read this sheet as one row per record. banner rows above a plausible header (72% confident)"
    );
  });

  it("renders the other refused kinds through the same generic form", () => {
    const layout: SheetLayoutIn = {
      kind: "not_a_table",
      confidence: 0.96,
      reasoning: "a report banner and contact details, no data grid",
    };

    expect(fullVerdict(hintVerdictLine(layout))).toBe(
      "Claude read this sheet as not a table. a report banner and contact details, no data grid (96% confident)"
    );
  });

  it("says plainly when there is NO verdict -- unknown or judge unreachable, no percentage theatre", () => {
    const unknownLayout: SheetLayoutIn = { kind: "unknown", confidence: 0.0, reasoning: "" };

    expect(fullVerdict(hintVerdictLine(unknownLayout))).toBe(
      "The tool couldn't judge this sheet's layout on its own."
    );
    expect(fullVerdict(hintVerdictLine(null))).toBe(
      "The tool couldn't judge this sheet's layout on its own."
    );
    expect(fullVerdict(hintVerdictLine(null))).not.toContain("%");
  });
});

describe("hintLabels -- the checking material (labels reading as field names IS the verdict being right)", () => {
  it("reads ONLY the label columns of Claude's blocks, in block order -- never a value column", () => {
    const labels = hintLabels(proposalLayout(kvProposal), kvEvidence);

    expect(labels).toEqual([
      "Name",
      "MRN",
      "Date of Birth",
      "Sex",
      "Accession #",
      "Ordering Provider",
      "Specimen Type",
      "Collected",
      "Received",
    ]);
    expect(labels).not.toContain("TAYLOR, James");
    expect(labels).not.toContain("CS-2026-698392");
  });

  it("clamps to the evidence actually sent -- a block's last_row beyond the preview is not an error", () => {
    const shortEvidence = kvEvidence.slice(0, 3);

    expect(hintLabels(proposalLayout(kvProposal), shortEvidence)).toEqual([
      "Name",
      "MRN",
      "Accession #",
      "Ordering Provider",
    ]);
  });

  it("returns nothing for a non-key-value or missing verdict -- there are no labels to claim", () => {
    expect(hintLabels(null, kvEvidence)).toEqual([]);
    expect(
      hintLabels({ kind: "row_per_record", confidence: 0.7, header_row_index: 1 }, kvEvidence)
    ).toEqual([]);
  });
});

describe("hintLayoutOptions -- the two-option question (12-UI-SPEC Discretion §3)", () => {
  it("offers the key-value option ONLY when the proposal carries blocks -- a kind without indices is un-actionable", () => {
    const withBlocks = hintLayoutOptions(proposalLayout(kvProposal));
    const blockless = hintLayoutOptions({ kind: "key_value", confidence: 0.9, key_value_blocks: [] });

    expect(withBlocks.keyValueOptionLabel).toBe("Labels down the side — 1 record(s)");
    expect(blockless.keyValueOptionLabel).toBeNull();
    expect(blockless.preSelected).toBeNull();
  });

  it("pre-selects the key-value option when present", () => {
    expect(hintLayoutOptions(proposalLayout(kvProposal)).preSelected).toBe("key_value");
  });

  it("labels the N-record variant off the blocks' value columns (one_record_per_value_column)", () => {
    const options = hintLayoutOptions({
      kind: "key_value",
      confidence: 0.9,
      key_value_blocks: [{ label_column: 0, value_columns: [1, 2, 3], first_row: 1, last_row: 8 }],
      one_record_per_value_column: true,
    });

    expect(options.keyValueOptionLabel).toBe("Labels down the side — 3 record(s)");
  });

  it("pre-selects 'One row per record' with the header row pre-filled for a low-confidence row_per_record", () => {
    const options = hintLayoutOptions({
      kind: "row_per_record",
      confidence: 0.72,
      header_row_index: 4,
    });

    expect(options.keyValueOptionLabel).toBeNull();
    expect(options.preSelected).toBe("row_per_record");
    expect(options.headerRowPrefill).toBe(4);
  });

  it("pre-selects NOTHING for an unknown verdict -- the human chooses, or nothing proceeds", () => {
    const options = hintLayoutOptions({ kind: "unknown", confidence: 0.0 });

    expect(options.keyValueOptionLabel).toBeNull();
    expect(options.preSelected).toBeNull();
    expect(options.headerRowPrefill).toBeNull();
  });

  it("carries the contract's exact question, option, limit, and blocked copy", () => {
    expect(HINT_LAYOUT_QUESTION_LABEL).toBe("How is this sheet laid out?");
    expect(ROW_PER_RECORD_OPTION_LABEL).toBe("One row per record");
    expect(HINT_LAYOUT_BLOCKED_LINE).toBe("Choose how the sheet is laid out.");
    expect(HINT_NO_KEY_VALUE_LIMIT_LINE).toBe(
      "If this sheet is a labels-down-the-side layout, the tool needs Claude's read to find the labels — it couldn't get one this time. If it isn't one row per record either, reshape it to one row per record or try a different file."
    );
  });
});

describe("toLayoutAnswerPayload -- both answers, exactly as 12-05 pinned them at the HTTP boundary", () => {
  it("posts 'Labels down the side' as CONFIRMATION of Claude's blocks -- never indices the browser invented", () => {
    const payload = toLayoutAnswerPayload("key_value", proposalLayout(kvProposal), undefined, "Patient Info");

    expect(payload).toEqual({
      sheet_name: "Patient Info",
      layout: {
        kind: "key_value",
        confidence: 1.0,
        reasoning: "confirmed by the curator",
        key_value_blocks: [
          { label_column: 0, value_columns: [1], first_row: 1, last_row: 10 },
          { label_column: 3, value_columns: [4], first_row: 1, last_row: 10 },
        ],
      },
    });
    // Pin the exact wire keys: no header_row_index, no data-row trim, nothing
    // the human did not confirm rides along.
    expect(Object.keys(payload.layout as object)).toEqual([
      "kind",
      "confidence",
      "reasoning",
      "key_value_blocks",
    ]);
  });

  it("carries one_record_per_value_column through when Claude proposed it -- the un-pivot's N-records switch is part of the blocks", () => {
    const layout = proposalLayout({
      layout: { ...kvLayoutDict, one_record_per_value_column: true },
    });

    const payload = toLayoutAnswerPayload("key_value", layout, undefined, "Visits");

    expect(payload.layout?.one_record_per_value_column).toBe(true);
  });

  it("posts 'One row per record' with the human's header row -- round trip B's explicit-layout form", () => {
    const payload = toLayoutAnswerPayload("row_per_record", proposalLayout(kvProposal), 4, "Results");

    expect(payload).toEqual({
      sheet_name: "Results",
      layout: {
        kind: "row_per_record",
        confidence: 1.0,
        reasoning: "confirmed by the curator",
        header_row_index: 4,
      },
    });
  });

  it("omits an unanswered header row and an unknown sheet name -- only what the human actually decided is sent", () => {
    const payload = toLayoutAnswerPayload("row_per_record", null, undefined, null);

    expect(payload).toEqual({
      layout: { kind: "row_per_record", confidence: 1.0, reasoning: "confirmed by the curator" },
    });
    expect(Object.keys(payload)).toEqual(["layout"]);
  });
});

describe("coverageLine", () => {
  it("renders the learned-profile copy verbatim", () => {
    expect(coverageLine(profileProposal)).toBe("7/7 canonical fields matched · learned profile");
  });

  it("renders the crosswalk copy verbatim", () => {
    expect(coverageLine(crosswalkProposal)).toBe("6/7 canonical fields matched · crosswalk");
  });

  it("labels a Claude proposal as evidence-free, verbatim -- the human is entitled to know nothing is behind it (D-11-19)", () => {
    expect(coverageLine(claudeProposal)).toBe(
      "No crosswalk match — Claude suggests assay-potency. Check it before ingesting."
    );
  });
});
