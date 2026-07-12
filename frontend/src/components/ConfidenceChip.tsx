import { cn } from "@/lib/utils";
import type { AlternativeOut } from "@/lib/types";

interface ConfidenceChipProps {
  candidate: AlternativeOut;
  onSelect: () => void;
}

/**
 * One ranked-alternative column (D-02a) -- "{column} · {confidence%}" in
 * mono/tabular-nums, per 04-UI-SPEC.md. Clicking resolves the field to
 * this column and clears its amber state (the parent, `FieldRow`, owns
 * what "resolves" means). The 32px minimum clickable height is the
 * documented desktop-first exception to the general 44px touch-target
 * guideline (04-UI-SPEC.md Spacing Scale).
 */
export function ConfidenceChip({ candidate, onSelect }: ConfidenceChipProps) {
  const confidencePct = Math.round(candidate.confidence * 100);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full border border-primary/40 bg-card px-3 text-mono-label transition-colors",
        "hover:border-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <span className="max-w-40 truncate text-foreground">{candidate.source_column}</span>
      <span className="font-semibold text-primary">{confidencePct}%</span>
    </button>
  );
}
