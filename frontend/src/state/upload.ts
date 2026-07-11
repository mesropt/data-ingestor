/**
 * The Upload screen's state machine (UI-02, D-04) -- a pure reducer with no
 * React dependency, so vitest covers the idle -> fileSelected -> uploading
 * -> mapping | structuralQuestion -> resolving -> mapping | structuralQuestion
 * flow (and its error branches) without rendering anything, mirroring
 * `state/fieldSet.ts`'s own "logic is tested, rendering is
 * gsd-ui-checker-validated" split.
 *
 * The discriminant is `kind` on the server's `/api/upload` and
 * `/api/structural-hint/resolve` response (`lib/types.ts::UploadResponse`,
 * `api/wire.py`'s Pattern 5) -- this module's own `phase` field is the
 * client-side mirror of that discrimination, carried forward through the
 * inline-hint resubmission loop the server itself allows ("a re-submitted
 * hint can still be ambiguous").
 */

import type { MappingResponse, StructuralHintIn, StructuralQuestionResponse, UploadResponse } from "../lib/types";

export type UploadState =
  | { phase: "idle" }
  | { phase: "fileSelected"; file: File }
  | { phase: "uploading"; file: File }
  | { phase: "mapping"; file: File; response: MappingResponse; uploadToken: string }
  | {
      phase: "structuralQuestion";
      file: File;
      response: StructuralQuestionResponse;
      uploadToken: string;
    }
  | { phase: "resolving"; file: File; uploadToken: string }
  | { phase: "error"; file: File; message: string };

export type UploadAction =
  | { type: "SELECT_FILE"; file: File }
  | { type: "SUBMIT_UPLOAD" }
  | { type: "UPLOAD_SUCCESS"; response: UploadResponse }
  | { type: "UPLOAD_ERROR"; message: string }
  | { type: "SUBMIT_HINT" }
  | { type: "HINT_SUCCESS"; response: UploadResponse }
  | { type: "HINT_ERROR"; message: string }
  | { type: "RESET" };

export const initialUploadState: UploadState = { phase: "idle" };

/** Maps the server's discriminated `kind` onto this reducer's own `phase`
 * -- used identically by the fresh-upload branch and the hint-resolve
 * branch, since `/api/structural-hint/resolve` returns the exact same
 * shape `/api/upload` does (Pattern 5, "a re-submitted hint can still be
 * ambiguous"). */
function fromResponse(file: File, response: UploadResponse): UploadState {
  if (response.kind === "mapping") {
    return { phase: "mapping", file, response, uploadToken: response.upload_token };
  }
  return { phase: "structuralQuestion", file, response, uploadToken: response.upload_token };
}

export function uploadReducer(state: UploadState, action: UploadAction): UploadState {
  switch (action.type) {
    case "SELECT_FILE":
      return { phase: "fileSelected", file: action.file };

    case "SUBMIT_UPLOAD":
      if (state.phase !== "fileSelected") return state;
      return { phase: "uploading", file: state.file };

    case "UPLOAD_SUCCESS":
      if (state.phase !== "uploading") return state;
      return fromResponse(state.file, action.response);

    case "UPLOAD_ERROR":
      if (state.phase !== "uploading") return state;
      return { phase: "error", file: state.file, message: action.message };

    case "SUBMIT_HINT":
      if (state.phase !== "structuralQuestion") return state;
      return { phase: "resolving", file: state.file, uploadToken: state.uploadToken };

    case "HINT_SUCCESS":
      if (state.phase !== "resolving") return state;
      return fromResponse(state.file, action.response);

    case "HINT_ERROR":
      if (state.phase !== "resolving") return state;
      return { phase: "error", file: state.file, message: action.message };

    case "RESET":
      return { phase: "idle" };

    default:
      return state;
  }
}

/** The dimensions a human can answer for a `StructureQuestion`
 * (`parsing/hint.py::StructuralHint`'s optional fields). `undefined` means
 * "the user hasn't answered this dimension" -- distinct from `0`/`""`,
 * which are legitimate answers (e.g. `headerRowIndex: 0`, the first row). */
export interface HintAnswers {
  headerRowIndex?: number;
  sheetName?: string;
  delimiter?: string;
  decimalSeparator?: string;
}

/** Builds exactly the `StructuralHintIn` wire shape from only the
 * dimensions the user actually answered -- an unanswered dimension is
 * OMITTED from the payload entirely (not sent as `null`), mirroring
 * `StructuralHint`'s "every field optional" contract so the server only
 * ever sees what the human actually decided. */
export function buildHintPayload(answers: HintAnswers): StructuralHintIn {
  const hint: StructuralHintIn = {};
  if (answers.headerRowIndex !== undefined) hint.header_row_index = answers.headerRowIndex;
  if (answers.sheetName !== undefined) hint.sheet_name = answers.sheetName;
  if (answers.delimiter !== undefined) hint.delimiter = answers.delimiter;
  if (answers.decimalSeparator !== undefined) hint.decimal_separator = answers.decimalSeparator;
  return hint;
}
