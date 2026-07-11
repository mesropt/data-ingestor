import { useEffect, useRef, useState } from "react";
import { Paperclip, ShieldAlert, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ApiError, listSchemas } from "@/lib/api";
import type { SchemaSummary } from "@/lib/types";

interface MapFileControlsProps {
  /** The currently-selected target Schema name (owned by Upload) + the vendor
   * label + the attached map file, all surfaced up via callbacks so Upload can
   * thread them into `uploadFile(..., {mapFile, schemaName, vendor})`. */
  schemaName: string | null;
  onSchemaNameChange: (name: string) => void;
  vendor: string;
  onVendorChange: (vendor: string) => void;
  mapFile: File | null;
  onMapFileChange: (file: File | null) => void;
  /** Auth mirror (Plan 06 / D-08-05): the map-file attach affordance is enabled
   * only when signedIn AND verified, because attaching a map file augments the
   * governed master crosswalk. This is a UX mirror only -- the server re-checks
   * `require_verified_user` on the augmenting path (T-08-12). */
  signedIn: boolean;
  verified: boolean;
  disabled?: boolean;
  /** Signed-out affordance: route to Sign In (mirrors SchemaControls). */
  onRequireSignIn: () => void;
}

/**
 * The optional Phase-08 reconcile ingress controls (D-08-06, RECON-01): pick a
 * target Schema, set a vendor label, and optionally attach a map file (a Phase
 * 07 master-map JSON envelope) alongside the CSV/Excel before uploading. When a
 * map file is attached its aliases augment the target Schema's crosswalk before
 * Claude maps the file; a map-file-vs-master conflict surfaces the inline
 * `ReconcilePanel`. Attaching is a governed mutation, gated on the
 * signed-in/verified mirror (the server is the authority, T-08-12); the plain
 * upload path (no map file) stays open exactly as today.
 */
export function MapFileControls({
  schemaName,
  onSchemaNameChange,
  vendor,
  onVendorChange,
  mapFile,
  onMapFileChange,
  signedIn,
  verified,
  disabled,
  onRequireSignIn,
}: MapFileControlsProps) {
  const [schemas, setSchemas] = useState<SchemaSummary[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mirrors state/auth.ts::isGovernedActionAllowed -- attaching a map file
  // augments the master, so it needs the same signed-in + verified mirror
  // SchemaControls uses. The server re-enforces the gate regardless (P2).
  const governed = signedIn && verified;

  useEffect(() => {
    listSchemas()
      .then(setSchemas)
      .catch((err: unknown) => {
        const fallback = "Couldn't load Schemas right now.";
        toast.error(err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback);
      });
  }, []);

  function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    // Reset so choosing the same file twice still fires onChange.
    event.target.value = "";
    onMapFileChange(file);
  }

  const attachButton = (
    <Button
      type="button"
      variant="outline"
      disabled={disabled || !governed}
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
          Attach a master-map file to apply a vendor's known aliases before Claude maps the file.
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="mapfile-schema">Target Schema</Label>
          <Select
            value={schemaName ?? undefined}
            onValueChange={(value) => onSchemaNameChange(String(value))}
            disabled={disabled || schemas.length === 0}
          >
            <SelectTrigger id="mapfile-schema" className="w-56">
              <SelectValue placeholder={schemas.length === 0 ? "No schemas yet" : "Choose a Schema…"} />
            </SelectTrigger>
            <SelectContent>
              {schemas.map((schema) => (
                <SelectItem key={schema.id} value={schema.name}>
                  {schema.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="mapfile-vendor">Vendor (source label)</Label>
          <Input
            id="mapfile-vendor"
            value={vendor}
            placeholder="e.g. novascreen"
            className="w-56"
            disabled={disabled}
            onChange={(event) => onVendorChange(event.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Map file</Label>
          {signedIn && !verified ? (
            <Tooltip>
              <TooltipTrigger render={attachButton} />
              <TooltipContent>Verify your email to attach a map file.</TooltipContent>
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
