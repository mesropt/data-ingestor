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

import { ApiError } from "../lib/api";
import type {
  DateFormatQuestionResponse,
  MappingResponse,
  ReconcileQuestionResponse,
  SheetGroupResponse,
  SheetQuestionResponse,
  StructuralHintIn,
  StructuralQuestionResponse,
  UploadResponse,
} from "../lib/types";
import { assertNever } from "../lib/utils";

/** The neutral title shown whenever the client cannot honestly name the
 * cause -- either a non-`ApiError` (network/JS failure, no status at all)
 * or an `ApiError` status the server reuses for two or more unrelated
 * causes. Naming a cause the server didn't actually report is the exact
 * defect this module fixes (principle 2, "never guess silently", applies
 * to our own error copy just as much as to Claude's mappings). */
const _NEUTRAL_TITLE = "Upload failed";

/** Maps ONLY the three `/api/upload` status codes each of which the server
 * emits for a single unambiguous cause (`api/routes/upload.py`). Every
 * other status -- notably 401 (a sign-in gate OR rejected Anthropic
 * credentials) and 500 (a parse `ValueError` OR an `anthropic.APIError`) --
 * is deliberately absent: the client cannot tell those two causes apart, so
 * it must not guess which one just happened. */
const _TITLE_BY_STATUS: Record<number, string> = {
  503: "The mapper isn't available",
  413: "This file is too large",
  400: "This file type can't be ingested",
};

/** Derives the upload error alert's TITLE from the error itself, never from
 * an assumption -- the companion to `consequenceMessage` (screens/Upload.tsx),
 * which already renders the server's own detail correctly. Only the title
 * used to lie (hardcoded to a parse-failure claim for every error); this
 * closes that gap without ever asserting a cause the server did not report. */
export function uploadErrorTitle(error: unknown): string {
  if (error instanceof ApiError) {
    return _TITLE_BY_STATUS[error.status] ?? _NEUTRAL_TITLE;
  }
  return _NEUTRAL_TITLE;
}

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
  | {
      phase: "reconcileQuestion";
      file: File;
      response: ReconcileQuestionResponse;
      uploadToken: string;
    }
  | { phase: "resolvingReconcile"; file: File; uploadToken: string }
  | {
      phase: "dateQuestion";
      file: File;
      response: DateFormatQuestionResponse;
      uploadToken: string;
    }
  | { phase: "resolvingDateFormat"; file: File; uploadToken: string }
  // The sheet-question pair deviates from its siblings in TWO deliberate
  // ways (11-UI-SPEC §Screens 1 "Error" state): `resolvingSheets` CARRIES
  // the response so the panel never unmounts mid-flight, and a resolve
  // failure lands back on `sheetQuestion` with `errorMessage` set -- never
  // on the `error` phase, which would tear the panel down and destroy every
  // tick and Schema choice the curator just made.
  | {
      phase: "sheetQuestion";
      file: File;
      response: SheetQuestionResponse;
      uploadToken: string;
      errorMessage: string | null;
    }
  | {
      phase: "resolvingSheets";
      file: File;
      response: SheetQuestionResponse;
      uploadToken: string;
    }
  // N independent datasets exist server-side and the group screen (11-10) takes
  // over; the dropzone stays locked. NOT terminal any more: it carries the
  // QUESTION it came from and the token that still answers it, so Back can
  // re-open the table/sheet selection without re-uploading the workbook. The
  // server keeps the manifest and the file under that same token for exactly
  // this reason (`routes/sheets.py` GETs the entry, it no longer POPs it).
  | {
      phase: "sheetGroup";
      file: File;
      response: SheetGroupResponse;
      groupId: string;
      question?: SheetQuestionResponse;
      uploadToken?: string;
    }
  | { phase: "error"; file: File; message: string; title: string };

export type UploadAction =
  | { type: "SELECT_FILE"; file: File }
  | { type: "SUBMIT_UPLOAD" }
  | { type: "UPLOAD_SUCCESS"; response: UploadResponse }
  | { type: "UPLOAD_ERROR"; message: string; title: string }
  | { type: "SUBMIT_HINT" }
  | { type: "HINT_SUCCESS"; response: UploadResponse }
  | { type: "HINT_ERROR"; message: string; title: string }
  | { type: "SUBMIT_RECONCILE" }
  | { type: "RECONCILE_SUCCESS"; response: UploadResponse }
  | { type: "RECONCILE_ERROR"; message: string; title: string }
  | { type: "SUBMIT_DATE_FORMAT" }
  | { type: "DATE_FORMAT_SUCCESS"; response: UploadResponse }
  | { type: "DATE_FORMAT_ERROR"; message: string; title: string }
  // SHEETS_ERROR carries no `title`: it never reaches the dropzone's error
  // surface -- it renders inside the panel as UI-SPEC's destructive Alert,
  // with every selection preserved.
  | { type: "SUBMIT_SHEETS" }
  | { type: "SHEETS_SUCCESS"; response: UploadResponse }
  | { type: "SHEETS_ERROR"; message: string }
  | { type: "BACK_TO_SHEETS" }
  | { type: "RESET" };

export const initialUploadState: UploadState = { phase: "idle" };

