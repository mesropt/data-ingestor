import { Loader2, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ConfirmGateProps {
  clear: number;
  total: number;
  ready: boolean;
  submitting: boolean;
  onConfirm: () => void;
  /** Auth mirror (Plan 06, 06-UI-SPEC Screen 5): whether a user is signed in
   * and whether that user is verified. These add TWO independent disable
   * reasons composed ON TOP of the existing `ready` gate -- they never
   * replace or weaken it. */
  signedIn: boolean;
  verified: boolean;
  /** Signed-out affordance: routes to Sign In carrying a returnTo back to
   * Review (the "Sign In to Confirm" button is actionable, not inert). */
  onRequireSignIn: () => void;
}

/**
 * The confirm/export control (UI-05) -- now composing the auth-gate mirror
 * (06-UI-SPEC Screen 5) with the existing readiness gate. Four mutually
 * exclusive priority tiers, auth first (mirrors the server's
 * `require_verified_user` check order, D-06-06):
 *   1. Signed out  → actionable "Sign In to Confirm" (outline, ShieldAlert),
 *      routes to Sign In with a returnTo. NOT the greyed disabled treatment,
 *      since it IS clickable.
 *   2. Signed in, unverified → the existing disabled treatment, label
 *      unchanged, "verify your email" tooltip.
 *   3. Signed in, verified, !ready → the existing "Resolve {n} more…"
 *      disabled behavior, UNCHANGED.
 *   4. Signed in, verified, ready → the existing enabled Confirm, UNCHANGED.
 * Never more than one tier's copy at once. The server independently
 * re-validates on `/api/confirm` (P1, T-06-12): this button is a UX mirror,
 * never the authority -- a tampered client still gets 401/403.
 */
export function ConfirmGate({
  clear,
  total,
  ready,
  submitting,
  onConfirm,
  signedIn,
  verified,
  onRequireSignIn,
}: ConfirmGateProps) {
  const remaining = total - clear;

  const progress = (
    <span className="text-label text-muted-foreground">
      {clear} of {total} resolved
    </span>
  );

  // Tier 1: signed out -- a distinct, actionable affordance (not disabled).
  if (!signedIn) {
    const signInButton = (
      <Button type="button" variant="outline" onClick={onRequireSignIn}>
        <ShieldAlert className="size-4" />
        Sign In to Confirm
      </Button>
    );
    return (
      <div className="flex h-16 shrink-0 items-center justify-between border-t border-border bg-secondary px-6">
        {progress}
        <Tooltip>
          <TooltipTrigger render={signInButton} />
          <TooltipContent>Sign in to confirm this mapping.</TooltipContent>
        </Tooltip>
      </div>
    );
  }

  // Tiers 2-4: signed in. The auth (verified) and readiness (ready) reasons
  // both feed the SAME disabled flag, but each keeps its own distinct copy.
  const confirmButton = (
    <Button type="button" disabled={!verified || !ready || submitting} onClick={onConfirm}>
      {submitting && <Loader2 className="size-4 animate-spin" />}
      Confirm & Save Mapping
    </Button>
  );

  let gated = confirmButton;
  if (!verified) {
    gated = (
      <Tooltip>
        <TooltipTrigger render={confirmButton} />
        <TooltipContent>Verify your email to confirm this mapping.</TooltipContent>
      </Tooltip>
    );
  } else if (!ready) {
    gated = (
      <Tooltip>
        <TooltipTrigger render={confirmButton} />
        <TooltipContent>Resolve {remaining} more uncertain field(s) before confirming.</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div className="flex h-16 shrink-0 items-center justify-between border-t border-border bg-secondary px-6">
      {progress}
      {gated}
    </div>
  );
}
