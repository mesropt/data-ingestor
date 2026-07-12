import { useRef, useState } from "react";
import { FileWarning, Loader2, UploadCloud, X } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// The old binary .xls (OLE2/BIFF) container is refused by the backend
// (parsing/table.py, api/routes/upload.py) — advertise only what actually
// ingests so the curator never picks a file the server will 400.
const ACCEPTED_EXTENSIONS = ".csv,.xlsx";

/** Shown only when the caller passes no `errorTitle` (null/undefined) --
 * never claims a specific cause on its own, since a title asserting a cause
 * the server did not report is the exact defect this component used to
 * have (hardcoded to a parse-failure claim for every error). */
const _DEFAULT_ERROR_TITLE = "Upload failed";

export type DropzonePhase = "idle" | "fileSelected" | "uploading" | "error" | "locked";

interface UploadDropzoneProps {
  phase: DropzonePhase;
  file: File | null;
  errorMessage?: string | null;
  /** The alert's title, derived by the caller (`state/upload.ts::uploadErrorTitle`)
   * from the actual error -- e.g. a 503 names the mapper as unavailable, but a
   * 500/401 (each emitted for two unrelated causes) and any non-`ApiError` fall
   * back to a neutral title there. `null`/`undefined` renders `_DEFAULT_ERROR_TITLE`
   * here, so this component never asserts a cause on its own either. */
  errorTitle?: string | null;
  /** Whether the submit button may act. Required (not optional) -- the
   * single call site (`screens/Upload.tsx`), and any future one, must
   * supply it: an enabled button that cannot act is the exact defect this
   * prop removes. Derived from the SAME value `Upload.tsx`'s
   * `handleSubmitUpload` guard checks, so the two can never drift apart
   * again. */
  canSubmit: boolean;
  /** The curator-facing reason submission is blocked, or `null` when
   * `canSubmit` is true. Rendered as small muted helper text beneath the
   * button whenever a file is selected but blocked. */
  blockedReason: string | null;
  onFileSelected: (file: File) => void;
  onRemove: () => void;
  onSubmit: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * File selection (UI-02 Screen 2) -- the four dropzone states declared in
 * 04-UI-SPEC.md: idle (dashed prompt), file-selected (compact chip +
 * enabled CTA), uploading (spinner, controls disabled), error (red border +
 * destructive Alert whose title honestly reflects the error passed in --
 * never a hardcoded parse-failure claim -- with the file preserved so the
 * curator can retry without re-picking it). Drives entirely off `state/upload.ts`'s reducer via the
 * Upload screen -- this component holds no upload state of its own beyond
 * the transient drag-hover visual. `locked` is a fifth, UI-SPEC-implied
 * state: once a structural question is showing (D-04), the dropzone
 * freezes on its file chip with no controls -- the inline
 * `StructuralHintPanel` below owns the next action, so the dropzone must
 * not offer a second, conflicting "Upload & Map" at the same time.
 *
 * `canSubmit`/`blockedReason`: the button's disabled state and
 * `Upload.tsx`'s `handleSubmitUpload` early-return guard now derive from
 * the SAME resolved-field-set value, so an enabled button that silently
 * does nothing (the reported defect) can no longer happen -- if the guard
 * would block, the button is already disabled, with the reason visible.
 */
export function UploadDropzone({
  phase,
  file,
  errorMessage,
  errorTitle,
  canSubmit,
  blockedReason,
  onFileSelected,
  onRemove,
  onSubmit,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const interactive = phase === "idle" || phase === "fileSelected" || phase === "error";
  const canBrowse = phase === "idle" || phase === "error";

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    onFileSelected(files[0]);
  }

  function openBrowser() {
    if (canBrowse) inputRef.current?.click();
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        role="button"
        tabIndex={canBrowse ? 0 : -1}
        aria-disabled={!canBrowse}
        onClick={openBrowser}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && canBrowse) {
            event.preventDefault();
            openBrowser();
          }
        }}
        onDragOver={(event) => {
          if (!canBrowse) return;
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          if (!canBrowse) return;
          event.preventDefault();
          setDragActive(false);
          handleFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-40 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          phase === "error" ? "border-destructive" : "border-border",
          dragActive && "border-primary bg-primary/5",
          canBrowse && "cursor-pointer"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS}
          className="hidden"
          onChange={(event) => handleFiles(event.target.files)}
        />

        {!file ? (
          <>
            <UploadCloud className="size-8 text-muted-foreground" />
            <p className="text-body">Drag a CSV or Excel file here, or click to browse</p>
            <p className="text-mono-label text-muted-foreground">.csv .xlsx</p>
          </>
        ) : (
          <div
            className="flex w-full max-w-sm items-center justify-between gap-3 rounded-lg bg-card px-3 py-2 ring-1 ring-foreground/10"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex min-w-0 flex-col text-left">
              <span className="truncate text-body">{file.name}</span>
              <span className="text-mono-label text-muted-foreground">{formatFileSize(file.size)}</span>
            </div>
            {interactive && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Remove selected file"
                onClick={onRemove}
              >
                <X className="size-4" />
              </Button>
            )}
          </div>
        )}
      </div>

      {phase === "error" && errorMessage && (
        <Alert variant="destructive">
          <FileWarning />
          <AlertTitle>{errorTitle ?? _DEFAULT_ERROR_TITLE}</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      )}

      {file && phase !== "locked" && (
        <div className="flex flex-col items-start gap-1.5">
          <Button
            type="button"
            disabled={phase === "uploading" || !canSubmit}
            onClick={onSubmit}
            className="self-start"
          >
            {phase === "uploading" && <Loader2 className="size-4 animate-spin" />}
            {phase === "uploading" ? "Mapping…" : "Upload & Map"}
          </Button>
          {blockedReason && (
            <p className="text-mono-label text-muted-foreground">{blockedReason}</p>
          )}
        </div>
      )}
    </div>
  );
}
