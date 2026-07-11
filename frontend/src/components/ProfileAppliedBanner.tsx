import { RefreshCw } from "lucide-react";

/**
 * API-03 auto-apply transparency indicator (UI-06, the second half of the
 * demo money shot). Rendered above the two-pane region only when the
 * upload response's `provenance` is `"auto-applied-from-profile"`
 * (`Review.tsx`'s `isAutoApplied` gate, `state/review.ts`) -- meaning the
 * confirmed+saved profile from a PRIOR upload matched this file's column
 * signature and the mapping came back with zero `needs_confirmation`
 * fields, no Claude call made. Deliberately `accent` (teal, the same
 * `--primary` token as the primary CTA) toned rather than `success`
 * (green) or `uncertain` (amber): this is a PROVENANCE signal about where
 * the mapping came from, not a field-clear-state signal -- 04-UI-SPEC.md's
 * Color section reserves the success/green hue exclusively for a clear
 * `FieldRow`'s left border, never for a banner like this one. "Not right?
 * Edit anyway." is intentionally a no-op link -- the FieldRows underneath
 * are already all clear and remain fully editable via the same D-02
 * chip/Accept/dropdown controls if the curator disagrees with the
 * auto-applied mapping.
 */
export function ProfileAppliedBanner() {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3">
      <RefreshCw className="size-4 shrink-0 text-primary" />
      <p className="text-body text-foreground">
        Auto-mapped from a saved profile — 0 Claude calls.{" "}
        <button type="button" className="text-primary underline-offset-2 hover:underline">
          Not right? Edit anyway.
        </button>
      </p>
    </div>
  );
}
