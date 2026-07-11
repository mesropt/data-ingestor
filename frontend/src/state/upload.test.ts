import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildHintPayload,
  initialUploadState,
  uploadReducer,
  type UploadState,
} from "./upload";
import { resolveHint, uploadFile } from "../lib/api";
import type { FieldSetPayload, MappingResponse, StructuralQuestionResponse } from "../lib/types";

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

  it("transitions uploading -> error on UPLOAD_ERROR, preserving the selected file", () => {
    const file = makeFile();
    const uploading: UploadState = { phase: "uploading", file };

    const state = uploadReducer(uploading, {
      type: "UPLOAD_ERROR",
      message: "Claude couldn't map this file right now.",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "Claude couldn't map this file right now.",
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

  it("transitions resolving -> error on HINT_ERROR, preserving the file", () => {
    const file = makeFile();
    const resolving: UploadState = { phase: "resolving", file, uploadToken: "token-2" };

    const state = uploadReducer(resolving, {
      type: "HINT_ERROR",
      message: "This file's structure isn't supported yet.",
    });

    expect(state).toEqual({
      phase: "error",
      file,
      message: "This file's structure isn't supported yet.",
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

describe("api client -- upload/hint", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("uploadFile POSTs multipart with file + field_set JSON + headers_only + optional sheet", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(mappingResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const fieldSet: FieldSetPayload = { name: "novascreen-v1", fields: [] };
    const file = makeFile();

    const result = await uploadFile(file, fieldSet, true, "Sheet1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/upload",
      expect.objectContaining({ method: "POST" })
    );
    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get("file")).toBe(file);
    expect(JSON.parse(formData.get("field_set") as string)).toEqual(fieldSet);
    expect(formData.get("headers_only")).toBe("true");
    expect(formData.get("sheet")).toBe("Sheet1");
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

    await uploadFile(makeFile(), { name: null, fields: [] }, false);

    const [, options] = fetchMock.mock.calls[0];
    const formData = options.body as FormData;
    expect(formData.get("sheet")).toBeNull();
    expect(formData.get("headers_only")).toBe("false");
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
});
