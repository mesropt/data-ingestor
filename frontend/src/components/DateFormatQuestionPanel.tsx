import { useState } from "react";
import { CalendarClock, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { DateFormatChoice, DateFormatOrder, DateFormatQuestionResponse } from "@/lib/types";
import { allColumnsAnswered, previewFor, toResolvePayload } from "@/state/dateFormat";

interface DateFormatQuestionPanelProps {
  question: DateFormatQuestionResponse;
  headersOnly: boolean;
  submitting: boolean;
  onResolve: (choices: DateFormatChoice[]) => void;
}

const OPTIONS: { order: DateFormatOrder; label: string }[] = [
  { order: "day_first", label: "DD/MM/YYYY" },
  { order: "month_first", label: "MM/DD/YYYY" },
];

/**
 * Inline per-column date-order resolution (D-10-07, T-10-31/T-10-32) --
 * renders directly below `UploadDropzone` in the SAME upload flow, never a
 * modal, mirroring `ReconcilePanel`'s multi-conflict/single-submit shape
 * (NOT `StructuralHintPanel`'s single-question one: there can genuinely be
 * more than one ambiguous date column in one file). Every column's order is
 * chosen independently and submitted together in ONE request; only an
 * `order` ever leaves this component (T-10-31, `toResolvePayload` carries
 * no format-string key at all). Under `headersOnly` no evidence value or
 * preview is rendered at all (T-10-32) -- the server already redacted
 * `example_values` to `[]` (Plan 05), so this component enforces the SAME
 * privacy rule on its own rendering as defence in depth.
 */
export function DateFormatQuestionPanel({
  question,
  headersOnly,
  submitting,
  onResolve,
}: DateFormatQuestionPanelProps) {
  const [answers, setAnswers] = useState<Record<string, DateFormatOrder>>({});

  function handleSubmit() {
    onResolve(toResolvePayload(question.upload_token, answers).choices);
  }

  const ready = allColumnsAnswered(question.columns, answers);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-heading">
          <CalendarClock className="size-5" />
          Confirm date order
        </CardTitle>
        <p className="text-body text-muted-foreground">
          {question.columns.length} column(s) have a date order Python can't determine on its own.
          Pick the right order for each — it's applied to every row in that column.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {question.columns.map((column) => {
          const selected = answers[column.target_field];
          const firstEvidence = !headersOnly ? (column.example_values[0] ?? null) : null;

          return (
            <div
              key={column.target_field}
              className="flex flex-col gap-2 rounded-lg border border-border p-3"
            >
              <Label className="text-mono-label">
                {firstEvidence
                  ? `'${column.source_column}' has values like ${firstEvidence} — is that day/month or month/day?`
                  : `'${column.source_column}' has an ambiguous date order.`}
              </Label>

              <div className="flex flex-col gap-2 sm:flex-row">
                {OPTIONS.map((option) => {
                  const preview = firstEvidence ? previewFor(firstEvidence, option.order) : null;
                  const isSelected = selected === option.order;
                  return (
                    <button
                      key={option.order}
                      type="button"
                      onClick={() =>
                        setAnswers((prev) => ({ ...prev, [column.target_field]: option.order }))
                      }
                      className={cn(
                        "flex flex-1 flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition-colors",
                        isSelected ? "border-primary bg-primary/10" : "border-border hover:bg-muted/40"
                      )}
                    >
                      <span className="text-body font-medium">{option.label}</span>
                      {preview && (
                        <span className="text-mono-label text-muted-foreground">e.g. {preview}</span>
                      )}
                    </button>
                  );
                })}
              </div>

              {headersOnly && (
                <p className="text-mono-label text-muted-foreground">
                  Values hidden — headers-only mode is on. {column.ambiguous_row_count} ambiguous
                  row(s) in this column.
                </p>
              )}
            </div>
          );
        })}

        <Button type="button" disabled={submitting || !ready} onClick={handleSubmit} className="self-start">
          {submitting && <Loader2 className="size-4 animate-spin" />}
          Use This Order and Continue
        </Button>
        <p className="text-mono-label text-muted-foreground">
          This choice applies to every row in this column — a flipped date order is a correctness
          defect, not a cosmetic one, so we only ask once.
        </p>
      </CardContent>
    </Card>
  );
}
