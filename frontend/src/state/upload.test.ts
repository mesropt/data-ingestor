import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildHintPayload,
  initialUploadState,
  toDropzonePhase,
  uploadErrorTitle,
  uploadReducer,
  type UploadState,
} from "./upload";
import { ApiError, resolveDateFormat, resolveHint, resolveReconcile, uploadFile } from "../lib/api";
import type {
  DateFormatChoice,
  DateFormatQuestionResponse,
  MappingResponse,
  ReconcileChoice,
  ReconcileQuestionResponse,
  StructuralQuestionResponse,
} from "../lib/types";

function makeFile(name = "novascreen.csv"): File {
  return new File(["cmpd,value\nNVS-1,1.2"], name, { type: "text/csv" });
}

const mappingResponse: MappingResponse = {
  kind: "mapping",
  ready: true,
  source_columns: ["cmpd", "value"],
  field_mappings: [],
  provenance: "fresh-claude",
  upload_token: "token-1",
  escalation: null,
};

const structuralQuestionResponse: StructuralQuestionResponse = {
  kind: "structural_question",
  unsure_about: "header_row_index",
  reason: "guessing risks reading the wrong row as data",
  confidence: 0.4,
  proposal: { header_row_index: 2 },
  alternatives: [],
  evidence_rows: [["a", "b"], ["cmpd", "value"]],
  answerable_by_hint: true,
  upload_token: "token-2",
};

const reconcileQuestionResponse: ReconcileQuestionResponse = {
  kind: "reconcile_question",
  upload_token: "token-r",
  schema_name: "assay-potency",
  vendor: "novascreen",
  conflicts: [
    {
      vendor: "novascreen",
      source_column: "Cmpd",
      master_field: "compound_id",
      map_file_field: "batch_id",
    },
  ],
};

const dateQuestionResponse: DateFormatQuestionResponse = {
  kind: "date_question",
  upload_token: "token-d",
  columns: [
    {
      target_field: "assay_date",
      source_column: "Experiment Date",
      day_first_format: "%d/%m/%Y",
      month_first_format: "%m/%d/%Y",
      example_values: ["03/04/2025"],
      ambiguous_row_count: 5,
    },
  ],
};

