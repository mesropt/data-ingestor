import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { StructuralHintIn, StructuralQuestionResponse } from "@/lib/types";
import {
  HINT_LAYOUT_BLOCKED_LINE,
  HINT_LAYOUT_QUESTION_LABEL,
  ROW_PER_RECORD_OPTION_LABEL,
  hintLabels,
  hintLayoutOptions,
  hintVerdictLine,
  proposalLayout,
  toLayoutAnswerPayload,
  type LayoutAnswer,
} from "@/state/sheets";
import { buildHintPayload, type HintAnswers } from "@/state/upload";

interface StructuralHintPanelProps {
  question: StructuralQuestionResponse;
  headersOnly: boolean;
  submitting: boolean;
  onResolve: (hint: StructuralHintIn) => void;
}

const DELIMITER_OPTIONS = [
  { value: ",", label: "Comma (,)" },
  { value: ";", label: "Semicolon (;)" },
  { value: "\t", label: "Tab" },
];

const DECIMAL_OPTIONS = [
  { value: ".", label: "Point (.)" },
  { value: ",", label: "Comma (,)" },
];

/**
 * Rows are zero-based everywhere behind this screen (the judge's verdict, the
 * hint payload, pandas) and ONE-based everywhere the curator has ever seen a
 * spreadsheet. The tool was showing its own numbering and calling it a row
 * number: it said the header was row 10, Excel says `Tset` is on row 11, and the
 * curator was left to decide which of the two was lying.
 *
 * So the boundary is here, and only here: every number this panel DISPLAYS is a
 * spreadsheet row number, every number it SENDS is a zero-based index. Nothing
 * downstream changes its mind about what a row index is.
 */
const EXCEL_ROW_OFFSET = 1;

/** A typed spreadsheet row number back to the zero-based index the payload
 * carries. An empty box is `undefined` (unanswered), never row 0 — and a number
 * below the first row cannot be sent at all: an off-by-one here would move the
 * header onto a data row and rename every column after it. */
function toRowIndex(typed: string): number | undefined {
  if (typed === "") return undefined;
  const row = Number(typed);
  if (!Number.isFinite(row) || row < EXCEL_ROW_OFFSET) return undefined;
  return row - EXCEL_ROW_OFFSET;
}

/** `question.proposal`/`question.alternatives` are `StructureQuestion.to_dict()`'s
 * plain JSON dicts (`proposal: Record<string, unknown> | null` in
 * `lib/types.ts`) -- this reads one `StructuralHint` key back out, `null`
 * when absent, mirroring the domain dataclass's "every field optional"
 * contract on the wire side too. */
function proposalField(proposal: Record<string, unknown> | null, key: string): string | number | null {
  if (!proposal) return null;
  const value = proposal[key];
  return value === undefined || value === null ? null : (value as string | number);
}

/** Inline structural-hint resolution (D-04, UI-02) -- renders directly
 * below `UploadDropzone` in the SAME upload flow, never a modal/wizard
 * step, AND inside a group member's Review tab (the Phase 11 recursive-arm
 * machinery): ONE answer surface, upgraded once, reached from both paths
 * (12-UI-SPEC Discretion §2). Which answer controls appear is derived
 * entirely from which `StructuralHint` dimensions are non-null on
 * `question.proposal` (mirrors whichever fields the question-builders
 * actually set), never a hardcoded assumption about `unsure_about`'s
 * free-text wording -- and the LAYOUT question follows that exact pattern:
 * `proposal.layout` non-null is what makes a question a layout question
 * (12-05's `service.layout_question_for` always attaches the verdict, an
 * UNKNOWN one included, so the human is told WHY they are asked).
 *
 * The layout question renders the verdict block (Claude's read + the
 * "Labels found" chips -- the curator's checking material), then the
 * two-option "How is this sheet laid out?" question: "Labels down the
 * side" ONLY when the proposal carries blocks (confirming CLAUDE's blocks,
 * never indices the browser invents), "One row per record" always,
 * revealing the existing header-row control pre-filled from the verdict.
 * A confident `row_per_record` never reaches this panel at all (D-12-15).
 *
 * P2/CR-01: when `headersOnly` is on, the evidence grid renders NO cell
 * values at all -- only the column/row counts -- even though the wire
 * response itself still carries `evidence_rows` (the server does not
 * strip them on this path); this component is the only place that
 * enforces the privacy guarantee for the hint preview. The verdict and
 * its labels still show under headers-only (Discretion §4's ruling: a
 * key-value sheet's labels are its dataset's COLUMN NAMES, and hiding
 * them would make the verdict uncheckable in exactly the mode where the
 * judge is weakest).
 */
