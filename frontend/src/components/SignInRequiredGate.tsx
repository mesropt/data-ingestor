import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface SignInRequiredGateProps {
  onSignIn: () => void;
  onCreateAccount: () => void;
}

/**
 * The app-wide signed-out interstitial for Schemas/Upload/Review (INGEST-06,
 * D-10-13, 10-UI-SPEC Discretion §3) -- `App.tsx` renders this in place of
 * those three tabs' real content whenever `!signedIn`. Docs stays open (a
 * prospective user reading what the tool does before creating an account is
 * a deliberate exception, not an oversight); this gate never covers Docs.
 *
 * Identical centered-`Card` idiom to Sign Up / Sign In (`max-w-[420px]`, `xl`
 * top padding) for the "no layout jump between auth-adjacent screens" reason
 * established in `06-UI-SPEC.md`. `ShieldAlert` (muted) matches the existing
 * "auth-required" icon convention already used on `ConfirmGate`'s signed-out
 * tier. One static state only -- the session probe's own loading treatment
 * already lives in `AppShell`'s `SignedInIndicator`, unchanged.
 */
export function SignInRequiredGate({ onSignIn, onCreateAccount }: SignInRequiredGateProps) {
  return (
    <div className="mx-auto flex max-w-[420px] flex-col pt-8">
      <Card>
        <CardContent className="flex flex-col items-center gap-6 text-center">
          <ShieldAlert className="size-8 text-muted-foreground" aria-hidden />
          <div className="flex flex-col gap-2">
            <h1 className="text-display">Sign in to use Data Ingestor</h1>
            <p className="text-body text-muted-foreground">
              Every Schema, upload, and mapping is tied to a signed-in identity — sign in or create an
              account to continue.
            </p>
          </div>
          <div className="flex w-full flex-col gap-2">
            <Button type="button" className="w-full" onClick={onSignIn}>
              Sign In
            </Button>
            <Button type="button" variant="outline" className="w-full" onClick={onCreateAccount}>
              Create Account
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