describe("uploadReducer", () => {
  it("transitions idle -> fileSelected on SELECT_FILE", () => {
    const file = makeFile();

    const state = uploadReducer(initialUploadState, { type: "SELECT_FILE", file });

    expect(state).toEqual({ phase: "fileSelected", file });
  });

  it("transitions fileSelected -> uploading on SUBMIT_UPLOAD", () => {
    const file = makeFile();
    const selected: UploadState = { phase: "fileSelected", file };

    const state = uploadReducer(selected, { type: "SUBMIT_UPLOAD" });

    expect(state).toEqual({ phase: "uploading", file });
  });

  it("transitions uploading -> mapping on a kind:'mapping' UPLOAD_SUCCESS", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, { type: "UPLOAD_SUCCESS", response: mappingResponse });

    expect(state).toEqual({
      phase: "mapping",
      file,
      response: mappingResponse,
      uploadToken: "token-1",
    });
  });

  it("transitions uploading -> structuralQuestion on a kind:'structural_question' UPLOAD_SUCCESS", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, {
      type: "UPLOAD_SUCCESS",
      response: structuralQuestionResponse,
    });

    expect(state).toEqual({
      phase: "structuralQuestion",
      file,
      response: structuralQuestionResponse,
      uploadToken: "token-2",
    });
  });

  it("transitions uploading -> error on UPLOAD_ERROR, preserving the selected file and carrying the title", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, {
      type: "UPLOAD_ERROR",
      message: "Claude couldn't map this file right now.",
      title: "Upload failed",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "Claude couldn't map this file right now.",
      title: "Upload failed",
    });
  });

  it("transitions structuralQuestion -> resolving on SUBMIT_HINT, threading the upload_token", () => {
    const file = makeFile();
    const question: UploadState = {
      phase: "structuralQuestion",
      file,
      response: structuralQuestionResponse,
      uploadToken: "token-2",
    };

    const state = uploadReducer(question, { type: "SUBMIT_HINT" });

    expect(state).toEqual({ phase: "resolving", file, uploadToken: "token-2" });
  });

  it("transitions resolving -> mapping on a kind:'mapping' HINT_SUCCESS", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolving", file, uploadToken: "token-2" };

    const state = uploadReducer(resolving, { type: "HINT_SUCCESS", response: mappingResponse });

    expect(state).toEqual({
      phase: "mapping",
      file,
      response: mappingResponse,
      uploadToken: "token-1",
    });
  });

  it("transitions resolving -> structuralQuestion on HINT_SUCCESS (a re-submitted hint can still be ambiguous)", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolving", file, uploadToken: "token-2" };
    const stillAmbiguous: StructuralQuestionResponse = {
      ...structuralQuestionResponse,
      upload_token: "token-3",
    };

    const state = uploadReducer(resolving, { type: "HINT_SUCCESS", response: stillAmbiguous });

    expect(state).toEqual({
      phase: "structuralQuestion",
      file,
      response: stillAmbiguous,
      uploadToken: "token-3",
    });
  });

  it("transitions resolving -> dateQuestion on HINT_SUCCESS (a resolved structural hint can still surface an ambiguous date column)", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolving", file, uploadToken: "token-2" };

    const state = uploadReducer(resolving, { type: "HINT_SUCCESS", response: dateQuestionResponse });

    expect(state).toEqual({
      phase: "dateQuestion",
      file,
      response: dateQuestionResponse,
      uploadToken: "token-d",
    });
  });

  it("transitions resolving -> error on HINT_ERROR, preserving the file and carrying the title", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolving", file, uploadToken: "token-2" };

    const state = uploadReducer(resolving, {
      type: "HINT_ERROR",
      message: "This file's structure isn't supported yet.",
      title: "Upload failed",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "This file's structure isn't supported yet.",
      title: "Upload failed",
    });
  });

  it("transitions uploading -> reconcileQuestion on a kind:'reconcile_question' UPLOAD_SUCCESS", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, {
      type: "UPLOAD_SUCCESS",
      response: reconcileQuestionResponse,
    });

    expect(state).toEqual({
      phase: "reconcileQuestion",
      file,
      response: reconcileQuestionResponse,
      uploadToken: "token-r",
    });
  });

  it("transitions reconcileQuestion -> resolvingReconcile on SUBMIT_RECONCILE, threading the upload_token", () => {
    const file = makeFile();
    const question: UploadState = {
      phase: "reconcileQuestion",
      file,
      response: reconcileQuestionResponse,
      uploadToken: "token-r",
    };

    const state = uploadReducer(question, { type: "SUBMIT_RECONCILE" });

    expect(state).toEqual({ phase: "resolvingReconcile", file, uploadToken: "token-r" });
  });

  it("transitions resolvingReconcile -> mapping on a kind:'mapping' RECONCILE_SUCCESS", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingReconcile", file, uploadToken: "token-r" };

    const state = uploadReducer(resolving, {
      type: "RECONCILE_SUCCESS",
      response: mappingResponse,
    });

    expect(state).toEqual({
      phase: "mapping",
      file,
      response: mappingResponse,
      uploadToken: "token-1",
    });
  });

  it("handles a reconcile_question from a resolve identically to the fresh path (defensive re-ask)", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingReconcile", file, uploadToken: "token-r" };
    const stillConflicting: ReconcileQuestionResponse = {
      ...reconcileQuestionResponse,
      upload_token: "token-r2",
    };

    const state = uploadReducer(resolving, {
      type: "RECONCILE_SUCCESS",
      response: stillConflicting,
    });

    expect(state).toEqual({
      phase: "reconcileQuestion",
      file,
      response: stillConflicting,
      uploadToken: "token-r2",
    });
  });

  it("transitions resolvingReconcile -> dateQuestion on RECONCILE_SUCCESS (a resolved reconcile can still surface an ambiguous date column)", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingReconcile", file, uploadToken: "token-r" };

    const state = uploadReducer(resolving, {
      type: "RECONCILE_SUCCESS",
      response: dateQuestionResponse,
    });

    expect(state).toEqual({
      phase: "dateQuestion",
      file,
      response: dateQuestionResponse,
      uploadToken: "token-d",
    });
  });

  it("transitions resolvingReconcile -> error on RECONCILE_ERROR, preserving the file and carrying the title", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingReconcile", file, uploadToken: "token-r" };

    const state = uploadReducer(resolving, {
      type: "RECONCILE_ERROR",
      message: "Couldn't apply your resolution right now.",
      title: "Upload failed",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "Couldn't apply your resolution right now.",
      title: "Upload failed",
    });
  });

  it("transitions uploading -> dateQuestion on a kind:'date_question' UPLOAD_SUCCESS", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, {
      type: "UPLOAD_SUCCESS",
      response: dateQuestionResponse,
    });

    expect(state).toEqual({
      phase: "dateQuestion",
      file,
      response: dateQuestionResponse,
      uploadToken: "token-d",
    });
  });

  it("transitions dateQuestion -> resolvingDateFormat on SUBMIT_DATE_FORMAT, threading the upload_token", () => {
    const file = makeFile();
    const question: UploadState = {
      phase: "dateQuestion",
      file,
      response: dateQuestionResponse,
      uploadToken: "token-d",
    };

    const state = uploadReducer(question, { type: "SUBMIT_DATE_FORMAT" });

    expect(state).toEqual({ phase: "resolvingDateFormat", file, uploadToken: "token-d" });
  });

  it("transitions resolvingDateFormat -> mapping on a kind:'mapping' DATE_FORMAT_SUCCESS", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingDateFormat", file, uploadToken: "token-d" };

    const state = uploadReducer(resolving, {
      type: "DATE_FORMAT_SUCCESS",
      response: mappingResponse,
    });

    expect(state).toEqual({
      phase: "mapping",
      file,
      response: mappingResponse,
      uploadToken: "token-1",
    });
  });

  it("transitions resolvingDateFormat -> error on DATE_FORMAT_ERROR, preserving the file and carrying the title", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolvingDateFormat", file, uploadToken: "token-d" };

    const state = uploadReducer(resolving, {
      type: "DATE_FORMAT_ERROR",
      message: "Couldn't apply your date order right now.",
      title: "Upload failed",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "Couldn't apply your date order right now.",
      title: "Upload failed",
    });
  });

  it("is a no-op for an action that doesn't apply to the current phase", () => {
    // e.g. UPLOAD_SUCCESS while idle -- nothing was ever submitted.
    const state = uploadReducer(initialUploadState, {
      type: "UPLOAD_SUCCESS",
      response: mappingResponse,
    });

    expect(state).toEqual(initialUploadState);
  });

  it("RESET returns to idle from any phase", () => {
    const mapping: UploadState = {
      phase: "mapping",
      file: makeFile(),
      response: mappingResponse,
      uploadToken: "token-1",
    };

    const state = uploadReducer(mapping, { type: "RESET" });

    expect(state).toEqual({ phase: "idle" });
  });
});

