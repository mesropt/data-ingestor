import { useState, type FormEvent } from "react";
import { Loader2, Mail } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthDivider } from "@/components/AuthDivider";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { ApiError, signUp } from "@/lib/api";

interface SignUpScreenProps {
  /** `/api/auth/config` google flag -- gates the Google block (D-06-05). */
  googleEnabled: boolean;
  /** Cross-link + post-success "Sign in now" -> switch to Sign In. */
  onSwitchToSignIn: () => void;
}

/** Renders the server's own consequence-first message on an ApiError,
 * falling back to a generic line (mirrors Upload.tsx's `consequenceMessage`
 * / api.ts's "render the server's own message" discipline). */
function signUpErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === "string") {
    return `${error.detail} Fix the highlighted field and try again.`;
  }
  return "We couldn't create your account right now. Nothing was saved — try again in a moment.";
}

/**
 * Sign Up (06-UI-SPEC Screen 1) -- a centered `max-w-[420px]` Card with an
 * email + password form. On success the card body is REPLACED (not stacked)
 * by the amber "check your server console" notice, since this dev build logs
 * the verification link to the console rather than emailing it (D-06-04).
 * All copy/tokens come from 06-UI-SPEC; no new token or primitive.
 */
export function SignUpScreen({ googleEnabled, onSwitchToSignIn }: SignUpScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [succeeded, setSucceeded] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signUp({ email, password });
      setSucceeded(true);
    } catch (err) {
      setError(signUpErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[420px] flex-col pt-8">
      <Card>
        <CardContent className="flex flex-col gap-6">
          {succeeded ? (
            <>
              <Alert className="border-uncertain bg-uncertain-bg text-uncertain-foreground">
                <Mail className="size-4" />
                <AlertTitle>Check your server console</AlertTitle>
                <AlertDescription className="text-uncertain-foreground/90">
                  We've created your account. This dev build prints your verification link to the server console
                  instead of emailing it — copy it from there and open it to verify.
                </AlertDescription>
              </Alert>
              <Button type="button" variant="outline" className="w-full" onClick={onSwitchToSignIn}>
                Sign in now
              </Button>
            </>
          ) : (
            <>
              <h1 className="text-display">Sign Up</h1>

              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="signup-email">Email</Label>
                  <Input
                    id="signup-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={submitting}
                    required
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="signup-password">Password</Label>
                  <Input
                    id="signup-password"
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={submitting}
                    required
                  />
                  <p className="text-body text-muted-foreground">At least 8 characters.</p>
                </div>

                <Button type="submit" className="w-full" disabled={submitting || !email || !password}>
                  {submitting && <Loader2 className="size-4 animate-spin" />}
                  {submitting ? "Creating…" : "Create Account"}
                </Button>
              </form>

              {googleEnabled && (
                <div className="flex flex-col gap-2">
                  <AuthDivider />
                  <GoogleSignInButton enabled={googleEnabled} />
                </div>
              )}

              <p className="text-body text-muted-foreground">
                Already have an account?{" "}
                <Button
                  type="button"
                  variant="link"
                  className="h-auto p-0 align-baseline"
                  onClick={onSwitchToSignIn}
                >
                  Sign in
                </Button>
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
