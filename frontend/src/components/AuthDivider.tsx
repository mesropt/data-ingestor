import { Separator } from "@/components/ui/separator";

/**
 * The "or" row between the email/password form and the Google button
 * (06-UI-SPEC Screens 1-2). Rendered ONLY alongside `GoogleSignInButton` --
 * never an orphaned "or" with nothing below it (Copywriting Contract).
 */
export function AuthDivider() {
  return (
    <div className="flex items-center gap-2">
      <Separator className="flex-1" />
      <span className="text-label text-muted-foreground">or</span>
      <Separator className="flex-1" />
    </div>
  );
}
