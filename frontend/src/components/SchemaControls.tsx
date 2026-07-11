import { useRef, useState } from "react";
import { Download, Loader2, ShieldAlert, Upload as UploadIcon } from "lucide-react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
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
import { ApiError, importMasterMap, masterMapDownloadUrl, promoteSchema } from "@/lib/api";
import type { FieldSetPayload, MasterMapEnvelope, SchemaSummary } from "@/lib/types";

interface SchemaControlsProps {
  /** The governed Schema list (from `listSchemas`, mirrored in Review's
   * `state/schema.ts` reducer) + the currently-selected name. */
  schemas: SchemaSummary[];
  selected: string | null;
  onSelect: (name: string) => void;
  /** The current editor field set -- promoted verbatim into a new Schema. */
  fieldSet: FieldSetPayload;
  /** Auth mirror (Plan 06): promote/import are enabled only when signedIn AND
   * verified -- exactly `state/auth.ts::isGovernedActionAllowed`. The server
   * re-checks `require_verified_user` on every mutation regardless (P1). */
  signedIn: boolean;
  verified: boolean;
  /** The vendor label threaded into the confirm crosswalk write (ALIAS-04);
   * owned by Review so `handleConfirm` can read it. */
  vendor: string;
  onVendorChange: (vendor: string) => void;
  /** Re-fetch the Schema list after a promote/import mutates it. */
  onReloadSchemas: () => void;
  /** Signed-out affordance: route to Sign In carrying a returnTo (mirrors
   * ConfirmGate's "Sign In to Confirm"). */
  onRequireSignIn: () => void;
}

/**
 * The minimal Phase-07 crosswalk controls (D-07-07): promote the current
 * field set into a governed Schema, pick an existing Schema, download /
 * import its master-map file, and set the vendor label the confirm will
 * accrete aliases under. Controls only -- the rich visual crosswalk registry
 * table and Docs page are Phase 09, deliberately NOT built here.
 *
 * Promote + Import are governed mutations, gated on the signed-in/verified
 * mirror (the server is the actual authority, T-07-14); Download is a plain
 * `<a download>` GET (a public read, mirroring ExportBar). A malformed or
 * hostile imported file cannot bypass the server's re-validation (T-07-15) --
 * the browser parses JSON only for convenience.
 */
export function SchemaControls({
  schemas,
  selected,
  onSelect,
  fieldSet,
  signedIn,
  verified,
  vendor,
  onVendorChange,
  onReloadSchemas,
  onRequireSignIn,
}: SchemaControlsProps) {
  const [promoteName, setPromoteName] = useState("");
  const [promoting, setPromoting] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Mirrors state/auth.ts::isGovernedActionAllowed -- Review passes the same
  // two booleans ConfirmGate already receives, so the gate stays a UX mirror.
  const governed = signedIn && verified;

  function reportApiError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      toast.error(typeof err.detail === "string" ? err.detail : fallback);
    } else {
      toast.error(fallback);
    }
  }

  async function handlePromote() {
    if (!signedIn) {
      onRequireSignIn();
      return;
    }
    const name = promoteName.trim();
    if (!name) {
      toast.error("Name the Schema before promoting.");
      return;
    }
    setPromoting(true);
    try {
      await promoteSchema(name, fieldSet);
      toast.success(`Promoted "${name}" to a governed Schema.`);
      setPromoteName("");
      onReloadSchemas();
      onSelect(name);
    } catch (err) {
      reportApiError(err, "Promote failed. Nothing was saved.");
    } finally {
      setPromoting(false);
    }
  }

  async function handleImportFile(file: File) {
    if (!selected) {
      toast.error("Select a Schema to import into first.");
      return;
    }
    setImporting(true);
    try {
      const text = await file.text();
      const envelope = JSON.parse(text) as MasterMapEnvelope;
      await importMasterMap(selected, envelope);
      toast.success(`Augmented "${selected}" from ${file.name}.`);
      onReloadSchemas();
    } catch (err) {
      if (err instanceof SyntaxError) {
        toast.error("That file isn't valid JSON. Nothing was imported.");
      } else {
        reportApiError(err, "Import failed. Nothing was imported.");
      }
    } finally {
      setImporting(false);
    }
  }

  function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so choosing the same file twice still fires onChange.
    event.target.value = "";
    if (file) {
      void handleImportFile(file);
    }
  }

  const promoteButton = (
    <Button type="button" variant="outline" disabled={promoting || (signedIn && !verified)} onClick={handlePromote}>
      {promoting ? <Loader2 className="size-4 animate-spin" /> : !signedIn ? <ShieldAlert className="size-4" /> : null}
      Promote to Schema
    </Button>
  );

  // Signed-out stays CLICKABLE (routes to onRequireSignIn, mirroring
  // ConfirmGate/Promote) -- disabled folds only the auth reason
  // (signedIn && !verified) and the readiness reason (governed && !selected),
  // never disabled merely for being signed out.
  const importButton = (
    <Button
      type="button"
      variant="outline"
      disabled={importing || (signedIn && !verified) || (governed && !selected)}
      onClick={() => (signedIn ? fileInputRef.current?.click() : onRequireSignIn())}
    >
      {importing ? <Loader2 className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}
      Import master map
    </Button>
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="schema-select">Crosswalk Schema</Label>
          <Select value={selected ?? undefined} onValueChange={(value) => onSelect(String(value))} disabled={schemas.length === 0}>
            <SelectTrigger id="schema-select" className="w-56">
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
          <Label htmlFor="schema-vendor">Vendor (source label)</Label>
          <Input
            id="schema-vendor"
            value={vendor}
            placeholder="e.g. novascreen"
            className="w-56"
            onChange={(event) => onVendorChange(event.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="schema-promote-name">New Schema name</Label>
          <Input
            id="schema-promote-name"
            value={promoteName}
            placeholder="e.g. assay-potency"
            className="w-56"
            onChange={(event) => setPromoteName(event.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {signedIn && !verified ? (
          <Tooltip>
            <TooltipTrigger render={promoteButton} />
            <TooltipContent>Verify your email to promote a Schema.</TooltipContent>
          </Tooltip>
        ) : (
          promoteButton
        )}

        {selected ? (
          <a
            href={masterMapDownloadUrl(selected)}
            download
            className={buttonVariants({ variant: "outline" })}
          >
            <Download className="size-4" />
            Download master map
          </a>
        ) : (
          <Tooltip>
            <TooltipTrigger
              render={
                <Button type="button" variant="outline" disabled>
                  <Download className="size-4" />
                  Download master map
                </Button>
              }
            />
            <TooltipContent>Select a Schema to download its master map.</TooltipContent>
          </Tooltip>
        )}

        {signedIn && !verified ? (
          <Tooltip>
            <TooltipTrigger render={importButton} />
            <TooltipContent>Verify your email to import a master map.</TooltipContent>
          </Tooltip>
        ) : governed && !selected ? (
          <Tooltip>
            <TooltipTrigger render={importButton} />
            <TooltipContent>Select a Schema to import into first.</TooltipContent>
          </Tooltip>
        ) : (
          importButton
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={onFileChosen}
        />
      </div>
    </div>
  );
}