export function StructuralHintPanel({ question, headersOnly, submitting, onResolve }: StructuralHintPanelProps) {
  const proposalHeaderRow = proposalField(question.proposal, "header_row_index") as number | null;
  const proposalSheet = proposalField(question.proposal, "sheet_name") as string | null;
  const proposalDelimiter = proposalField(question.proposal, "delimiter") as string | null;
  const proposalDecimal = proposalField(question.proposal, "decimal_separator") as string | null;
  const proposalShape = proposalField(question.proposal, "table_shape") as string | null;

  const layoutProposal = proposalLayout(question.proposal);
  const isLayoutQuestion = layoutProposal !== null;
  const layoutOptions = hintLayoutOptions(layoutProposal);
  const verdictLine = hintVerdictLine(layoutProposal);
  const labels = hintLabels(layoutProposal, question.evidence_rows);

  const showHeaderRowControl = proposalHeaderRow !== null && !isLayoutQuestion;
  // The layout question is ABOUT this sheet -- the member's own question --
  // so no sheet Select is offered; the sheet name rides the answer payload.
  const showSheetControl = proposalSheet !== null && !isLayoutQuestion;
  const showDelimiterControl = proposalDelimiter !== null && !isLayoutQuestion;
  const showDecimalControl = proposalDecimal !== null && !isLayoutQuestion;

  const sheetOptions = Array.from(
    new Set(
      [
        proposalSheet,
        ...question.alternatives.map((alt) => proposalField(alt, "sheet_name") as string | null),
      ].filter((name): name is string => name !== null)
    )
  );

  const [layoutAnswer, setLayoutAnswer] = useState<LayoutAnswer | null>(layoutOptions.preSelected);
  const [headerRowIndex, setHeaderRowIndex] = useState<number | undefined>(
    proposalHeaderRow ?? layoutOptions.headerRowPrefill ?? undefined
  );
  const [sheetName, setSheetName] = useState<string | undefined>(proposalSheet ?? undefined);
  const [delimiter, setDelimiter] = useState<string | undefined>(proposalDelimiter ?? undefined);
  const [decimalSeparator, setDecimalSeparator] = useState<string | undefined>(proposalDecimal ?? undefined);

  const rowCount = question.evidence_rows.length;
  const columnCount = question.evidence_rows.reduce((max, row) => Math.max(max, row.length), 0);

  // The clickable-grid affordance: legacy header questions have it whenever
  // the proposal named a header row; the layout question reveals it WITH the
  // "One row per record" answer -- the grid row-click sets ONLY
  // `header_row_index`, never a key-value block (the human confirms or
  // rejects Claude's blocks wholesale; they do not edit them).
  const headerRowActive = isLayoutQuestion ? layoutAnswer === "row_per_record" : showHeaderRowControl;

  function handleSubmit() {
    const answers: HintAnswers = {};
    if (showHeaderRowControl && headerRowIndex !== undefined) answers.headerRowIndex = headerRowIndex;
    if (showSheetControl && sheetName !== undefined) answers.sheetName = sheetName;
    if (showDelimiterControl && delimiter !== undefined) answers.delimiter = delimiter;
    if (showDecimalControl && decimalSeparator !== undefined) answers.decimalSeparator = decimalSeparator;
    onResolve(buildHintPayload(answers));
  }

  function handleLayoutSubmit() {
    if (layoutAnswer === null) return;
    onResolve(toLayoutAnswerPayload(layoutAnswer, layoutProposal, headerRowIndex, proposalSheet));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">Help us find the table</CardTitle>
        <p className="text-body text-muted-foreground">{question.reason}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isLayoutQuestion && (
          // The verdict block, first: the claim, its reasoning, and its
          // confidence -- the tool never presents a claim the human cannot
          // check. The label chips ARE the check: field names reading as
          // field names is the verdict being right; a person's name among
          // them is it being wrong. Shown under headers-only too
          // (Discretion §4) -- labels are column names, not cell values.
          <div className="flex flex-col gap-2">
            <p className="text-body">
              {verdictLine.judged ? (
                <>
                  {verdictLine.lead}
                  <span className="font-semibold">{verdictLine.kindPhrase}</span>
                  {verdictLine.rest}
                  <span className="text-mono-label tabular-nums">{verdictLine.confidence}</span>
                  {verdictLine.trailer}
                </>
              ) : (
                verdictLine.text
              )}
            </p>
            {labels.length > 0 && (
              <>
                <span className="text-label text-muted-foreground">Labels found:</span>
                <div className="flex flex-wrap gap-2">
                  {labels.map((label, index) => (
                    <Badge key={`${label}-${index}`} variant="secondary" className="text-mono-label">
                      {label}
                    </Badge>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {headersOnly ? (
          <p className="text-body text-muted-foreground">
            Cell values hidden — headers-only mode is on. Showing column names and row count only.
            {" "}({columnCount} columns, {rowCount} rows)
          </p>
        ) : (
          // The grid is the curator's checking material, so it shows the rows
          // AROUND the row in question (the server centres the window on it),
          // numbered with their TRUE sheet row -- a header at row 10 under a
          // cover block was previously being confirmed against rows 0-4, which
          // could neither confirm nor refute it. The row numbers are also what
          // makes the number in the "Header row" box mean something: click a row
          // and the box shows that row's index, not its position in the preview.
          <div className="max-w-full overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-mono-label">
              <tbody>
                {question.evidence_rows.map((row, offset) => {
                  const rowIndex = question.evidence_first_row + offset;
                  return (
                    <tr
                      key={rowIndex}
                      role={headerRowActive ? "button" : undefined}
                      tabIndex={headerRowActive ? 0 : undefined}
                      onClick={() => {
                        if (headerRowActive) setHeaderRowIndex(rowIndex);
                      }}
                      className={cn(
                        offset % 2 === 1 && "bg-muted/40",
                        headerRowActive && "cursor-pointer hover:bg-primary/10",
                        headerRowActive && headerRowIndex === rowIndex && "bg-primary/15"
                      )}
                    >
                      <td className="select-none border-r border-border px-2 py-1 text-right tabular-nums text-muted-foreground">
                        {rowIndex + EXCEL_ROW_OFFSET}
                      </td>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex} className="whitespace-nowrap px-2 py-1">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {isLayoutQuestion ? (
          <>
            <div className="flex flex-col gap-2">
              <Label>{HINT_LAYOUT_QUESTION_LABEL}</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                {layoutOptions.keyValueOptionLabel !== null && (
                  <button
                    type="button"
                    onClick={() => setLayoutAnswer("key_value")}
                    className={cn(
                      "flex min-h-8 flex-1 flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition-colors",
                      layoutAnswer === "key_value"
                        ? "border-primary bg-primary/15"
                        : "border-border hover:bg-muted/40"
                    )}
                  >
                    <span className="text-body font-medium">{layoutOptions.keyValueOptionLabel}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setLayoutAnswer("row_per_record")}
                  className={cn(
                    "flex min-h-8 flex-1 flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition-colors",
                    layoutAnswer === "row_per_record"
                      ? "border-primary bg-primary/15"
                      : "border-border hover:bg-muted/40"
                  )}
                >
                  <span className="text-body font-medium">{ROW_PER_RECORD_OPTION_LABEL}</span>
                </button>
              </div>
            </div>

            {layoutAnswer === "row_per_record" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="hint-header-row">Header row</Label>
                <p className="text-body text-muted-foreground">
                  The row that holds the column names, numbered as your spreadsheet numbers it.
                  Click it in the grid above, or type its number — then confirm.
                </p>
                <Input
                  id="hint-header-row"
                  type="number"
                  min={EXCEL_ROW_OFFSET}
                  value={headerRowIndex === undefined ? "" : headerRowIndex + EXCEL_ROW_OFFSET}
                  onChange={(event) => setHeaderRowIndex(toRowIndex(event.target.value))}
                  className="w-32"
                />
              </div>
            )}

            <Button
              type="button"
              disabled={submitting || layoutAnswer === null}
              onClick={handleLayoutSubmit}
              className="self-start"
            >
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Use This and Re-parse
            </Button>
            {layoutAnswer === null && (
              <p className="text-mono-label text-muted-foreground">{HINT_LAYOUT_BLOCKED_LINE}</p>
            )}
          </>
        ) : !question.answerable_by_hint ? (
          // Legacy dead end: after D-12-15 every layout question arrives
          // answerable, so only a STALE pre-verdict response can land here.
          // Kept so such a response cannot crash; no new copy is written.
          <p className="text-body text-muted-foreground">
            This file's structure ({proposalShape ?? question.unsure_about}) isn't supported yet.
            Reshape it to one row per record, or try a different file.
          </p>
        ) : (
          <>
            {showHeaderRowControl && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="hint-header-row">Header row</Label>
                <Input
                  id="hint-header-row"
                  type="number"
                  min={EXCEL_ROW_OFFSET}
                  value={headerRowIndex === undefined ? "" : headerRowIndex + EXCEL_ROW_OFFSET}
                  onChange={(event) => setHeaderRowIndex(toRowIndex(event.target.value))}
                  className="w-32"
                />
              </div>
            )}

            {showSheetControl && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="hint-sheet">Sheet</Label>
                <Select value={sheetName} onValueChange={(value) => setSheetName(String(value))}>
                  <SelectTrigger id="hint-sheet" className="w-56">
                    <SelectValue placeholder="Choose a sheet…" />
                  </SelectTrigger>
                  <SelectContent>
                    {sheetOptions.map((name) => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {showDelimiterControl && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="hint-delimiter">Delimiter</Label>
                <Select value={delimiter} onValueChange={(value) => setDelimiter(String(value))}>
                  <SelectTrigger id="hint-delimiter" className="w-40">
                    <SelectValue placeholder="Choose a delimiter…" />
                  </SelectTrigger>
                  <SelectContent>
                    {DELIMITER_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {showDecimalControl && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="hint-decimal">Decimal separator</Label>
                <Select value={decimalSeparator} onValueChange={(value) => setDecimalSeparator(String(value))}>
                  <SelectTrigger id="hint-decimal" className="w-40">
                    <SelectValue placeholder="Choose a separator…" />
                  </SelectTrigger>
                  <SelectContent>
                    {DECIMAL_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <Button type="button" disabled={submitting} onClick={handleSubmit} className="self-start">
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Use This and Re-parse
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
