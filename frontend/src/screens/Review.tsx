import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmGate } from "@/components/ConfirmGate";
import { ExportBar } from "@/components/ExportBar";
import { ProfileAppliedBanner } from "@/components/ProfileAppliedBanner";
import { ReviewTable } from "@/components/ReviewTable";
import { ApiError, GateRejected, confirm, listSchemas } from "@/lib/api";
import type {
  ConfirmResponse,
  FieldMappingOut,
  FieldSetPayload,
  MappingResponse,
  SchemaOut,
} from "@/lib/types";
import { escalationLine } from "@/state/dateFormat";
import {
  applyGateRejection,
  gateRejection,
  isAutoApplied,
  isReady,
  provenanceLine,
  reopenField,
  resolutionProgress,
  resolveByAccept,
  resolveByChip,
  resolveByDropdown,
  reviewSubject,
  toConfirmPayload,
  vendorBlockedReason,
} from "@/state/review";
import type { ConfirmError } from "@/state/review";
import { initialVendor, vendorHint } from "@/state/vendorMemory";

interface ReviewProps {
  /** `null` before any file has been uploaded this session -- the Upload
   * screen only ever calls `App.tsx`'s `onMapped` (and so lands here) once
   * `/api/upload`/a resolve returns a `kind:"mapping"` response; this screen
   * never performs its own upload or mapping call, so it never needs its
   * own upload-in-flight loading state (that lives entirely in
   * `Upload.tsx`). */
  mapping: MappingResponse | null;
  /** The governed Schema name the file was ACTUALLY mapped against
   * (threaded from Upload's `SchemaPicker` via `App.tsx`, D-10-02/D-10-06) --
   * shown read-only next to the upload-token line. Review no longer renders
   * a second Schema selector of its own (10-UI-SPEC Discretion §6): a
   * second selector here could silently disagree with the one that fixed
   * the mapping target. */
  schemaName: string | null;
  /** Auth mirror for the ConfirmGate (Plan 06). The server re-checks every
   * confirm (P1); these only drive the button's UX tier. */
  signedIn: boolean;
  verified: boolean;
  /** Open Sign In carrying a returnTo back to this Review screen. */
  onRequireSignIn: () => void;
  /** D-11-15: the worksheet this dataset came from, when the ingest has one
   * (a sheet-group member's tab passes its own sheet name). Absent/null on
   * the single-ingest path -- the provenance line then falls back to the
   * source FILE's name, the same fallback the server itself writes into
   * `__source_sheet` (`table.origin_sheet or source_label`). */
  sheetName?: string | null;
  /** Group-member reporting (11-10, both optional -- the single-dataset
   * path passes neither and behaves exactly as before). `ReviewGroupTabs`
   * needs a member's LIVE amber count for its tab badge and its own
   * confirm for the group "Download All" gate; this screen stays the ONLY
   * owner of the resolution state and merely reports it upward -- the
   * parent mirrors, it never controls (T-11-37: controlling from above
   * would re-create the remount hazard these tabs exist to close). */
  onMappingsChange?: (mappings: FieldMappingOut[]) => void;
  onConfirmed?: (response: ConfirmResponse) => void;
}

/** Strips a Schema's per-field vendor-alias provenance, leaving exactly the
 * `FieldPayload` shape `/api/confirm`'s `field_set` body key needs --
 * `CanonicalField.to_dict()`'s `aliases` are a crosswalk-editing concern
 * (owned by the Schemas page), never something the confirm gate reads. The
 * server's own signature check (CR-01: `submitted_field_set.signature !=
 * entry.field_set.signature`) is the actual authority; this is only the
 * client's honest copy of what the upload was mapped against. */
function fieldSetFromSchema(schema: SchemaOut): FieldSetPayload {
  return {
    name: schema.name,
    fields: schema.fields.map(({ aliases: _aliases, ...field }) => field),
  };
}

/**
 * The Review screen (UI-03/04/05, the demo's centerpiece) -- side-by-side
 * source/target panes, the D-02 amber-field resolution controls, and the
 * sticky confirm gate. `mappings` is the ONLY place a field's resolution
 * lives client-side; every resolve action goes through `state/review.ts`'s
 * pure functions, never a hand-rolled inline mutation. The parent
 * (`App.tsx`) keys this component by `upload_token` so a fresh upload
 * always remounts it with fresh local state, rather than this component
 * trying to detect "a new mapping arrived" via an effect.
 *
 * Carries no Schema selector of its own (D-10-02/Discretion §6): the
 * Schema is shown read-only, and its full field list is fetched once (to
 * build the `field_set` body `/api/confirm` still requires) so a curator
 * never re-chooses a Schema that could disagree with what Upload already
 * resolved against.
 */
