import { Globe } from "lucide-react";

import { Button } from "@/components/ui/button";

interface GoogleSignInButtonProps {
  /** The `/api/auth/config` `google_oauth_enabled` flag. When false the
   * button renders `null` entirely (not a disabled/dead button) -- the
   * parent already guards, but this stays self-guarding. */
  enabled: boolean;
}

/**
 * "Continue with Google" (AUTH-02, D-06-05) -- a full-width outline button
 * that navigates the browser to the server's OAuth entry point. Renders only
 * when the backend reports the flag on (off by default → absent).
 *
 * 06-UI-SPEC Registry Safety FLAG: the generic lucide `Globe` icon is a
 * PLACEHOLDER, not Google's official multi-color "G" brand mark. (The
 * UI-SPEC named `Chrome`, which this lucide-react version no longer exports;
 * `Globe` is an equivalent generic stand-in and keeps the FLAG's intent --
 * NOT a Google brand asset.) Acceptable for the flag-off-by-default overnight
 * build; swap in Google's real brand asset per Google's sign-in branding
 * guidelines before any public, flag-on demo (a trademark concern, not a
 * design-token one).
 */
export function GoogleSignInButton({ enabled }: GoogleSignInButtonProps) {
  if (!enabled) {
    return null;
  }
  return (
    <Button
      type="button"
      variant="outline"
      className="w-full"
      onClick={() => {
        // Full-page navigation to the server-side OAuth redirect (not a
        // fetch) -- the browser follows Google's consent flow and lands
        // back on the SPA via the callback route.
        window.location.href = "/api/auth/google/login";
      }}
    >
      <Globe className="size-4" />
      Continue with Google
    </Button>
  );
}
