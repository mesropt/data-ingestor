import { RefreshCw } from "lucide-react";

/** Built out fully in Task 3 (UI-06) -- a minimal-but-real placeholder
 * here so Review.tsx compiles and its conditional render (only when
 * `isAutoApplied(mapping.provenance)`) is wired correctly at this task's
 * commit boundary, mirroring 04-05's precedent for mutually-dependent
 * files split across task commits. */
export function ProfileAppliedBanner() {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3">
      <RefreshCw className="size-4 shrink-0 text-primary" />
      <p className="text-body text-foreground">Auto-mapped from a saved profile — 0 Claude calls.</p>
    </div>
  );
}