describe("toDropzonePhase", () => {
  it("maps idle/fileSelected/uploading/error straight through", () => {
    expect(toDropzonePhase("idle")).toBe("idle");
    expect(toDropzonePhase("fileSelected")).toBe("fileSelected");
    expect(toDropzonePhase("uploading")).toBe("uploading");
    expect(toDropzonePhase("error")).toBe("error");
  });

  it("locks the dropzone for every in-flight question/resolve/mapping phase", () => {
    expect(toDropzonePhase("structuralQuestion")).toBe("locked");
    expect(toDropzonePhase("resolving")).toBe("locked");
    expect(toDropzonePhase("reconcileQuestion")).toBe("locked");
    expect(toDropzonePhase("resolvingReconcile")).toBe("locked");
    expect(toDropzonePhase("mapping")).toBe("locked");
  });

  it("locks the dropzone for the date-question phases too", () => {
    expect(toDropzonePhase("dateQuestion")).toBe("locked");
    expect(toDropzonePhase("resolvingDateFormat")).toBe("locked");
  });
});

describe("uploadErrorTitle", () => {
  it("names a missing-mapper cause for a 503 (the UAT defect: never claim a parse failure here)", () => {
    expect(uploadErrorTitle(new ApiError(503, "no Anthropic credentials configured"))).toBe(
      "The mapper isn't available"
    );
  });

  it("names an over-size cause for a 413", () => {
    expect(uploadErrorTitle(new ApiError(413, "file too large"))).toBe("This file is too large");
  });

  it("names a rejected-extension cause for a 400", () => {
    expect(uploadErrorTitle(new ApiError(400, "unsupported file type"))).toBe(
      "This file type can't be ingested"
    );
  });

  it("falls through to the neutral title for a 500 -- emitted for two unrelated causes, so it must not guess", () => {
    expect(uploadErrorTitle(new ApiError(500, "parse failed"))).toBe("Upload failed");
  });

  it("falls through to the neutral title for a 401 -- emitted for two unrelated causes, so it must not guess", () => {
    expect(uploadErrorTitle(new ApiError(401, "not signed in"))).toBe("Upload failed");
  });

  it("falls through to the neutral title for a plain network/JS error with no status", () => {
    expect(uploadErrorTitle(new Error("network down"))).toBe("Upload failed");
  });
});

