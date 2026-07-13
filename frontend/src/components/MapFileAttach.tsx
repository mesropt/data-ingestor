import { useRef } from "react";
import { Paperclip, ShieldAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface MapFileAttachProps {
  /** The Schema Upload's `SchemaPicker` (control #1) already resolved --
   * `MapFileAttach` has no Schema select of its own (D-10-01/02): a second
   * selector here could silently disagree with the one fixing the mapping
   * target. `null` before a Schema is chosen; the helper copy adapts. */
  schemaName: string | null;
  /** Read-only here: the curator names the vendor ONCE, on the Upload screen
   * above. A map file's aliases are recorded against it, so this component
   * still needs the value -- it just no longer asks for it a second time. */
  vendor: string;
  mapFile: File | null;
  onMapFileChange: (file: File | null) => void;
  /** Auth mirror (Plan 06 / D-08-05): the map-file attach affordance is
   * enabled only when signedIn AND verified, because attaching a map file
   * augments the governed master crosswalk. This is a UX mirror only -- the
   * server re-checks `require_verified_user` on the augmenting path
   * (T-08-12). */
  signedIn: boolean;
  verified: boolean;
  disabled?: boolean;
  /** Signed-out affordance: route to Sign In (mirrors ConfirmGate). */
  onRequireSignIn: () => void;
}

/**
 * The simplified Phase-08 reconcile ingress (replacing `MapFileControls`,
 * D-10-01/02): a vendor label + an optional map-file attach against the
 * ALREADY-chosen Schema (control #1) -- no Schema select of its own. When a
 * map file is attached its aliases augment the target Schema's crosswalk
 * before Claude maps the file; a map-file-vs-master conflict still surfaces
 * the inline `ReconcilePanel`. Attaching is a governed mutation, gated on
 * the signed-in/verified mirror (the server is the authority, T-08-12); the
 * plain upload path (no map file) stays open exactly as today.
 */
export function MapFileAttach({
  schemaName,
  vendor,
  mapFile,
  onMapFileChange,
  signedIn,
  verified,
  disabled,
  onRequireSignIn,
}: MapFileAttachProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    // Reset so choosing the same file twice still fires onChange.
    event.target.value = "";
    onMapFileChange(file);
  }

  // Signed-out stays CLICKABLE (routes to onRequireSignIn, mirroring
  // ConfirmGate's "Sign In to Confirm") -- only the signed-in-but-unverified
  // tier is disabled, never disabled merely for being signed out.
  const attachButton = (
    <Button
      type="button"
      variant="outline"
      disabled={disabled || (signedIn && !verified)}
      onClick={() => (signedIn ? fileInputRef.current?.click() : onRequireSignIn())}
    >
      {!signedIn ? <ShieldAlert className="size-4" /> : <Paperclip className="size-4" />}
      Attach map file
    </Button>
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex flex-col gap-0.5">
        <p className="text-body font-medium">Reconcile against a Schema (optional)</p>
        <p className="text-body text-muted-foreground">
          Attach a master-map file to apply{" "}
          <span className="font-medium">{vendor.trim() || "this vendor"}</span>'s known aliases to{" "}
          <span className="font-medium">{schemaName ?? "the chosen Schema"}</span> before mapping.
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-col gap-1.5">
          <Label>Map file</Label>
          {signedIn && !verified ? (
            <Tooltip>
              <TooltipTrigger render={attachButton} />
              <TooltipContent>Verify your email to attach a map file.</TooltipContent>
            </Tooltip>
          ) : !signedIn ? (
            <Tooltip>
              <TooltipTrigger render={attachButton} />
              <TooltipContent>Sign in to attach a map file.</TooltipContent>
            </Tooltip>
          ) : (
            attachButton
          )}
        </div>
      </div>

      {mapFile && (
        <div className="flex items-center gap-2 text-body text-muted-foreground">
          <Paperclip className="size-4" />
          <span className="font-mono">{mapFile.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => onMapFileChange(null)}
          >
            <X className="size-4" />
            Remove
          </Button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={onFileChosen}
      />
    </div>
  );
}
