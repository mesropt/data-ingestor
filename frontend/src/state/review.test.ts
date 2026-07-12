import { afterEach, describe, expect, it, vi } from "vitest";

import {
  applyGateRejection,
  gateRejection,
  isAutoApplied,
  isReady,
  reopenField,
  resolutionProgress,
  resolveByAccept,
  resolveByChip,
  resolveByDropdown,
  toConfirmPayload,
} from "./review";
import { ApiError, confirm, GateRejected } from "../lib/api";
import type { FieldMappingOut, FieldSetPayload, MappingResponse, UnclearDetail } from "../lib/types";

function makeMapping(overrides: Partial<FieldMappingOut> = {}): FieldMappingOut {
  return {
    target_field: "compound_id",
    source_column: "cmpd",
    confidence: 0.92,
    reasoning: "the column header matches compound_id closely",
    needs_confirmation: false,
    inferred_value: null,
    alternatives: [],
    validator_note: null,
    ...overrides,
  };
}

describe("isReady", () => {
  it("mirrors MappingProposal.is_ready: true only when no field needs confirmation", () => {
    const mappings = [makeMapping({ target_field: "a" }), makeMapping({ target_field: "b" })];
    expect(isReady(mappings)).toBe(true);
  });

  it("is false when any field still needs confirmation", () => {
    const mappings = [
      makeMapping({ target_field: "a" }),
      makeMapping({ target_field: "b", needs_confirmation: true }),
    ];
    expect(isReady(mappings)).toBe(false);
  });

  it("is false for an empty mapping (Python's all([]) trap -- an empty proposal is never ready)", () => {
    expect(isReady([])).toBe(false);
  });

  it("stays false for a field with source_column null but inferred_value set, until resolved (MAP-02)", () => {
    const mappings = [
      makeMapping({
        target_field: "unit",
        source_column: null,
        inferred_value: "nM",
        needs_confirmation: true,
      }),
    ];
    expect(isReady(mappings)).toBe(false);
  });
});

describe("resolutionProgress", () => {
  it("counts clear vs total fields", () => {
    const mappings = [
      makeMapping({ target_field: "a" }),
      makeMapping({ target_field: "b", needs_confirmation: true }),
      makeMapping({ target_field: "c", needs_confirmation: true }),
    ];
    expect(resolutionProgress(mappings)).toEqual({ clear: 1, total: 3 });
  });
});

describe("resolveByChip (D-02a)", () => {
  it("sets source_column + confidence from the chip and clears needs_confirmation for that field only", () => {
    const mappings = [
      makeMapping({ target_field: "a", needs_confirmation: true, source_column: null }),
      makeMapping({ target_field: "b", needs_confirmation: true, source_column: null }),
    ];

    const result = resolveByChip(mappings, "a", { source_column: "cmpd_id", confidence: 0.81 });

    expect(result[0]).toMatchObject({
      target_field: "a",
      source_column: "cmpd_id",
      confidence: 0.81,
      needs_confirmation: false,
    });
    // field b untouched
    expect(result[1]).toEqual(mappings[1]);
  });
});

describe("resolveByAccept (D-02b)", () => {
  it("keeps the top source_column as-is and clears needs_confirmation", () => {
    const mappings = [
      makeMapping({ target_field: "a", needs_confirmation: true, source_column: "cmpd", confidence: 0.6 }),
    ];

    const result = resolveByAccept(mappings, "a");

    expect(result[0]).toMatchObject({
      target_field: "a",
      source_column: "cmpd",
      confidence: 0.6,
      needs_confirmation: false,
    });
  });

  it("also clears needs_confirmation when source_column is null (accepting an inferred_value, MAP-02)", () => {
    const mappings = [
      makeMapping({
        target_field: "unit",
        needs_confirmation: true,
        source_column: null,
        inferred_value: "nM",
      }),
    ];

    const result = resolveByAccept(mappings, "unit");

    expect(result[0]).toMatchObject({
      target_field: "unit",
      source_column: null,
      inferred_value: "nM",
      needs_confirmation: false,
    });
  });
});

describe("resolveByDropdown (D-02c)", () => {
  it("sets any source_column from the full column list and clears needs_confirmation", () => {
    const mappings = [makeMapping({ target_field: "a", needs_confirmation: true, source_column: null })];

    const result = resolveByDropdown(mappings, "a", "unexpected_column_17");

    expect(result[0]).toMatchObject({
      target_field: "a",
      source_column: "unexpected_column_17",
      needs_confirmation: false,
    });
  });
});

