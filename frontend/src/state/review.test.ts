import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isAutoApplied,
  isReady,
  resolutionProgress,
  resolveByAccept,
  resolveByChip,
  resolveByDropdown,
  toConfirmPayload,
} from "./review";
import { confirm, GateRejected } from "../lib/api";
import type { FieldMappingOut, FieldSetPayload, MappingResponse } from "../lib/types";

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
});
