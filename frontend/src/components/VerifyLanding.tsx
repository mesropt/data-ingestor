import { useEffect, useState } from "react";
import { Loader2, Mail, MailCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { verifyEmail } from "@/lib/api";

interface VerifyLandingProps {
  /** Navigate to Sign In (the single CTA in every resolved state). */
  onSignIn: () => void;
}

type VerifyPhase = "pending" | "verified" | "expired";

/** Reads the `token` query param off the console-printed `/verify?token=...`
 * link. A missing token is treated as an expired/invalid link (same terminal
 * state), never a crash. */
function tokenFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("token");
}

/**
 * Email Verification Landing (06-UI-SPEC Screen 3, AUTH-03) -- reached only
 * via the console-printed link. On mount it calls `GET /api/auth/verify` and
 * shows a single centered result (no form): `MailCheck` in success-green for
 * a verified token, a muted `Mail` for an expired/invalid one (an expired
 * link is an expected lifecycle state, not a user error → not destructive
 * red). Near-instant local DB lookup, so a bare spinner covers the pending
 * window with no skeleton.
 */
export function VerifyLanding({ onSignIn }: VerifyLandingProps) {
  const [phase, setPhase] = useState<VerifyPhase>("pending");

  useEffect(() => {
    let active = true;
    const token = tokenFromUrl();
    if (!token) {
      setPhase("expired");
      return;
    }
    verifyEmail(token)
      .then((result) => {
        if (active) setPhase(result.status === "verified" ? "verified" : "expired");
      })
      .catch(() => {
        // Any ApiError (400/404/expired token) lands in the same terminal
        // "expired" state -- the SPA never surfaces a raw error here.
        if (active) setPhase("expired");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mx-auto flex max-w-[420px] flex-col pt-8">
      <Card>
        <CardContent className="flex flex-col items-center gap-4 py-4 text-center">
          {phase === "pending" && <Loader2 className="size-8 animate-spin text-muted-foreground" />}

          {phase === "verified" && (
            <>
              <MailCheck className="size-8 text-success" />
              <h1 className="text-display">Email Verified</h1>
              <p className="text-body text-muted-foreground">
                Your email is confirmed. You can now sign in and confirm mappings.
              </p>
              <Button type="button" className="w-full" onClick={onSignIn}>
                Sign In
              </Button>
            </>
          )}

          {phase === "expired" && (
            <>
              <Mail className="size-8 text-muted-foreground" />
              <h1 className="text-display">This link has expired</h1>
              <p className="text-body text-muted-foreground">
                Verification links are single-use and time-limited. Sign in and request a new one from your
                account.
              </p>
              <Button type="button" className="w-full" onClick={onSignIn}>
                Sign In
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
