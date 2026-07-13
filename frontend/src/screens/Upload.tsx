import { useReducer, useState } from "react";

import { DateFormatQuestionPanel } from "@/components/DateFormatQuestionPanel";
import { HeadersOnlyToggle } from "@/components/HeadersOnlyToggle";
import { MapFileAttach } from "@/components/MapFileAttach";
import { ReconcilePanel } from "@/components/ReconcilePanel";
import { SchemaPicker } from "@/components/SchemaPicker";
import { SheetQuestionPanel } from "@/components/SheetQuestionPanel";
import { StructuralHintPanel } from "@/components/StructuralHintPanel";
import { UploadDropzone } from "@/components/UploadDropzone";
import {
  ApiError,
  resolveDateFormat,
  resolveHint,
  resolveReconcile,
  resolveSheets,
  uploadFile,
} from "@/lib/api";
import type {
  DateFormatChoice,
  DateFormatQuestionResponse,
  MappingResponse,
  ReconcileChoice,
  ReconcileQuestionResponse,
  SheetGroupResponse,
  SheetSelection,
  StructuralHintIn,
  StructuralQuestionResponse,
} from "@/lib/types";
import { assertNever } from "@/lib/utils";
import {
  initialUploadState,
  toDropzonePhase,
  uploadErrorTitle,
  uploadReducer,
  type UploadState,
} from "@/state/upload";

/** Every non-`idle` phase carries `file` -- a small helper beats repeating
 * the same phase-narrowing switch at every render-time read site. */
function fileFromState(state: UploadState): File | null {
  return state.phase === "idle" ? null : state.file;
}

interface UploadProps {
  /** Called once `/api/upload` (or a resolve) returns `kind:"mapping"` --
   * the Upload screen's job ends at handing the response + the Schema NAME
   * it was mapped against to whatever consumes it next (the Review screen);
   * it navigates there but does not render it. `schemaName` is the SAME
   * governed Schema `SchemaPicker` resolved -- Review shows it read-only and
   * needs it to build `/api/confirm`'s request (D-10-02/D-10-06). */
  onMapped: (response: MappingResponse, schemaName: string) => void;
  /** Called once `/api/sheets/resolve` returns the `kind:"sheet_group"` arm
   * (11-10): N independent datasets now exist server-side, and the Review
   * screen's member tabs take over. `schemasBySheet` is the human's OWN
   * per-sheet Schema choices from the selection panel -- each member's
   * Review shows its Schema read-only and builds `/api/confirm` from it,
   * exactly as `onMapped`'s `schemaName` does for a single dataset.
   * `headersOnly` rides along so a member's still-pending question panel
   * enforces the same privacy rule this screen's own panels do. */
  onSheetGroup: (
    group: SheetGroupResponse,
    schemasBySheet: Record<string, string>,
    headersOnly: boolean
  ) => void;
  /** Auth mirror (Plan 06 / D-08-05), threaded into `MapFileAttach`: the
   * map-file attach affordance is enabled only when signedIn AND verified,
   * because attaching a map file augments the governed master crosswalk. The
   * server re-enforces `require_verified_user` on the augmenting path (T-08-12);
   * this mirror only gates UX. `onRequireSignIn` routes a signed-out user to
   * Sign In, mirroring how Review receives them. */
  signedIn: boolean;
  verified: boolean;
  onRequireSignIn: () => void;
}

function consequenceMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (error.detail && typeof error.detail === "object") return JSON.stringify(error.detail);
  }
  return fallback;
}

/**
 * Upload screen (D-10-01/02): pick a governed Schema, optionally attach a
 * map file, toggle headers-only (P2), drop a file, submit to `/api/upload`.
 * Exactly three controls plus the dropzone -- the internal `FieldSet`
 * concept never appears anywhere on this screen. When the server can't
 * resolve the file's structure, a map-file conflict, or an ambiguous mapped
 * date column, the matching inline panel (`StructuralHintPanel` /
 * `ReconcilePanel` / `DateFormatQuestionPanel`, D-04/D-08/D-10-07) appears
 * below the dropzone in the SAME flow -- never a separate route or modal --
 * and its resolution loops back through the same reducer. All state
 * transitions are driven by `state/upload.ts`'s vitest-covered reducer;
 * this screen only wires user events to `dispatch` and the four API calls
 * to it.
 */
