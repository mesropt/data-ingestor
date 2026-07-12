import { useEffect, useReducer, useState } from "react";
import { FileWarning } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FieldSetPicker } from "@/components/FieldSetPicker";
import { HeadersOnlyToggle } from "@/components/HeadersOnlyToggle";
import { MapFileControls } from "@/components/MapFileControls";
import { ReconcilePanel } from "@/components/ReconcilePanel";
import { StructuralHintPanel } from "@/components/StructuralHintPanel";
import { UploadDropzone, type DropzonePhase } from "@/components/UploadDropzone";
import { ApiError, listFieldSets, resolveHint, resolveReconcile, uploadFile } from "@/lib/api";
import type {
  FieldSetPayload,
  FieldSetTemplate,
  MappingResponse,
  ReconcileChoice,
  ReconcileQuestionResponse,
  StructuralHintIn,
  StructuralQuestionResponse,
} from "@/lib/types";
import { assertNever } from "@/lib/utils";
import { initialUploadState, uploadReducer, type UploadState } from "@/state/upload";

/** Every non-`idle` phase carries `file` -- a small helper beats repeating
 * the same phase-narrowing switch at every render-time read site. */
function fileFromState(state: UploadState): File | null {
  return state.phase === "idle" ? null : state.file;
}

interface UploadProps {
  /** Called once `/api/upload` (or a hint resolve) returns `kind:"mapping"`
   * -- the Upload screen's job ends at handing the response + its
   * `upload_token` to whatever consumes it next (the Review screen, Plan
   * 06); it navigates there but does not render it. `fieldSet` is the
   * SAME `FieldSetPayload` the request was mapped against -- Review needs
   * it to build `/api/confirm`'s request body (`ConfirmRequest.field_set`,
   * `state/review.ts::toConfirmPayload`), and nothing upstream of Review
   * else has it once the Upload screen's own `selectedTemplate` state is
   * gone. */
  onMapped: (response: MappingResponse, fieldSet: FieldSetPayload) => void;
  /** Auth mirror (Plan 06 / D-08-05), threaded into `MapFileControls`: the
   * map-file attach affordance is enabled only when signedIn AND verified,
   * because attaching a map file augments the governed master crosswalk. The
   * server re-enforces `require_verified_user` on the augmenting path (T-08-12);
   * this mirror only gates UX. `onRequireSignIn` routes a signed-out user to
   * Sign In, mirroring how Review/SchemaControls receive them. */
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

/** The dropzone only knows its own 5 visual states -- this maps the
 * reducer's richer `phase` onto them. `mapping` never actually renders
 * (the screen navigates away via `onMapped` the instant a mapping response
 * arrives), but is included for exhaustiveness. */
function toDropzonePhase(phase: string): DropzonePhase {
  switch (phase) {
    case "idle":
      return "idle";
    case "fileSelected":
      return "fileSelected";
    case "uploading":
      return "uploading";
    case "error":
      return "error";
    case "structuralQuestion":
    case "resolving":
    case "reconcileQuestion":
    case "resolvingReconcile":
    case "mapping":
      return "locked";
    default:
      return "idle";
  }
}

/**
 * Upload screen (UI-02): pick a field set, toggle headers-only (P2), drop a
 * file, submit to `/api/upload`. When the server is unsure of the file's
 * structure, the `StructuralHintPanel` (D-04) appears inline below the
 * dropzone in the SAME flow -- never a separate route or modal -- and its
 * resolution loops back through the same reducer. All state transitions
 * are driven by `state/upload.ts`'s vitest-covered reducer; this screen
 * only wires user events to `dispatch` and the two API calls to it.
 */
export function Upload({ onMapped, signedIn, verified, onRequireSignIn }: UploadProps) {
  const [templates, setTemplates] = useState<FieldSetTemplate[]>([]);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [headersOnly, setHeadersOnly] = useState(false);
  // The optional reconcile ingress (D-08-06): a target Schema, a vendor label,
  // and an attached map file, all owned here and threaded into `uploadFile`.
  const [schemaName, setSchemaName] = useState<string | null>(null);
  const [vendor, setVendor] = useState("");
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [state, dispatch] = useReducer(uploadReducer, initialUploadState);
  // Screen-local: the reducer's `resolving`/`resolvingReconcile` phases
  // intentionally carry no `response` (state/upload.test.ts pins those shapes)
  // -- the last-seen question is kept here purely so the panel stays rendered
  // (with its own `submitting` spinner) while a resolve is in flight.
  const [lastQuestion, setLastQuestion] = useState<StructuralQuestionResponse | null>(null);
  const [lastReconcile, setLastReconcile] = useState<ReconcileQuestionResponse | null>(null);

  useEffect(() => {
    listFieldSets()
      .then(setTemplates)
      .catch((err: unknown) => {
        setTemplatesError(consequenceMessage(err, "Couldn't load saved field sets right now."));
      });
  }, []);

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null;

  /** Routes a discriminated `/api/upload` or resolve response onto the right
   * inline panel: a `mapping` proceeds silently to Review; a
   * `structural_question` or `reconcile_question` keeps its question rendered.
   * Shared by the fresh upload and both resolve loops. */
  function handleResponse(response: Awaited<ReturnType<typeof uploadFile>>, fieldSet: FieldSetPayload) {
    switch (response.kind) {
      case "mapping":
        setLastQuestion(null);
        setLastReconcile(null);
        onMapped(response, fieldSet);
        return;
      case "reconcile_question":
        setLastReconcile(response);
        return;
      case "structural_question":
        setLastQuestion(response);
        return;
      default:
        // Exhaustiveness: a future 4th `kind` is a compile-time error here,
        // not a silent mis-render into the StructuralHintPanel.
        assertNever(response);
    }
  }

  async function handleSubmitUpload() {
    if (state.phase !== "fileSelected" || !selectedTemplate) return;
    const file = state.file;
    // The map-file options are sent ONLY when a file is attached; a plain
    // upload's request stays byte-identical to today (uploadFile's guard).
    const options = mapFile
      ? { mapFile, schemaName: schemaName ?? "", vendor }
      : undefined;
    dispatch({ type: "SUBMIT_UPLOAD" });
    try {
      const response = await uploadFile(file, selectedTemplate.field_set, headersOnly, undefined, options);
      dispatch({ type: "UPLOAD_SUCCESS", response });
      handleResponse(response, selectedTemplate.field_set);
    } catch (err) {
      dispatch({
        type: "UPLOAD_ERROR",
        message: consequenceMessage(
          err,
          "Claude couldn't map this file right now. Nothing was saved — retry, or try again in a moment."
        ),
      });
    }
  }

  async function handleResolveReconcile(choices: ReconcileChoice[]) {
    if (state.phase !== "reconcileQuestion" || !selectedTemplate) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_RECONCILE" });
    try {
      const response = await resolveReconcile(uploadToken, choices);
      dispatch({ type: "RECONCILE_SUCCESS", response });
      handleResponse(response, selectedTemplate.field_set);
    } catch (err) {
      dispatch({
        type: "RECONCILE_ERROR",
        message: consequenceMessage(
          err,
          "Couldn't apply your resolution right now. Nothing was saved — retry, or try again in a moment."
        ),
      });
    }
  }

  async function handleResolveHint(hint: StructuralHintIn) {
    if (state.phase !== "structuralQuestion" || !selectedTemplate) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_HINT" });
    try {
      const response = await resolveHint(uploadToken, hint);
      dispatch({ type: "HINT_SUCCESS", response });
      handleResponse(response, selectedTemplate.field_set);
    } catch (err) {
      dispatch({
        type: "HINT_ERROR",
        message: consequenceMessage(
          err,
          "Claude couldn't map this file right now. Nothing was saved — retry, or try again in a moment."
        ),
      });
    }
  }

  const controlsDisabled =
    state.phase === "uploading" || state.phase === "resolving" || state.phase === "resolvingReconcile";
  const dropzoneFile = fileFromState(state);
  const dropzoneErrorMessage = state.phase === "error" ? state.message : null;
  const showHintPanel =
    (state.phase === "structuralQuestion" || state.phase === "resolving") && lastQuestion !== null;
  const showReconcilePanel =
    (state.phase === "reconcileQuestion" || state.phase === "resolvingReconcile") && lastReconcile !== null;

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-8">
      <h1 className="text-display">Upload File</h1>

      {templatesError && (
        <Alert variant="destructive">
          <FileWarning />
          <AlertTitle>Couldn't load saved field sets</AlertTitle>
          <AlertDescription>{templatesError}</AlertDescription>
        </Alert>
      )}

      <FieldSetPicker
        templates={templates}
        value={selectedTemplateId}
        onChange={setSelectedTemplateId}
        disabled={controlsDisabled}
      />

      <HeadersOnlyToggle checked={headersOnly} onCheckedChange={setHeadersOnly} disabled={controlsDisabled} />

      <MapFileControls
        schemaName={schemaName}
        onSchemaNameChange={setSchemaName}
        vendor={vendor}
        onVendorChange={setVendor}
        mapFile={mapFile}
        onMapFileChange={setMapFile}
        signedIn={signedIn}
        verified={verified}
        disabled={controlsDisabled}
        onRequireSignIn={onRequireSignIn}
      />

      <UploadDropzone
        phase={toDropzonePhase(state.phase)}
        file={dropzoneFile}
        errorMessage={dropzoneErrorMessage}
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
    </div>
  );
}
