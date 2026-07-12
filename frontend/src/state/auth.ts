/**
 * The auth surface's state machine (D-06-07, AUTH-01/02/03) -- a pure reducer
 * with NO React dependency, so vitest covers the probing -> signedIn |
 * signedOut transitions (and the returnTo round-trip a redirected-from-Confirm
 * sign-in needs) without rendering anything, mirroring `state/upload.ts`'s
 * own "logic is tested, rendering is gsd-ui-checker-validated" split.
 *
 * This is strictly the UX mirror of plan 06-02's server-side gate: the
 * selectors here reflect only the last server-resolved user, and the
 * authoritative verified/authenticated check always re-runs server-side on
 * `/api/confirm` (P1, T-06-14) -- a tampered client that forces a selector
 * true still gets 401/403 from the endpoint.
 */

import type { AuthUser } from "../lib/types";

export type AuthState =
  | { phase: "probing" }
  | { phase: "signedOut"; returnTo?: string }
  | { phase: "signedIn"; user: AuthUser; returnTo?: string };

export type AuthAction =
  | { type: "SESSION_RESOLVED"; user: AuthUser | null }
  | { type: "SIGN_IN_SUCCESS"; user: AuthUser }
  | { type: "SIGN_OUT" }
  | { type: "SET_RETURN_TO"; returnTo: string | undefined };

export const initialAuthState: AuthState = { phase: "probing" };

/** The pending post-sign-in destination carried on whichever phase holds it
 * -- read so it survives a SIGN_IN_SUCCESS (the "Sign In to Confirm" flow
 * stamps it while signedOut, and App reads it off the resulting signedIn
 * state to route back to Review). */
function returnToOf(state: AuthState): string | undefined {
  return "returnTo" in state ? state.returnTo : undefined;
}

export function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "SESSION_RESOLVED": {
      const returnTo = returnToOf(state);
      return action.user
        ? { phase: "signedIn", user: action.user, ...(returnTo ? { returnTo } : {}) }
        : { phase: "signedOut", ...(returnTo ? { returnTo } : {}) };
    }

    case "SIGN_IN_SUCCESS": {
      const returnTo = returnToOf(state);
      return { phase: "signedIn", user: action.user, ...(returnTo ? { returnTo } : {}) };
    }

    case "SIGN_OUT":
      return { phase: "signedOut" };

    case "SET_RETURN_TO":
      // Too early to know signed-in status -- SESSION_RESOLVED hasn't landed
      // yet, so forcing signedOut here would misrepresent a signed-in
      // resolution that's already in flight. No-op: preserve state as-is.
      if (state.phase === "probing") {
        return state;
      }
      // Stamp the destination without changing who is (or isn't) signed in.
      if (state.phase === "signedIn") {
        return { ...state, returnTo: action.returnTo };
      }
      return { phase: "signedOut", ...(action.returnTo ? { returnTo: action.returnTo } : {}) };

    default:
      return state;
  }
}

/** True only in the signedIn phase. */
export function isSignedIn(state: AuthState): boolean {
  return state.phase === "signedIn";
}

/** True only when signedIn AND the resolved user is verified. */
export function isVerified(state: AuthState): boolean {
  return state.phase === "signedIn" && state.user.is_verified;
}

/** The UI mirror of the server's `require_verified_user`: a governed action
 * (Confirm & Save) is allowed only when signedIn AND verified. Never the
 * authority -- the server re-checks every confirm (P1, T-06-14). */
export function isGovernedActionAllowed(state: AuthState): boolean {
  return isSignedIn(state) && isVerified(state);
}
