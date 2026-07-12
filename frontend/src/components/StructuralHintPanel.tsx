import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { StructuralHintIn, StructuralQuestionResponse } from "@/lib/types";
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
 * step. Which answer controls appear is derived entirely from which
 * `StructuralHint` dimensions are non-null on `question.proposal` (mirrors
 * whichever fields `parsing/table.py`'s question-builders actually set),
 * never a hardcoded assumption about `unsure_about`'s free-text wording.
 * P2/CR-01: when `headersOnly` is on, the evidence grid renders NO cell
 * values at all -- only the column/row counts -- even though the wire
 * response itself still carries `evidence_rows` (the server does not
 * strip them on this path); this component is the only place that
 * enforces the privacy guarantee for the hint preview.
 */
export function StructuralHintPanel({ question, headersOnly, submitting, onResolve }: StructuralHintPanelProps) {
  const proposalHeaderRow = proposalField(question.proposal, "header_row_index") as number | null;
  const proposalSheet = proposalField(question.proposal, "sheet_name") as string | null;
  const proposalDelimiter = proposalField(question.proposal, "delimiter") as string | null;
  const proposalDecimal = proposalField(question.proposal, "decimal_separator") as string | null;
  const proposalShape = proposalField(question.proposal, "table_shape") as string | null;

  const showHeaderRowControl = proposalHeaderRow !== null;
  const showSheetControl = proposalSheet !== null;
  const showDelimiterControl = proposalDelimiter !== null;
  const showDecimalControl = proposalDecimal !== null;

  const sheetOptions = Array.from(
    new Set(
      [
        proposalSheet,
        ...question.alternatives.map((alt) => proposalField(alt, "sheet_name") as string | null),
      ].filter((name): name is string => name !== null)
    )
  );

  const [headerRowIndex, setHeaderRowIndex] = useState<number | undefined>(proposalHeaderRow ?? undefined);
  const [sheetName, setSheetName] = useState<string | undefined>(proposalSheet ?? undefined);
  const [delimiter, setDelimiter] = useState<string | undefined>(proposalDelimiter ?? undefined);
  const [decimalSeparator, setDecimalSeparator] = useState<string | undefined>(proposalDecimal ?? undefined);

  const rowCount = question.evidence_rows.length;
  const columnCount = question.evidence_rows.reduce((max, row) => Math.max(max, row.length), 0);

  function handleSubmit() {
    const answers: HintAnswers = {};
    if (showHeaderRowControl && headerRowIndex !== undefined) answers.headerRowIndex = headerRowIndex;
    if (showSheetControl && sheetName !== undefined) answers.sheetName = sheetName;
    if (showDelimiterControl && delimiter !== undefined) answers.delimiter = delimiter;
    if (showDecimalControl && decimalSeparator !== undefined) answers.decimalSeparator = decimalSeparator;
    onResolve(buildHintPayload(answers));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">Help us find the table</CardTitle>
        <p className="text-body text-muted-foreground">{question.reason}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {headersOnly ? (
          <p className="text-body text-muted-foreground">
            Cell values hidden — headers-only mode is on. Showing column names and row count only.
            {" "}({columnCount} columns, {rowCount} rows)
          </p>
        ) : (
          <div className="max-w-full overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-mono-label">
              <tbody>
                {question.evidence_rows.slice(0, 5).map((row, rowIndex) => (
                  <tr
                    key={rowIndex}
                    role={showHeaderRowControl ? "button" : undefined}
                    tabIndex={showHeaderRowControl ? 0 : undefined}
                    onClick={() => {
                      if (showHeaderRowControl) setHeaderRowIndex(rowIndex);
                    }}
                    className={cn(
                      rowIndex % 2 === 1 && "bg-muted/40",
                      showHeaderRowControl && "cursor-pointer hover:bg-primary/10",
                      showHeaderRowControl && headerRowIndex === rowIndex && "bg-primary/15"
                    )}
                  >
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex} className="whitespace-nowrap px-2 py-1">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!question.answerable_by_hint ? (
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
                  min={0}
                  value={headerRowIndex ?? ""}
                  onChange={(event) =>
                    setHeaderRowIndex(event.target.value === "" ? undefined : Number(event.target.value))
                  }
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