export function Review({
  mapping,
  schemaName,
  signedIn,
  verified,
  onRequireSignIn,
  sheetName,
  onMappingsChange,
  onConfirmed,
}: ReviewProps) {
  const [mappings, setMappings] = useState(mapping?.field_mappings ?? []);
  const [submitting, setSubmitting] = useState(false);
  const [confirmError, setConfirmError] = useState<ConfirmError | null>(null);
  const [confirmed, setConfirmed] = useState<ConfirmResponse | null>(null);

  // The full governed Schema list, fetched once -- needed only to derive
  // the `FieldSetPayload` /api/confirm's field_set body key requires (the
  // server's own signature check against the RETAINED field set is the
  // real authority, CR-01). Review never lets the curator pick a DIFFERENT
  // Schema here; `schemaName` is fixed by Upload.
  const [schemas, setSchemas] = useState<SchemaOut[]>([]);
  // D-10-13/INGEST-02: the vendor is pre-filled ONLY from a learned column
  // signature (a profile match) or the Schema's crosswalk -- NEVER from the
  // Schema's own name. That old default silently wrote a vendor literally
  // named after the Schema (e.g. "assay-potency") into the governed
  // crosswalk on an inattentive confirm -- a silent wrong guess dressed as
  // a convenience, precisely what this product refuses. `mapping` can still
  // be null here (hooks run before the early-return guard below).
  const [vendor, setVendor] = useState(mapping ? initialVendor(mapping) : "");

  // Group-member reporting (11-10): mirror the LIVE mappings upward after
  // every resolution so a group tab's amber-count badge tracks the
  // curator's work. Deliberately deps [mappings] only -- the callback prop
  // is read at effect time, and depending on its identity would re-fire the
  // mirror on every parent render for no state change (the same
  // exhaustive-deps carve-out the mount effect below already documents).
  useEffect(() => {
    onMappingsChange?.(mappings);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappings]);

  useEffect(() => {
    listSchemas()
      .then(setSchemas)
      .catch(() => {
        // A schema-list fetch failure leaves `fieldSet` null below;
        // `handleConfirm` guards on it and reports a retry-able message --
        // it never silently confirms against an incomplete field set.
      });
    // Load once on mount -- this screen no longer promotes/imports Schemas
    // (those affordances moved to the Schemas page, Plan 06).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!mapping || !schemaName) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 py-16 text-center">
        <h2 className="text-heading">No file uploaded yet.</h2>
        <p className="max-w-md text-body text-muted-foreground">
          Upload a CSV or Excel file and choose a Schema to see Claude's proposed mapping here.
        </p>
      </div>
    );
  }

  const schema = schemas.find((s) => s.name === schemaName) ?? null;
  const fieldSet = schema ? fieldSetFromSchema(schema) : null;

  const progress = resolutionProgress(mappings);
  const ready = isReady(mappings);
  const autoApplied = isAutoApplied(mapping.provenance);

  async function handleConfirm() {
    if (!fieldSet) {
      setConfirmError("Still loading this Schema's fields — try again in a moment.");
      return;
    }
    setSubmitting(true);
    setConfirmError(null);
    try {
      // Crosswalk accrual (ALIAS-04): the Schema is always known here
      // (Upload requires one, D-10-01), and the vendor is now MANDATORY
      // (quick 260712) -- the server rejects a blank one (P1), and the
      // ConfirmGate's vendor tier keeps this closure unreachable while it
      // is blank. Trimmed to mirror the server's own rule.
      const trimmedVendor = vendor.trim();
      // Non-null assertions below: this closure only runs from a click on
      // ConfirmGate, which never renders until the early `!mapping ||
      // !schemaName` return above has already passed -- TS's flow analysis
      // just can't see that across a nested closure boundary (mirrors the
      // pre-existing `mapping!`/`fieldSet!` pattern this replaces).
      const payload = toConfirmPayload(mapping!.upload_token, fieldSet, mappings, {
        saveProfile: true,
        export: true,
        provenance: mapping!.provenance ?? "fresh-claude",
        schemaName: schemaName!,
        vendor: trimmedVendor,
      });
      const response = await confirm(payload);
      setConfirmed(response);
      // Report this member's OWN confirm upward (11-10) -- the group bar is
      // a lookup over these per-member verdicts, never a gate of its own.
      onConfirmed?.(response);
      toast.success("Mapping confirmed and saved. This source's format is now recognized automatically next time.");
    } catch (err) {
      if (err instanceof GateRejected) {
        // P1 (T-04-18): the server's OWN gate rejected the request --
        // export is never unlocked from this branch. Re-flag exactly the
        // fields the server named back to amber (`applyGateRejection`) so
        // the rejection is never a dead end: those rows regain their D-02
        // controls (and, for a field the client had shown clear/green,
        // `FieldRow`'s "Change column" affordance already got it there --
        // this closes the loop for a field the user never manually
        // reopened, e.g. a stale Accept from a prior session).
        setMappings((current) => applyGateRejection(current, err.unclearFields));
        setConfirmError(gateRejection(err.unclearDetails));
      } else if (err instanceof ApiError) {
        setConfirmError(typeof err.detail === "string" ? err.detail : "Confirm failed. Nothing was saved.");
      } else {
        setConfirmError("Confirm failed. Nothing was saved.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    // Vertical height budget: AppShell's header (h-16 = 4rem) + main's
    // own py-8 (2rem top + 2rem bottom = 4rem) = 8rem of fixed chrome
    // around this screen's content (AppShell.tsx). ReviewTable owns its
    // own scroll within the remaining space; ConfirmGate is a normal
    // flex-column child pinned to the bottom of THIS fixed-height
    // container, never requiring the page body to scroll horizontally
    // or the footer to be scrolled into view (04-UI-SPEC.md Layout &
    // Responsive Behavior).
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-display">Review Mapping</h1>
        {/* What file, onto what Schema -- never the raw upload token, which
         * means nothing to a curator (quick 260712). The token stays a
         * wire-level correlation detail only. */}
        <p className="text-mono-label text-muted-foreground">
          {reviewSubject(mapping.source_name, schemaName)}
        </p>
        {/* D-11-15 (SHEET-03's visible half): where these rows came FROM,
         * on EVERY ingest -- the worksheet for a group member, the file
         * itself for a CSV. Header metadata only, NEVER a row in
         * ReviewTable (UI-SPEC Discretion §3): it is not a mapped field,
         * has no confidence and no amber state, and rendering it as one
         * would present a bookkeeping constant as something Claude
         * proposed and the human must check. */}
        {provenanceLine(sheetName, mapping.source_name) && (
          <p className="text-mono-label text-muted-foreground">
            {provenanceLine(sheetName, mapping.source_name)}
          </p>
        )}
        {mapping.escalation && (
          <p className="text-mono-label text-muted-foreground">{escalationLine(mapping.escalation)}</p>
        )}
        <div className="flex flex-col gap-1.5 pt-2 sm:w-56">
          {/* Required (quick 260712): the server rejects a vendor-less
           * confirm, and the ConfirmGate mirrors that with a disabled
           * button + reason -- the same mechanism as the amber-field gate.
           * Still NEVER pre-filled with a guess (D-10-13): only a profile
           * match or the crosswalk may pre-fill it; otherwise the human
           * types it. */}
          <Label htmlFor="review-vendor">Vendor (source label) — required</Label>
          <Input
            id="review-vendor"
            value={vendor}
            placeholder="e.g. novascreen"
            required
            aria-required
            onChange={(event) => setVendor(event.target.value)}
          />
          {vendorHint(mapping) && <p className="text-label text-muted-foreground">{vendorHint(mapping)}</p>}
        </div>
      </div>

      {autoApplied && <ProfileAppliedBanner />}

      {confirmError && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Confirm rejected</AlertTitle>
          <AlertDescription>
            {typeof confirmError === "string" ? (
              confirmError
            ) : (
              <div className="flex flex-col gap-1.5">
                <p>Confirm rejected — nothing was saved.</p>
                <ul className="list-disc space-y-1 pl-5">
                  {confirmError.fields.map(({ name, reason }) => (
                    <li key={name}>{reason ? `${name} — ${reason}` : name}</li>
                  ))}
                </ul>
                <p>Resolve the highlighted field(s) below and confirm again.</p>
              </div>
            )}
          </AlertDescription>
        </Alert>
      )}

      <div className="min-h-0 flex-1">
        <ReviewTable
          sourceColumns={mapping.source_columns}
          mappings={mappings}
          onResolveByChip={(targetField, candidate) =>
            setMappings((current) => resolveByChip(current, targetField, candidate))
          }
          onResolveByAccept={(targetField) => setMappings((current) => resolveByAccept(current, targetField))}
          onResolveByDropdown={(targetField, column) =>
            setMappings((current) => resolveByDropdown(current, targetField, column))
          }
          onReopen={(targetField) => setMappings((current) => reopenField(current, targetField))}
        />
      </div>

      {confirmed?.export ? (
        <ExportBar exportUrls={confirmed.export} />
      ) : (
        <ConfirmGate
          clear={progress.clear}
          total={progress.total}
          ready={ready}
          submitting={submitting}
          onConfirm={handleConfirm}
          vendorBlockedReason={vendorBlockedReason(vendor)}
          signedIn={signedIn}
          verified={verified}
          onRequireSignIn={onRequireSignIn}
        />
      )}
    </div>
  );
}