describe("reopenField (re-edit a resolved/green field)", () => {
  it("flips a clear field back to needs_confirmation=true so FieldRow renders its resolution controls again", () => {
    const mappings = [
      makeMapping({ target_field: "assay_date", needs_confirmation: false, source_column: "assay" }),
    ];

    const result = reopenField(mappings, "assay_date");

    expect(result[0]).toMatchObject({
      target_field: "assay_date",
      needs_confirmation: true,
    });
  });

  it("keeps the field's current source_column and alternatives intact -- reopening never clears them", () => {
    const mappings = [
      makeMapping({
        target_field: "assay_date",
        needs_confirmation: false,
        source_column: "assay",
        alternatives: [{ source_column: "run_date", confidence: 0.7 }],
      }),
    ];

    const result = reopenField(mappings, "assay_date");

    expect(result[0]).toMatchObject({
      source_column: "assay",
      alternatives: [{ source_column: "run_date", confidence: 0.7 }],
    });
  });

  it("only touches the named field -- every other field's object reference is untouched", () => {
    const mappings = [
      makeMapping({ target_field: "a", needs_confirmation: false }),
      makeMapping({ target_field: "b", needs_confirmation: false }),
    ];

    const result = reopenField(mappings, "a");

    expect(result[1]).toBe(mappings[1]);
  });

  it("is a no-op shape-wise on an already-amber field (idempotent re-flag)", () => {
    const mappings = [makeMapping({ target_field: "a", needs_confirmation: true })];

    const result = reopenField(mappings, "a");

    expect(result[0].needs_confirmation).toBe(true);
  });
});

describe("applyGateRejection (P1 server 422 re-flags exactly the rejected fields)", () => {
  it("sets needs_confirmation=true for every named field, leaving others untouched", () => {
    const mappings = [
      makeMapping({ target_field: "assay_date", needs_confirmation: false, source_column: "assay" }),
      makeMapping({ target_field: "compound_id", needs_confirmation: false, source_column: "cmpd" }),
    ];

    const result = applyGateRejection(mappings, ["assay_date"]);

    expect(result[0]).toMatchObject({ target_field: "assay_date", needs_confirmation: true });
    // untouched field keeps its exact object reference
    expect(result[1]).toBe(mappings[1]);
  });

  it("preserves the rejected field's source_column/alternatives -- the server rejected the VALUE, not the slot", () => {
    const mappings = [
      makeMapping({
        target_field: "assay_date",
        needs_confirmation: false,
        source_column: "assay",
        confidence: 1.0,
      }),
    ];

    const result = applyGateRejection(mappings, ["assay_date"]);

    expect(result[0]).toMatchObject({
      target_field: "assay_date",
      source_column: "assay",
      confidence: 1.0,
      needs_confirmation: true,
    });
  });

  it("re-flags multiple named fields in one pass", () => {
    const mappings = [
      makeMapping({ target_field: "a", needs_confirmation: false }),
      makeMapping({ target_field: "b", needs_confirmation: false }),
      makeMapping({ target_field: "c", needs_confirmation: false }),
    ];

    const result = applyGateRejection(mappings, ["a", "c"]);

    expect(result.map((m) => m.needs_confirmation)).toEqual([true, false, true]);
  });

  it("is a no-op when unclearFieldNames is empty -- no field is spuriously re-flagged", () => {
    const mappings = [makeMapping({ target_field: "a", needs_confirmation: false })];

    const result = applyGateRejection(mappings, []);

    expect(result[0]).toBe(mappings[0]);
  });
});

describe("toConfirmPayload", () => {
  it("produces {upload_token, field_set, field_mappings, save_profile, export} matching /api/confirm's contract", () => {
    const fieldSet: FieldSetPayload = { name: "novascreen-v1", fields: [] };
    const mappings = [makeMapping({ target_field: "a" })];

    const payload = toConfirmPayload("token-1", fieldSet, mappings, {
      saveProfile: true,
      export: true,
    });

    expect(payload).toEqual({
      upload_token: "token-1",
      field_set: fieldSet,
      field_mappings: [
        {
          target_field: "a",
          source_column: "cmpd",
          confidence: 0.92,
          reasoning: "the column header matches compound_id closely",
          needs_confirmation: false,
          inferred_value: null,
          alternatives: [],
        },
      ],
      save_profile: true,
      export: true,
    });
  });

  it("never sends a trusted top-level ready flag -- the shape has no such field", () => {
    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: false,
      export: false,
    });
    expect(payload).not.toHaveProperty("ready");
    expect(payload).not.toHaveProperty("is_ready");
  });

  it("carries schema_name + vendor additively when supplied (ALIAS-04 crosswalk accrual)", () => {
    const fieldSet: FieldSetPayload = { name: "novascreen-v1", fields: [] };
    const mappings = [makeMapping({ target_field: "a" })];

    const payload = toConfirmPayload("token-1", fieldSet, mappings, {
      saveProfile: true,
      export: true,
      schemaName: "assay-potency",
      vendor: "novascreen",
    });

    expect(payload).toMatchObject({ schema_name: "assay-potency", vendor: "novascreen" });
  });

  it("omits schema_name + vendor entirely when not supplied -- the no-schema payload is byte-identical to today's", () => {
    const fieldSet: FieldSetPayload = { name: "novascreen-v1", fields: [] };
    const mappings = [makeMapping({ target_field: "a" })];

    const payload = toConfirmPayload("token-1", fieldSet, mappings, {
      saveProfile: true,
      export: true,
    });

    expect(payload).not.toHaveProperty("schema_name");
    expect(payload).not.toHaveProperty("vendor");
  });
});