/** Maps the server's discriminated `kind` onto this reducer's own `phase`
 * -- used identically by the fresh-upload branch and the hint-resolve
 * branch, since `/api/structural-hint/resolve` returns the exact same
 * shape `/api/upload` does (Pattern 5, "a re-submitted hint can still be
 * ambiguous"). */
function fromResponse(file: File, response: UploadResponse): UploadState {
  switch (response.kind) {
    case "mapping":
      return { phase: "mapping", file, response, uploadToken: response.upload_token };
    case "reconcile_question":
      return { phase: "reconcileQuestion", file, response, uploadToken: response.upload_token };
    case "structural_question":
      return { phase: "structuralQuestion", file, response, uploadToken: response.upload_token };
    case "date_question":
      return { phase: "dateQuestion", file, response, uploadToken: response.upload_token };
    case "sheet_question":
      return {
        phase: "sheetQuestion",
        file,
        response,
        uploadToken: response.upload_token,
        errorMessage: null,
      };
    case "sheet_group":
      return { phase: "sheetGroup", file, response, groupId: response.group_id };
    default:
      // Exhaustiveness: a future 5th `kind` is a compile-time error here,
      // not a silent fall-through into the wrong phase.
      return assertNever(response);
  }
}

/** The dropzone only knows its own 5 visual states (`components/
 * UploadDropzone.tsx::DropzonePhase`) -- this maps the reducer's richer
 * `phase` onto them. Lives here (not in `screens/Upload.tsx`) so it is a
 * pure, vitest-covered function under the `node` test environment with no
 * DOM dependency -- its return type is the SAME literal union
 * `DropzonePhase` declares, so it satisfies that prop structurally without
 * this module importing anything from the components layer. `mapping`
 * never actually renders (the screen navigates away via `onMapped` the
 * instant a mapping response arrives), but is included for exhaustiveness. */
export function toDropzonePhase(
  phase: UploadState["phase"]
): "idle" | "fileSelected" | "uploading" | "error" | "locked" {
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
    case "dateQuestion":
    case "resolvingDateFormat":
    case "sheetQuestion":
    case "resolvingSheets":
    case "sheetGroup":
    case "mapping":
      return "locked";
    default:
      return "idle";
  }
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
      return { phase: "error", file: state.file, message: action.message, title: action.title };

    case "SUBMIT_HINT":
      if (state.phase !== "structuralQuestion") return state;
      return { phase: "resolving", file: state.file, uploadToken: state.uploadToken };

    case "HINT_SUCCESS":
      if (state.phase !== "resolving") return state;
      return fromResponse(state.file, action.response);

    case "HINT_ERROR":
      if (state.phase !== "resolving") return state;
      return { phase: "error", file: state.file, message: action.message, title: action.title };

    case "SUBMIT_RECONCILE":
      if (state.phase !== "reconcileQuestion") return state;
      return { phase: "resolvingReconcile", file: state.file, uploadToken: state.uploadToken };

    case "RECONCILE_SUCCESS":
      if (state.phase !== "resolvingReconcile") return state;
      return fromResponse(state.file, action.response);

    case "RECONCILE_ERROR":
      if (state.phase !== "resolvingReconcile") return state;
      return { phase: "error", file: state.file, message: action.message, title: action.title };

    case "SUBMIT_DATE_FORMAT":
      if (state.phase !== "dateQuestion") return state;
      return { phase: "resolvingDateFormat", file: state.file, uploadToken: state.uploadToken };

    case "DATE_FORMAT_SUCCESS":
      if (state.phase !== "resolvingDateFormat") return state;
      return fromResponse(state.file, action.response);

    case "DATE_FORMAT_ERROR":
      if (state.phase !== "resolvingDateFormat") return state;
      return { phase: "error", file: state.file, message: action.message, title: action.title };

    case "SUBMIT_SHEETS":
      if (state.phase !== "sheetQuestion") return state;
      return {
        phase: "resolvingSheets",
        file: state.file,
        response: state.response,
        uploadToken: state.uploadToken,
      };

    case "SHEETS_SUCCESS": {
      if (state.phase !== "resolvingSheets") return state;
      const next = fromResponse(state.file, action.response);
      // Carry the question and its token INTO the group phase -- they are what
      // Back re-opens, and this is the only moment both are in hand.
      return next.phase === "sheetGroup"
        ? { ...next, question: state.response, uploadToken: state.uploadToken }
        : next;
    }

    case "BACK_TO_SHEETS":
      // Back to the selection screen, with every tick and Schema choice as the
      // curator left them. Refused when the question was not retained rather
      // than faked from scratch: a reconstructed question is a different
      // question, and it would quietly drop their answers.
      if (state.phase !== "sheetGroup" || !state.question || !state.uploadToken) return state;
      return {
        phase: "sheetQuestion",
        file: state.file,
        response: state.question,
        uploadToken: state.uploadToken,
        errorMessage: null,
      };

    case "SHEETS_ERROR":
      // Back to the QUESTION, never to `error`: the panel stays mounted, so
      // the curator's ticks and per-sheet Schema choices survive the failure
      // (UI-SPEC: "all selections preserved").
      if (state.phase !== "resolvingSheets") return state;
      return {
        phase: "sheetQuestion",
        file: state.file,
        response: state.response,
        uploadToken: state.uploadToken,
        errorMessage: action.message,
      };

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