export function Upload({ onMapped, onSheetGroup, signedIn, verified, onRequireSignIn }: UploadProps) {
  const [selectedSchema, setSelectedSchema] = useState<string | null>(null);
  const [headersOnly, setHeadersOnly] = useState(false);
  // The optional reconcile ingress (D-08-06), now targeting the SAME Schema
  // control #1 already fixed -- MapFileAttach has no Schema select of its
  // own (D-10-01/02).
  const [vendor, setVendor] = useState("");
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [state, dispatch] = useReducer(uploadReducer, initialUploadState);
  // Screen-local: the reducer's `resolving`/`resolvingReconcile`/
  // `resolvingDateFormat` phases intentionally carry no `response`
  // (state/upload.test.ts pins those shapes) -- the last-seen question is
  // kept here purely so the panel stays rendered (with its own `submitting`
  // spinner) while a resolve is in flight.
  const [lastQuestion, setLastQuestion] = useState<StructuralQuestionResponse | null>(null);
  const [lastReconcile, setLastReconcile] = useState<ReconcileQuestionResponse | null>(null);
  const [lastDateQuestion, setLastDateQuestion] = useState<DateFormatQuestionResponse | null>(null);

  // D-10-01: submit is blocked with the UI-SPEC's exact copy until a Schema
  // is chosen -- the same mechanism `UploadDropzone`'s canSubmit/blockedReason
  // props already provide (quick task 260712-e0e's mechanism, now fed a
  // Schema-shaped reason instead of a field-set one; the field-set auto-select
  // helpers themselves are deleted, not carried forward).
  const blockedReason = selectedSchema === null ? "Choose a Schema before uploading." : null;

  /** Routes a discriminated `/api/upload` or resolve response onto the right
   * inline panel: a `mapping` proceeds silently to Review; a
   * `structural_question`, `reconcile_question`, or `date_question` keeps
   * its question rendered. Shared by the fresh upload and all three resolve
   * loops. `schemaName` is the Schema the request was actually made against
   * (captured at call time by each handler below), threaded to `onMapped`
   * only on the `mapping` arm. */
  function handleResponse(response: Awaited<ReturnType<typeof uploadFile>>, schemaName: string) {
    switch (response.kind) {
      case "mapping":
        setLastQuestion(null);
        setLastReconcile(null);
        setLastDateQuestion(null);
        onMapped(response, schemaName);
        return;
      case "reconcile_question":
        setLastReconcile(response);
        return;
      case "structural_question":
        setLastQuestion(response);
        return;
      case "date_question":
        setLastDateQuestion(response);
        return;
      case "sheet_question":
        // The reducer's `sheetQuestion` phase carries the response itself
        // (unlike its siblings), so the panel renders straight from state --
        // no `lastSheetQuestion` mirror needed; just clear the other panels.
        setLastQuestion(null);
        setLastReconcile(null);
        setLastDateQuestion(null);
        return;
      case "sheet_group":
        // Defensive only: a group is minted exclusively by /api/sheets/
        // resolve, whose handler below routes it to `onSheetGroup` itself
        // (it alone knows the per-sheet Schema selections). The resolve
        // siblings that share this switch can never return this kind.
        return;
      default:
        // Exhaustiveness: a future 5th `kind` is a compile-time error here,
        // not a silent mis-render into the wrong panel.
        assertNever(response);
    }
  }

  async function handleSubmitUpload() {
    if (state.phase !== "fileSelected" || !selectedSchema) return;
    const file = state.file;
    // The map-file options are sent ONLY when a file is attached; a plain
    // upload's request stays byte-identical otherwise (uploadFile's guard).
    const options = mapFile ? { mapFile, vendor } : undefined;
    dispatch({ type: "SUBMIT_UPLOAD" });
    try {
      const response = await uploadFile(file, selectedSchema, headersOnly, undefined, options);
      dispatch({ type: "UPLOAD_SUCCESS", response });
      handleResponse(response, selectedSchema);
    } catch (err) {
      dispatch({
        type: "UPLOAD_ERROR",
        message: consequenceMessage(
          err,
          "Claude couldn't map this file right now. Nothing was saved — retry, or try again in a moment."
        ),
        title: uploadErrorTitle(err),
      });
    }
  }

  async function handleResolveReconcile(choices: ReconcileChoice[]) {
    if (state.phase !== "reconcileQuestion" || !selectedSchema) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_RECONCILE" });
    try {
      const response = await resolveReconcile(uploadToken, choices);
      dispatch({ type: "RECONCILE_SUCCESS", response });
      handleResponse(response, selectedSchema);
    } catch (err) {
      dispatch({
        type: "RECONCILE_ERROR",
        message: consequenceMessage(
          err,
          "Couldn't apply your resolution right now. Nothing was saved — retry, or try again in a moment."
        ),
        title: uploadErrorTitle(err),
      });
    }
  }

  async function handleResolveHint(hint: StructuralHintIn) {
    if (state.phase !== "structuralQuestion" || !selectedSchema) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_HINT" });
    try {
      const response = await resolveHint(uploadToken, hint);
      dispatch({ type: "HINT_SUCCESS", response });
      handleResponse(response, selectedSchema);
    } catch (err) {
      dispatch({
        type: "HINT_ERROR",
        message: consequenceMessage(
          err,
          "Claude couldn't map this file right now. Nothing was saved — retry, or try again in a moment."
        ),
        title: uploadErrorTitle(err),
      });
    }
  }

  async function handleResolveDateFormat(choices: DateFormatChoice[]) {
    if (state.phase !== "dateQuestion" || !selectedSchema) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_DATE_FORMAT" });
    try {
      const response = await resolveDateFormat(uploadToken, choices);
      dispatch({ type: "DATE_FORMAT_SUCCESS", response });
      handleResponse(response, selectedSchema);
    } catch (err) {
      dispatch({
        type: "DATE_FORMAT_ERROR",
        message: consequenceMessage(
          err,
          "Couldn't apply your date order right now. Nothing was saved — retry, or try again in a moment."
        ),
        title: uploadErrorTitle(err),
      });
    }
  }

  async function handleResolveSheets(selections: SheetSelection[]) {
    if (state.phase !== "sheetQuestion") return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_SHEETS" });
    try {
      const response = await resolveSheets({ upload_token: uploadToken, selections });
      dispatch({ type: "SHEETS_SUCCESS", response });
      // Route the group into Review's member tabs (11-10), carrying the
      // human's OWN per-sheet Schema choices -- the wire deliberately does
      // not echo them back (T-08-08: server-retained), and this handler is
      // the one place that still holds them.
      onSheetGroup(
        response,
        Object.fromEntries(selections.map((s) => [s.sheet_name, s.schema_name])),
        headersOnly
      );
    } catch (err) {
      // Back to the question WITH the message -- the panel stays mounted and
      // every tick/Schema choice survives (UI-SPEC: selections preserved).
      dispatch({
        type: "SHEETS_ERROR",
        message: consequenceMessage(
          err,
          "Couldn't prepare the selected sheets — nothing was ingested. Your selections are kept; try again, or re-upload the file."
        ),
      });
    }
  }

  const controlsDisabled =
    state.phase === "uploading" ||
    state.phase === "resolving" ||
    state.phase === "resolvingReconcile" ||
    state.phase === "resolvingDateFormat" ||
    state.phase === "resolvingSheets";
  const dropzoneFile = fileFromState(state);
  const dropzoneErrorMessage = state.phase === "error" ? state.message : null;
  const dropzoneErrorTitle = state.phase === "error" ? state.title : null;
  const showHintPanel =
    (state.phase === "structuralQuestion" || state.phase === "resolving") && lastQuestion !== null;
  const showReconcilePanel =
    (state.phase === "reconcileQuestion" || state.phase === "resolvingReconcile") && lastReconcile !== null;
  const showDateQuestionPanel =
    (state.phase === "dateQuestion" || state.phase === "resolvingDateFormat") && lastDateQuestion !== null;

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-8">
      <h1 className="text-display">Upload File</h1>

      <SchemaPicker value={selectedSchema} onChange={setSelectedSchema} disabled={controlsDisabled} />

      <MapFileAttach
        schemaName={selectedSchema}
        vendor={vendor}
        onVendorChange={setVendor}
        mapFile={mapFile}
        onMapFileChange={setMapFile}
        signedIn={signedIn}
        verified={verified}
        disabled={controlsDisabled}
        onRequireSignIn={onRequireSignIn}
      />

      <HeadersOnlyToggle checked={headersOnly} onCheckedChange={setHeadersOnly} disabled={controlsDisabled} />

      <UploadDropzone
        phase={toDropzonePhase(state.phase)}
        file={dropzoneFile}
        errorMessage={dropzoneErrorMessage}
        errorTitle={dropzoneErrorTitle}
        canSubmit={blockedReason === null}
        blockedReason={blockedReason}
        onFileSelected={(file) => dispatch({ type: "SELECT_FILE", file })}
        onRemove={() => dispatch({ type: "RESET" })}
        onSubmit={handleSubmitUpload}
      />

      {showHintPanel && lastQuestion && (
        <StructuralHintPanel
          question={lastQuestion}
          headersOnly={headersOnly}
          submitting={state.phase === "resolving"}
          onResolve={handleResolveHint}
        />
      )}

      {showReconcilePanel && lastReconcile && (
        <ReconcilePanel
          question={lastReconcile}
          submitting={state.phase === "resolvingReconcile"}
          onResolve={handleResolveReconcile}
        />
      )}

      {showDateQuestionPanel && lastDateQuestion && (
        <DateFormatQuestionPanel
          question={lastDateQuestion}
          headersOnly={headersOnly}
          submitting={state.phase === "resolvingDateFormat"}
          onResolve={handleResolveDateFormat}
        />
      )}

      {/* Unlike its siblings this panel reads the question straight off the
          reducer state (both phases carry `response`), so an in-flight or
          failed resolve never unmounts it -- the curator's ticks and Schema
          choices are component-local and survive. Keyed by the upload token:
          a NEW workbook's question remounts with fresh pre-selections. */}
      {(state.phase === "sheetQuestion" || state.phase === "resolvingSheets") && (
        <SheetQuestionPanel
          key={state.uploadToken}
          question={state.response}
          defaultSchema={selectedSchema}
          submitting={state.phase === "resolvingSheets"}
          errorMessage={state.phase === "sheetQuestion" ? state.errorMessage : null}
          onResolve={handleResolveSheets}
        />
      )}
    </div>
  );
}