describe("buildHintPayload", () => {
  it("includes only the dimensions the user answered", () => {
    expect(buildHintPayload({ headerRowIndex: 2 })).toEqual({ header_row_index: 2 });
  });

  it("returns an empty object when nothing was answered", () => {
    expect(buildHintPayload({})).toEqual({});
  });

  it("includes every answered dimension, mirroring the StructuralHint shape", () => {
    expect(
      buildHintPayload({
        headerRowIndex: 1,
        sheetName: "Sheet2",
        delimiter: ";",
        decimalSeparator: ",",
      })
    ).toEqual({
      header_row_index: 1,
      sheet_name: "Sheet2",
      delimiter: ";",
      decimal_separator: ",",
    });
  });

  it("omits an unanswered dimension even when its value could be falsy-looking (0)", () => {
    expect(buildHintPayload({ headerRowIndex: 0 })).toEqual({ header_row_index: 0 });
    expect(buildHintPayload({})).not.toHaveProperty("header_row_index");
  });
});

describe("api client -- upload/hint/date-format", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("uploadFile POSTs multipart with file + schema_name + headers_only + optional sheet", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const file = makeFile();

    const result = await uploadFile(file, "assay-potency", true, "Sheet1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/upload",
      expect.objectContaining({ method: "POST" })
    );
    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get("file")).toBe(file);
    expect(formData.get("schema_name")).toBe("assay-potency");
    expect(formData.get("headers_only")).toBe("true");
    expect(formData.get("sheet")).toBe("Sheet1");
    // D-10-01/02: the internal FieldSet concept never leaves the browser as
    // a serialized JSON body key anymore -- schema_name replaces it.
    expect(formData.get("field_set")).toBeNull();
    // Never manually set Content-Type -- the browser must set the
    // multipart boundary itself.
    expect(options.headers).toBeUndefined();
    expect(result).toEqual(mappingResponse);
  });

  it("uploadFile omits the sheet field when not provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await uploadFile(makeFile(), "assay-potency", false);

    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData.get("sheet")).toBeNull();
    expect(formData.get("headers_only")).toBe("false");
  });

  it("uploadFile leaves a plain upload's body free of map_file/vendor keys", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await uploadFile(makeFile(), "assay-potency", false);

    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData.get("map_file")).toBeNull();
    expect(formData.get("vendor")).toBeNull();
  });

  it("uploadFile appends map_file + vendor only when a map file is attached (schema_name is always sent once, never duplicated)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(reconcileQuestionResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const mapFile = new File(['{"schema_version":1}'], "master-map.json", {
      type: "application/json",
    });

    const result = await uploadFile(makeFile(), "assay-potency", false, undefined, {
      mapFile,
      vendor: "novascreen",
    });

    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData.get("map_file")).toBe(mapFile);
    expect(formData.get("schema_name")).toBe("assay-potency");
    expect(formData.get("vendor")).toBe("novascreen");
    expect(options.headers).toBeUndefined();
    expect(result).toEqual(reconcileQuestionResponse);
  });

  it("resolveReconcile POSTs {upload_token, choices} to /api/reconcile/resolve with credentials and parses the discriminated response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const choices: ReconcileChoice[] = [
      { vendor: "novascreen", source_column: "Cmpd", decision: "take_map_file" },
    ];

    const result = await resolveReconcile("token-r", choices);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reconcile/resolve",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual({
      upload_token: "token-r",
      choices,
    });
    expect(result).toEqual(mappingResponse);
  });

  it("resolveHint POSTs {upload_token, hint} as JSON and parses the discriminated response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(structuralQuestionResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await resolveHint("token-2", { header_row_index: 1 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/structural-hint/resolve",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual({
      upload_token: "token-2",
      hint: { header_row_index: 1 },
    });
    expect(result).toEqual(structuralQuestionResponse);
  });

  it("resolveDateFormat POSTs {upload_token, choices} to /api/date-format/resolve with credentials and parses the discriminated response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const choices: DateFormatChoice[] = [{ target_field: "assay_date", order: "day_first" }];

    const result = await resolveDateFormat("token-d", choices);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/date-format/resolve",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual({
      upload_token: "token-d",
      choices,
    });
    expect(result).toEqual(mappingResponse);
  });
});
