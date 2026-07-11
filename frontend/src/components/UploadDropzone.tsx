import { useRef, useState } from "react";
import { FileWarning, Loader2, UploadCloud, X } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPTED_EXTENSIONS = ".csv,.xlsx,.xls";

export type DropzonePhase = "idle" | "fileSelected" | "uploading" | "error" | "locked";

interface UploadDropzoneProps {
  phase: DropzonePhase;
  file: File | null;
  errorMessage?: string | null;
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
 * destructive Alert, file preserved so the curator can retry without
 * re-picking it). Drives entirely off `state/upload.ts`'s reducer via the
 * Upload screen -- this component holds no upload state of its own beyond
 * the transient drag-hover visual. `locked` is a fifth, UI-SPEC-implied
 * state: once a structural question is showing (D-04), the dropzone
 * freezes on its file chip with no controls -- the inline
 * `StructuralHintPanel` below owns the next action, so the dropzone must
 * not offer a second, conflicting "Upload & Map" at the same time.
 */
export function UploadDropzone({
  phase,
  file,
  errorMessage,
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
            <p className="text-mono-label text-muted-foreground">.csv .xlsx .xls</p>
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
          <AlertTitle>This file couldn't be read as a table</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      )}

      {file && phase !== "locked" && (
        <Button
          type="button"
          disabled={phase === "uploading"}
          onClick={onSubmit}
          className="self-start"
        >
          {phase === "uploading" && <Loader2 className="size-4 animate-spin" />}
          {phase === "uploading" ? "Mapping…" : "Upload & Map"}
        </Button>
      )}
    </div>
  );
}
