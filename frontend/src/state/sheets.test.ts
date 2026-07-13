import { describe, expect, it } from "vitest";

import {
  UNREADABLE_SHAPE_LINE,
  coverageLine,
  initialSelections,
  showsDetectedHeaders,
  showsSchemaSelect,
  submitBlockedReason,
  toResolvePayload,
} from "./sheets";
import type { SheetChoice } from "./sheets";
import type { SheetOut, SheetQuestionResponse, SheetSchemaProposal } from "../lib/types";

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
  source: "claude",
  reason: "column names resemble potency readouts",
};

function sheet(overrides: Partial<SheetOut>): SheetOut {
  return {
    sheet_name: "DATA",
    row_count: 12,
    headers: ["Cmpd ID", "IC50 (uM)"],
    column_signature: "sig-1",
    status: "ok",
    proposals: [crosswalkProposal],
    proposed_schema: "assay-potency",
    tie: false,
    ...overrides,
  };
}

function question(sheets: SheetOut[]): SheetQuestionResponse {
  return { kind: "sheet_question", upload_token: "token-s", sheets };
}

describe("initialSelections", () => {
  it("pre-ticks a sheet with a proposal and pre-selects that Schema (D-11-06: pre-fill, never auto-apply)", () => {
    const selections = initialSelections(question([sheet({})]), null);

    expect(selections).toEqual([{ sheetName: "DATA", ticked: true, schemaName: "assay-potency" }]);
  });

  it("pre-unticks a zero-coverage sheet -- `proposals == []` IS the propose-skip signal, never `proposed_schema`", () => {
    const skip = sheet({
      sheet_name: "Notes",
      proposals: [],
      proposed_schema: null,
    });

    const selections = initialSelections(question([skip]), null);

    expect(selections).toEqual([{ sheetName: "Notes", ticked: false, schemaName: null }]);
  });

  it("falls back to the Upload dropdown's Schema for the Select when the scorer proposed none (D-11-16) -- WITHOUT ticking the sheet", () => {
    const skip = sheet({ sheet_name: "Notes", proposals: [], proposed_schema: null });

    const selections = initialSelections(question([skip]), "assay-potency");

    expect(selections).toEqual([
      { sheetName: "Notes", ticked: false, schemaName: "assay-potency" },
    ]);
  });

  it("shows a tie AS a tie: ticked, but the Select left EMPTY -- the tool breaks ties for nobody", () => {
    const tied = sheet({
      proposals: [crosswalkProposal, { ...crosswalkProposal, schema_name: "assay-binding" }],
      proposed_schema: null,
      tie: true,
    });

    const selections = initialSelections(question([tied]), null);

    expect(selections).toEqual([{ sheetName: "DATA", ticked: true, schemaName: null }]);
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
      { sheetName: "Chart", ticked: false, schemaName: null },
      { sheetName: "Pivot", ticked: false, schemaName: null },
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
      { sheetName: "LEGEND", ticked: false, schemaName: "assay-potency" },
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

/** The `Summary` sheet of a real clinical workbook: a key-value cover page
 * (labels in column A, values in column B). The shape gate rules it out
 * correctly and the backend now suppresses its headers -- so it arrives with
 * NOTHING: no headers, no proposals, no Schema. The panel must not invent any
 * of them back. */
const unreadableShape = (): SheetOut =>
  sheet({
    sheet_name: "Summary",
    status: "unsupported_shape",
    headers: [],
    proposals: [],
    proposed_schema: null,
  });

describe("an unreadable shape shows no answer, because the tool has none", () => {
  it("renders NO detected-headers list -- the tool could not read the shape, so any header it named would be a cell value dressed as a column", () => {
    expect(showsDetectedHeaders(unreadableShape())).toBe(false);
  });

  it("renders NO Schema control -- a Schema for a sheet the tool has just proposed to skip is an answer to a question it cannot answer", () => {
    expect(showsSchemaSelect(unreadableShape())).toBe(false);
  });

  it("pre-selects NO Schema, and the Upload dropdown does not get to fill it either -- `proposed_schema ?? defaultSchema` is what put `assay-potency` on the screen", () => {
    const selections = initialSelections(question([unreadableShape()]), "assay-potency");

    expect(selections).toEqual([{ sheetName: "Summary", ticked: false, schemaName: null }]);
  });

  it("stays present and stays TICKABLE -- marked, never dropped, never disabled away (SHEET-04)", () => {
    const selections = initialSelections(
      question([unreadableShape(), sheet({ sheet_name: "IgE Results" })]),
      null
    );

    expect(selections.map((s) => s.sheetName)).toEqual(["Summary", "IgE Results"]);
    // Unticked is a PROPOSAL, not a lock: the human may still tick it, and
    // `submitBlockedReason` then makes them choose a Schema for it themselves.
    expect(submitBlockedReason([{ sheetName: "Summary", ticked: true, schemaName: null }])).toBe(
      "Choose a Schema for 'Summary' — ties aren't broken automatically."
    );
  });

  it("says plainly what it is and what the tool cannot do, in place of the headers it will not show", () => {
    expect(UNREADABLE_SHAPE_LINE).toBe(
      "This sheet isn't laid out as one row per record, so the tool can't read it as a table — it has no headers to show and nothing to map. Proposed: skip this sheet."
    );
  });
});

describe("every other sheet is untouched -- only the SHAPE case is suppressed", () => {
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
      { sheetName: "DATA", ticked: false, schemaName: "assay-potency" },
      { sheetName: "Notes", ticked: false, schemaName: null },
    ];

    expect(submitBlockedReason(selections)).toBe("Tick at least one sheet to ingest.");
  });

  it("blocks while any ticked sheet has no Schema, naming that sheet", () => {
    const selections: SheetChoice[] = [
      { sheetName: "DATA", ticked: true, schemaName: "assay-potency" },
      { sheetName: "Week 2", ticked: true, schemaName: null },
    ];

    expect(submitBlockedReason(selections)).toBe(
      "Choose a Schema for 'Week 2' — ties aren't broken automatically."
    );
  });

  it("returns null when at least one sheet is ticked and every ticked sheet has a Schema", () => {
    const selections: SheetChoice[] = [
      { sheetName: "DATA", ticked: true, schemaName: "assay-potency" },
      { sheetName: "Notes", ticked: false, schemaName: null },
    ];

    expect(submitBlockedReason(selections)).toBeNull();
  });
});

describe("toResolvePayload", () => {
  it("includes ONLY ticked sheets, each with its chosen Schema, matching SheetResolveRequest", () => {
    const selections: SheetChoice[] = [
      { sheetName: "Week 1", ticked: true, schemaName: "assay-potency" },
      { sheetName: "Notes", ticked: false, schemaName: "assay-potency" },
      { sheetName: "Week 2", ticked: true, schemaName: "assay-binding" },
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
