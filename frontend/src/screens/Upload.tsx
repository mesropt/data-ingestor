import { useEffect, useReducer, useState } from "react";
import { FileWarning } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FieldSetPicker } from "@/components/FieldSetPicker";
import { HeadersOnlyToggle } from "@/components/HeadersOnlyToggle";
import { StructuralHintPanel } from "@/components/StructuralHintPanel";
import { UploadDropzone, type DropzonePhase } from "@/components/UploadDropzone";
import { ApiError, listFieldSets, resolveHint, uploadFile } from "@/lib/api";
import type {
  FieldSetPayload,
  FieldSetTemplate,
  MappingResponse,
  StructuralHintIn,
  StructuralQuestionResponse,
} from "@/lib/types";
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
export function Upload({ onMapped }: UploadProps) {
  const [templates, setTemplates] = useState<FieldSetTemplate[]>([]);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [headersOnly, setHeadersOnly] = useState(false);
  const [state, dispatch] = useReducer(uploadReducer, initialUploadState);
  // Screen-local: the reducer's `resolving` phase intentionally carries no
  // `response` (state/upload.test.ts pins that shape) -- the last-seen
  // question is kept here purely so the panel stays rendered (with its own
  // `submitting` spinner) while a hint resolve is in flight.
  const [lastQuestion, setLastQuestion] = useState<StructuralQuestionResponse | null>(null);

  useEffect(() => {
    listFieldSets()
      .then(setTemplates)
      .catch((err: unknown) => {
        setTemplatesError(consequenceMessage(err, "Couldn't load saved field sets right now."));
      });
  }, []);

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null;

  async function handleSubmitUpload() {
    if (state.phase !== "fileSelected" || !selectedTemplate) return;
    const file = state.file;
    dispatch({ type: "SUBMIT_UPLOAD" });
    try {
      const response = await uploadFile(file, selectedTemplate.field_set, headersOnly);
      dispatch({ type: "UPLOAD_SUCCESS", response });
      if (response.kind === "mapping") {
        setLastQuestion(null);
        onMapped(response, selectedTemplate.field_set);
      } else {
        setLastQuestion(response);
      }
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

  async function handleResolveHint(hint: StructuralHintIn) {
    if (state.phase !== "structuralQuestion" || !selectedTemplate) return;
    const uploadToken = state.uploadToken;
    dispatch({ type: "SUBMIT_HINT" });
    try {
      const response = await resolveHint(uploadToken, hint);
      dispatch({ type: "HINT_SUCCESS", response });
      if (response.kind === "mapping") {
        setLastQuestion(null);
        onMapped(response, selectedTemplate.field_set);
      } else {
        setLastQuestion(response);
      }
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

  const controlsDisabled = state.phase === "uploading" || state.phase === "resolving";
  const dropzoneFile = fileFromState(state);
  const dropzoneErrorMessage = state.phase === "error" ? state.message : null;
  const showHintPanel =
    (state.phase === "structuralQuestion" || state.phase === "resolving") && lastQuestion !== null;

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
    </div>
  );
}
