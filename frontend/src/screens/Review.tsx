import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ConfirmGate } from "@/components/ConfirmGate";
import { ExportBar } from "@/components/ExportBar";
import { ProfileAppliedBanner } from "@/components/ProfileAppliedBanner";
import { ReviewTable } from "@/components/ReviewTable";
import { ApiError, GateRejected, confirm } from "@/lib/api";
import type { ConfirmResponse, FieldSetPayload, MappingResponse } from "@/lib/types";
import {
  applyGateRejection,
  isAutoApplied,
  isReady,
  reopenField,
  resolutionProgress,
  resolveByAccept,
  resolveByChip,
  resolveByDropdown,
  toConfirmPayload,
} from "@/state/review";

interface ReviewProps {
  /** `null` before any file has been uploaded this session -- the Upload
   * screen (Plan 05) only ever calls `App.tsx`'s `onMapped` (and so lands
   * here) once `/api/upload`/`/api/structural-hint/resolve` returns a
   * `kind:"mapping"` response; this screen never performs its own upload
   * or mapping call, so it never needs its own upload-in-flight loading
   * state (that lives entirely in `Upload.tsx`, 04-05). */
  mapping: MappingResponse | null;
  fieldSet: FieldSetPayload | null;
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
 */
export function Review({ mapping, fieldSet }: ReviewProps) {
  const [mappings, setMappings] = useState(mapping?.field_mappings ?? []);
  const [submitting, setSubmitting] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<ConfirmResponse | null>(null);

  if (!mapping || !fieldSet) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 py-16 text-center">
        <h2 className="text-heading">No file uploaded yet.</h2>
        <p className="max-w-md text-body text-muted-foreground">
          Upload a CSV or Excel file and choose a field set to see Claude's proposed mapping here.
        </p>
      </div>
    );
  }

  const progress = resolutionProgress(mappings);
  const ready = isReady(mappings);
  const autoApplied = isAutoApplied(mapping.provenance);

  async function handleConfirm() {
    setSubmitting(true);
    setConfirmError(null);
    try {
      const payload = toConfirmPayload(mapping!.upload_token, fieldSet!, mappings, {
        saveProfile: true,
        export: true,
        provenance: mapping!.provenance ?? "fresh-claude",
      });
      const response = await confirm(payload);
      setConfirmed(response);
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
        setConfirmError(
          "The server found an uncertain field that wasn't resolved. Nothing was saved — resolve the highlighted field(s) below and confirm again."
        );
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
        <p className="text-mono-label text-muted-foreground">
          upload {mapping.upload_token} — {fieldSet.name ?? "unnamed field set"}
        </p>
      </div>

      {autoApplied && <ProfileAppliedBanner />}

      {confirmError && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Confirm rejected</AlertTitle>
          <AlertDescription>{confirmError}</AlertDescription>
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
        />
      )}
    </div>
  );
}