describe("isAutoApplied", () => {
  it("is true only for the auto-applied-from-profile provenance (UI-06 money shot)", () => {
    expect(isAutoApplied("auto-applied-from-profile")).toBe(true);
    expect(isAutoApplied("fresh-claude")).toBe(false);
    expect(isAutoApplied(null)).toBe(false);
  });

  it("drives an already-ready gate when combined with a zero-needs_confirmation mapping response", () => {
    const response: MappingResponse = {
      kind: "mapping",
      ready: true,
      source_columns: ["cmpd", "value"],
      field_mappings: [makeMapping({ target_field: "a" }), makeMapping({ target_field: "b" })],
      provenance: "auto-applied-from-profile",
      upload_token: "token-2",
      escalation: null,
      remembered_vendor: null,
      remembered_vendor_source: null,
      vendor_candidates: [],
    };

    expect(isAutoApplied(response.provenance)).toBe(true);
    expect(isReady(response.field_mappings)).toBe(true);
  });
});

describe("api.confirm -- /api/confirm", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("POSTs the confirm payload as JSON and returns the parsed ConfirmResponse on 200", async () => {
    const confirmResponse = {
      ready: true,
      manifest: { rows: 3 },
      profile_id: "profile-1",
      export: { csv_url: "/api/export/run-1/csv" },
    };
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(confirmResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });
    const result = await confirm(payload);

    expect(fetchMock).toHaveBeenCalledWith("/api/confirm", expect.objectContaining({ method: "POST" }));
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual(payload);
    expect(result).toEqual(confirmResponse);
  });

  it("surfaces a 422 gate rejection as a typed GateRejected carrying unclear_fields, never a generic ApiError", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { unclear_fields: ["assay_type", "unit"] } }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toBeInstanceOf(GateRejected);
    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["assay_type", "unit"],
    });
  });

  it("also surfaces a FieldCoverageError 422 ({missing_fields}) as a GateRejected carrying those names", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { missing_fields: ["assay_date"], unknown_fields: [] } }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toBeInstanceOf(GateRejected);
    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["assay_date"],
    });
  });

  it("re-raises a 422 that names NO field as an ApiError carrying the server's own message, never an empty GateRejected", async () => {
    // /api/confirm also 422s with a plain-string detail -- a field-set parse
    // failure, the CR-01 signature mismatch, an unresolved date column. Those
    // name no field, so there is nothing for `applyGateRejection` to re-flag:
    // swallowing them into an empty GateRejected rendered a rejection alert
    // with no content and hid the real cause from the curator.
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: "field set does not match the uploaded file" }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.not.toBeInstanceOf(GateRejected);
    await expect(confirm(payload)).rejects.toBeInstanceOf(ApiError);
    await expect(confirm(payload)).rejects.toMatchObject({
      status: 422,
      detail: "field set does not match the uploaded file",
    });
  });

  it("carries unclear_details with the real reason AND keeps unclearFields as the plain name array", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            detail: {
              unclear_fields: ["value"],
              unclear_details: [
                { field: "value", reason: "12.5 is below the declared minimum 100", source_column: "potency" },
              ],
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } }
        )
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["value"],
      unclearDetails: [{ field: "value", reason: "12.5 is below the declared minimum 100", sourceColumn: "potency" }],
    });
  });

  it("falls back to reason:null details derived from unclear_fields when an older body omits unclear_details", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { unclear_fields: ["assay_type", "unit"] } }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["assay_type", "unit"],
      unclearDetails: [
        { field: "assay_type", reason: null, sourceColumn: null },
        { field: "unit", reason: null, sourceColumn: null },
      ],
    });
  });

  it("does not throw on a malformed unclear_details -- drops unparseable entries and still names every field", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            detail: {
              unclear_fields: ["value", "unit"],
              unclear_details: "nope",
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } }
        )
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["value", "unit"],
      unclearDetails: [
        { field: "value", reason: null, sourceColumn: null },
        { field: "unit", reason: null, sourceColumn: null },
      ],
    });
  });

  it("drops non-object / missing-field entries from an unclear_details array without throwing", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            detail: {
              unclear_fields: ["value"],
              unclear_details: [null, { reason: "x" }],
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } }
        )
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const payload = toConfirmPayload("token-1", { name: null, fields: [] }, [], {
      saveProfile: true,
      export: true,
    });

    await expect(confirm(payload)).rejects.toMatchObject({
      unclearFields: ["value"],
      unclearDetails: [{ field: "value", reason: null, sourceColumn: null }],
    });
  });
});

describe("gateRejection (shapes a rejection's fields for the Review alert)", () => {
  it("maps each detail to {name, reason}, preserving order and never dropping a null-reason field", () => {
    const details: UnclearDetail[] = [
      { field: "value", reason: "12.5 is below the declared minimum 100", sourceColumn: "potency" },
      { field: "assay_type", reason: null, sourceColumn: null },
    ];

    const result = gateRejection(details);

    expect(result).toEqual({
      fields: [
        { name: "value", reason: "12.5 is below the declared minimum 100" },
        { name: "assay_type", reason: null },
      ],
    });
  });
});
