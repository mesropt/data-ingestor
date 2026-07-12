import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MAX_FIELDS,
  addField,
  createEmptyFieldSetDraft,
  editField,
  removeField,
  toFieldSetPayload,
} from "./fieldSet";
import { ApiError, getFieldSet, listFieldSets, saveFieldSet } from "../lib/api";

describe("addField", () => {
  it("appends a default field (required=true, type='none')", () => {
    const before = createEmptyFieldSetDraft();

    const after = addField(before);

    expect(after.fields).toHaveLength(1);
    expect(after.fields[0]).toMatchObject({
      name: "",
      type: "none",
      required: true,
    });
    // Immutable: the original draft is untouched.
    expect(before.fields).toHaveLength(0);
  });

  it("blocks adding beyond MAX_FIELDS (50) -- a UX mirror of loader.py's authoritative cap", () => {
    let state = createEmptyFieldSetDraft();
    for (let i = 0; i < MAX_FIELDS; i += 1) {
      state = addField(state);
    }
    expect(state.fields).toHaveLength(MAX_FIELDS);

    const blocked = addField(state);

    expect(blocked.fields).toHaveLength(MAX_FIELDS);
  });
});

describe("removeField", () => {
  it("drops the field with the given id", () => {
    let state = addField(createEmptyFieldSetDraft());
    state = addField(state);
    const idToRemove = state.fields[0].id;

    const after = removeField(state, idToRemove);

    expect(after.fields).toHaveLength(1);
    expect(after.fields.find((f) => f.id === idToRemove)).toBeUndefined();
  });
});

describe("editField", () => {
  it("updates a single attribute immutably", () => {
    const state = addField(createEmptyFieldSetDraft());
    const id = state.fields[0].id;

    const after = editField(state, id, { name: "compound_id" });

    expect(after.fields[0].name).toBe("compound_id");
    // Original state's field is untouched (immutability).
    expect(state.fields[0].name).toBe("");
    expect(after).not.toBe(state);
    expect(after.fields[0]).not.toBe(state.fields[0]);
  });
});

describe("toFieldSetPayload", () => {
  it("produces exactly the {name, fields:[...]} FieldSet.to_dict() shape", () => {
    let state = createEmptyFieldSetDraft();
    state = { ...state, name: "novascreen-v1" };
    state = addField(state);
    state = editField(state, state.fields[0].id, {
      name: "compound_id",
      description: "The compound identifier",
      type: "text",
      required: true,
    });

    const payload = toFieldSetPayload(state);

    expect(payload).toEqual({
      name: "novascreen-v1",
      fields: [
        {
          name: "compound_id",
          description: "The compound identifier",
          type: "text",
          allowed_values: null,
          unit: null,
          required: true,
          min: null,
          max: null,
          date_format: null,
        },
      ],
    });
  });

  it("serializes min/max only for number/integer types", () => {
    let state = createEmptyFieldSetDraft();
    state = addField(state);
    state = editField(state, state.fields[0].id, {
      name: "value",
      type: "number",
      min: 0,
      max: 1000,
    });

    const payload = toFieldSetPayload(state);

    expect(payload.fields[0].min).toBe(0);
    expect(payload.fields[0].max).toBe(1000);
  });

  it("drops min/max for a text field even if a stray value lingers in draft state", () => {
    let state = createEmptyFieldSetDraft();
    state = addField(state);
    state = editField(state, state.fields[0].id, {
      name: "notes",
      type: "text",
      min: 5,
      max: 10,
    });

    const payload = toFieldSetPayload(state);

    expect(payload.fields[0].min).toBeNull();
    expect(payload.fields[0].max).toBeNull();
  });

  it("serializes date_format only for the date type", () => {
    let state = createEmptyFieldSetDraft();
    state = addField(state);
    state = editField(state, state.fields[0].id, {
      name: "assay_date",
      type: "date",
      dateFormat: "%Y-%m-%d",
    });

    const payload = toFieldSetPayload(state);

    expect(payload.fields[0].date_format).toBe("%Y-%m-%d");
  });

  it("drops date_format for a non-date field even if a stray value lingers in draft state", () => {
    let state = createEmptyFieldSetDraft();
    state = addField(state);
    state = editField(state, state.fields[0].id, {
      name: "target",
      type: "text",
      dateFormat: "%Y-%m-%d",
    });

    const payload = toFieldSetPayload(state);

    expect(payload.fields[0].date_format).toBeNull();
  });

  it("maps type 'none' to a null type", () => {
    let state = createEmptyFieldSetDraft();
    state = addField(state);

    const payload = toFieldSetPayload(state);

    expect(payload.fields[0].type).toBeNull();
  });
});

describe("api client", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("saveFieldSet POSTs to /api/field-sets with the {name, field_set} body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "abc123" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await saveFieldSet("novascreen-v1", {
      name: "novascreen-v1",
      fields: [],
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/field-sets",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
    const [, options] = fetchMock.mock.calls[0];
    expect(JSON.parse(options.body as string)).toEqual({
      name: "novascreen-v1",
      field_set: { name: "novascreen-v1", fields: [] },
    });
    expect(result).toEqual({ id: "abc123" });
  });

  it("listFieldSets GETs /api/field-sets", async () => {
    const templates = [{ id: "abc123", name: "novascreen-v1", field_set: { name: null, fields: [] } }];
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(templates), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await listFieldSets();

    expect(fetchMock).toHaveBeenCalledWith("/api/field-sets", expect.objectContaining({ method: "GET" }));
    expect(result).toEqual(templates);
  });

  it("getFieldSet GETs /api/field-sets/{id}", async () => {
    const fieldSet = { name: "novascreen-v1", fields: [] };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(fieldSet), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const result = await getFieldSet("abc123");

    expect(fetchMock).toHaveBeenCalledWith("/api/field-sets/abc123", expect.objectContaining({ method: "GET" }));
    expect(result).toEqual(fieldSet);
  });

  it("surfaces a 422 as a typed ApiError carrying the server detail", async () => {
    // A fresh Response per call -- Response.json() can only be read once
    // per instance, and this test calls saveFieldSet twice.
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: "field name too long" }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        })
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(saveFieldSet("bad", { name: "bad", fields: [] })).rejects.toBeInstanceOf(ApiError);
    await expect(saveFieldSet("bad", { name: "bad", fields: [] })).rejects.toMatchObject({
      status: 422,
      detail: "field name too long",
    });
  });
});
