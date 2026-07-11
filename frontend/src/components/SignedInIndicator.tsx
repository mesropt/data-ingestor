import { LogOut, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AuthState } from "@/state/auth";

interface SignedInIndicatorProps {
  /** The auth store's current state (probing / signedOut / signedIn). */
  state: AuthState;
  /** Open the Sign In overlay (signed-out and probing slots). */
  onSignIn: () => void;
  /** Sign out: the parent (App) performs the API call, updates the store,
   * and fires the "Signed out." toast -- this chip stays presentational. */
  onSignOut: () => void;
}

/**
 * The AppShell trailing identity chip (06-UI-SPEC Screen 4). Signed-in shows
 * a quiet `UserRound` icon + the email in `.text-mono-label` (attribution
 * metadata, not an account menu -- the email is NOT clickable) + an icon-only
 * ghost Sign Out button. Signed-out shows a single outline "Sign In" button
 * in the SAME slot (never a blank gap, so the bar width doesn't shift).
 * Probing renders that Sign In slot at low opacity to avoid a layout shift
 * once the sub-second session probe resolves.
 */
export function SignedInIndicator({ state, onSignIn, onSignOut }: SignedInIndicatorProps) {
  if (state.phase === "signedIn") {
    return (
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1">
          <UserRound className="size-4 text-muted-foreground" />
          <span className="max-w-[160px] truncate text-mono-label">{state.user.email}</span>
        </span>
        <Tooltip>
          <TooltipTrigger
            render={
              <Button type="button" variant="ghost" size="icon" aria-label="Sign Out" onClick={onSignOut}>
                <LogOut className="size-4" />
              </Button>
            }
          />
          <TooltipContent>Sign Out</TooltipContent>
        </Tooltip>
      </div>
    );
  }

  const probing = state.phase === "probing";
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={onSignIn}
      className={probing ? "pointer-events-none opacity-50" : undefined}
      aria-hidden={probing}
    >
      Sign In
    </Button>
  );
}
