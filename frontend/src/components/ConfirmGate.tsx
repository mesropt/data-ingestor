import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ConfirmGateProps {
  clear: number;
  total: number;
  ready: boolean;
  submitting: boolean;
  onConfirm: () => void;
}

/**
 * The confirm/export control (UI-05) -- progress text left ("{n} of
 * {total} resolved"), the "Confirm & Save Mapping" CTA right. `disabled`
 * derives DIRECTLY from `ready` (the caller's `state/review.ts::isReady`,
 * itself a mirror of `domain/models.py::MappingProposal.is_ready`) --
 * never a separately-computed heuristic (T-04-19). The server
 * independently re-validates on `/api/confirm` (P1); this button is a UX
 * convenience, not the authority -- a 422 rejection is handled by the
 * caller (`Review.tsx`), which never lets this component's own local
 * state believe the confirm succeeded.
 */
export function ConfirmGate({ clear, total, ready, submitting, onConfirm }: ConfirmGateProps) {
  const remaining = total - clear;
  const confirmButton = (
    <Button type="button" disabled={!ready || submitting} onClick={onConfirm}>
      {submitting && <Loader2 className="size-4 animate-spin" />}
      Confirm & Save Mapping
    </Button>
  );

  return (
    <div className="flex h-16 shrink-0 items-center justify-between border-t border-border bg-secondary px-6">
      <span className="text-label text-muted-foreground">
        {clear} of {total} resolved
      </span>
      {!ready ? (
        <Tooltip>
          <TooltipTrigger render={confirmButton} />
          <TooltipContent>Resolve {remaining} more uncertain field(s) before confirming.</TooltipContent>
        </Tooltip>
      ) : (
        confirmButton
      )}
    </div>
  );
}
