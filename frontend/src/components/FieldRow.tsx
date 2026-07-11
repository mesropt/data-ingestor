import { useState } from "react";
import { AlertTriangle, CheckCircle2, FlaskConical, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfidenceChip } from "@/components/ConfidenceChip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AlternativeOut, FieldMappingOut } from "@/lib/types";

interface FieldRowProps {
  mapping: FieldMappingOut;
  sourceColumns: string[];
  onResolveByChip: (candidate: AlternativeOut) => void;
  onResolveByAccept: () => void;
  onResolveByDropdown: (column: string) => void;
  onReopen: () => void;
}

/**
 * One target field's mapping state (UI-04). Clear (`!needs_confirmation`)
 * renders a thin `success`-tinted left-border row with reasoning collapsed
 * behind "Why?" -- a clear field doesn't need to shout its reasoning -- and
 * a muted "Change column" text-button (`onReopen`) so a resolved field is
 * never a dead end: the server's own P1 gate can reject an Accept the
 * client showed as green (a wrong-typed column bound at 100% confidence is
 * still wrong), and the only way back is re-opening the field's controls.
 * Clicking it hands off to the parent's `reopenField` (`state/review.ts`)
 * which flips `needs_confirmation` back to `true` WITHOUT losing the
 * field's current `source_column`/`alternatives` -- this component then
 * simply re-renders in the uncertain branch below with those same values
 * pre-populated. Uncertain (`needs_confirmation`) renders the full `uncertain` wash with
 * Claude's reasoning ALWAYS visible at rest (D-01's hard rule: the amber
 * reason is never hidden behind hover), the `validator_note` on its own
 * distinct sub-line when present (omitted entirely when `null`, never a
 * "No validator note" placeholder), the D-02 ranked-alternative chips, an
 * "Accept" button, and the manual full-column dropdown escape hatch
 * (D-02c). Resolving any of the three ways is the parent's job
 * (`state/review.ts`'s pure functions) -- this component only reports
 * intent through its callback props.
 */
export function FieldRow({
  mapping,
  sourceColumns,
  onResolveByChip,
  onResolveByAccept,
  onResolveByDropdown,
  onReopen,
}: FieldRowProps) {
  const [showReasoning, setShowReasoning] = useState(false);

  if (!mapping.needs_confirmation) {
    const confidencePct = Math.round(mapping.confidence * 100);
    return (
      <div className="flex flex-col gap-2 border-l-4 border-success bg-success-bg px-4 py-3 transition-colors duration-150">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="size-4 shrink-0 text-success" />
          <span className="text-body font-semibold">{mapping.target_field}</span>
          <span className="text-mono-label text-muted-foreground">
            {mapping.source_column ?? (mapping.inferred_value ? `(inferred) ${mapping.inferred_value}` : "(no column)")}
          </span>
          <span className="text-mono-label font-semibold text-success">{confidencePct}%</span>
          <button
            type="button"
            className="ml-auto text-label text-muted-foreground underline-offset-2 hover:underline"
            onClick={() => setShowReasoning((v) => !v)}
          >
            Why?
          </button>
          <button
            type="button"
            className="text-label text-muted-foreground underline-offset-2 hover:underline"
            onClick={onReopen}
          >
            Change column
          </button>
        </div>
        {showReasoning && <p className="text-body text-muted-foreground">{mapping.reasoning}</p>}
      </div>
    );
  }

  const inferredOnly = mapping.source_column === null && mapping.inferred_value !== null;

  return (
    <div className="flex flex-col gap-3 border-l-4 border-uncertain bg-uncertain-bg px-4 py-3 transition-colors duration-150">
      <div className="flex items-center gap-2">
        <AlertTriangle className="size-4 shrink-0 text-uncertain-foreground" />
        <span className="text-body font-semibold text-uncertain-foreground">{mapping.target_field}</span>
        <span className="rounded-full bg-uncertain px-2 py-0.5 text-xs font-medium text-uncertain-foreground">
          Needs review
        </span>
      </div>

      {inferredOnly && (
        <p className="text-mono-label text-uncertain-foreground">
          <span className="text-muted-foreground">(inferred)</span> {mapping.inferred_value}
        </p>
      )}

      <p className="flex items-start gap-2 text-body text-uncertain-foreground">
        <Sparkles className="mt-0.5 size-4 shrink-0" />
        <span>{mapping.reasoning}</span>
      </p>

      {mapping.validator_note && (
        <p className="flex items-start gap-2 text-body text-uncertain-foreground">
          <FlaskConical className="mt-0.5 size-4 shrink-0" />
          <span>{mapping.validator_note}</span>
        </p>
      )}

      {mapping.alternatives.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {mapping.alternatives.map((candidate) => (
            <ConfidenceChip
              key={candidate.source_column}
              candidate={candidate}
              onSelect={() => onResolveByChip(candidate)}
            />
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          className="border-primary/40 text-primary hover:bg-primary/10"
          onClick={onResolveByAccept}
        >
          Accept
        </Button>
        <Select onValueChange={(value) => onResolveByDropdown(String(value))}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Choose a different column…" />
          </SelectTrigger>
          <SelectContent>
            {sourceColumns.map((column) => (
              <SelectItem key={column} value={column}>
                {column}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
