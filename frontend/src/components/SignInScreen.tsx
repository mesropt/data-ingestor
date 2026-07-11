import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthDivider } from "@/components/AuthDivider";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { ApiError, signIn } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface SignInScreenProps {
  /** `/api/auth/config` google flag -- gates the Google block (D-06-05). */
  googleEnabled: boolean;
  /** True when reached via the ConfirmGate "Sign In to Confirm" affordance
   * (not a fresh nav) -- renders one muted contextual line (D-06-07). */
  redirectedFromConfirm?: boolean;
  /** Parent (App) updates the auth store, fires the "Signed in as {email}."
   * toast, closes the overlay, and honors any returnTo (06-UI-SPEC). */
  onSignedIn: (user: AuthUser) => void;
  /** Cross-link -> switch to Sign Up. */
  onSwitchToSignUp: () => void;
}

/**
 * Sign In (06-UI-SPEC Screen 2) -- the same `max-w-[420px]` Card layout as
 * Sign Up for visual symmetry. Calls `signIn`; on success the parent handles
 * the session/toast/redirect. Bad credentials show a destructive inline
 * Alert and clear ONLY the password (the email stays for convenience). An
 * unverified user still signs in fine here (D-06-04) -- verification gates a
 * governed action later (ConfirmGate), never Sign In itself.
 */
export function SignInScreen({
  googleEnabled,
  redirectedFromConfirm = false,
  onSignedIn,
  onSwitchToSignUp,
}: SignInScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await signIn({ email, password });
      onSignedIn(user);
    } catch (err) {
      if (err instanceof ApiError) {
        setError("That email and password don't match. Nothing was changed — try again.");
        setPassword("");
      } else {
        setError("We couldn't sign you in right now. Nothing was changed — try again in a moment.");
      }
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[420px] flex-col pt-8">
      <Card>
        <CardContent className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-display">Sign In</h1>
            {redirectedFromConfirm && (
              <p className="text-body text-muted-foreground">Sign in to confirm your mapping.</p>
            )}
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="signin-email">Email</Label>
              <Input
                id="signin-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="signin-password">Password</Label>
              <Input
                id="signin-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <Button type="submit" className="w-full" disabled={submitting || !email || !password}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {submitting ? "Signing in…" : "Sign In"}
            </Button>
          </form>

          {googleEnabled && (
            <div className="flex flex-col gap-2">
              <AuthDivider />
              <GoogleSignInButton enabled={googleEnabled} />
            </div>
          )}

          <p className="text-body text-muted-foreground">
            Don't have an account?{" "}
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 align-baseline"
              onClick={onSwitchToSignUp}
            >
              Sign up
            </Button>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
