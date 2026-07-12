import { describe, expect, it } from "vitest";

import {
  MAX_FIELDS,
  canAddField,
  deleteFieldWarning,
  fieldSummaryLine,
  fromCanonicalField,
  toFieldPayload,
  type SchemaFieldDraft,
} from "./schemaEdit";
import type { CanonicalFieldPayload, SchemaOut } from "../lib/types";

function makeField(overrides: Partial<CanonicalFieldPayload> = {}): CanonicalFieldPayload {
  return {
    name: "compound_id",
    description: null,
    type: null,
    allowed_values: null,
    unit: null,
    required: false,
    min: null,
    max: null,
    date_format: null,
    aliases: [],
    ...overrides,
  };
}

function makeDraft(overrides: Partial<SchemaFieldDraft> = {}): SchemaFieldDraft {
  return {
    name: "compound_id",
    description: "",
    type: "none",
    allowedValues: [],
    unit: "",
    required: false,
    min: null,
    max: null,
    dateFormat: "",
    ...overrides,
  };
}

function makeSchema(fieldCount: number): SchemaOut {
  return {
    id: "schema-1",
    name: "assay-potency",
    created_by: null,
    fields: Array.from({ length: fieldCount }, (_, i) => makeField({ name: `field_${i}` })),
  };
}

describe("toFieldPayload", () => {
  it("serializes a minimal draft with empty strings coerced to null", () => {
    const draft = makeDraft({ name: "compound_id" });
    expect(toFieldPayload(draft)).toEqual({
      name: "compound_id",
      description: null,
      type: null,
      allowed_values: null,
      unit: null,
      required: false,
      min: null,
      max: null,
      date_format: null,
    });
  });

  it("never emits an empty allowed_values array -- null when empty", () => {
    const draft = makeDraft({ allowedValues: [] });
    expect(toFieldPayload(draft).allowed_values).toBeNull();
  });

  it("keeps a populated allowed_values list", () => {
    const draft = makeDraft({ allowedValues: ["IC50", "EC50"] });
    expect(toFieldPayload(draft).allowed_values).toEqual(["IC50", "EC50"]);
  });

  it("only serializes min/max for a numeric type", () => {
    const numeric = makeDraft({ type: "number", min: 0, max: 100 });
    expect(toFieldPayload(numeric).min).toBe(0);
    expect(toFieldPayload(numeric).max).toBe(100);

    const nonNumeric = makeDraft({ type: "text", min: 5, max: 10 });
    expect(toFieldPayload(nonNumeric).min).toBeNull();
    expect(toFieldPayload(nonNumeric).max).toBeNull();
  });

  it("only serializes date_format for a date type, empty string becomes null", () => {
    const date = makeDraft({ type: "date", dateFormat: "%Y-%m-%d" });
    expect(toFieldPayload(date).date_format).toBe("%Y-%m-%d");

    const dateNoFormat = makeDraft({ type: "date", dateFormat: "" });
    expect(toFieldPayload(dateNoFormat).date_format).toBeNull();

    const nonDate = makeDraft({ type: "text", dateFormat: "%Y-%m-%d" });
    expect(toFieldPayload(nonDate).date_format).toBeNull();
  });

  it("maps the 'none' type sentinel to null", () => {
    expect(toFieldPayload(makeDraft({ type: "none" })).type).toBeNull();
  });
});

describe("fromCanonicalField", () => {
  it("seeds a draft from a CanonicalFieldPayload, defaulting nulls to empty strings/arrays", () => {
    const field = makeField({ name: "assay_type", description: null, type: null, unit: null, allowed_values: null });
    expect(fromCanonicalField(field)).toEqual({
      name: "assay_type",
      description: "",
      type: "none",
      allowedValues: [],
      unit: "",
      required: false,
      min: null,
      max: null,
      dateFormat: "",
    });
  });

  it("carries populated constraints through untouched", () => {
    const field = makeField({
      name: "value",
      description: "the measured value",
      type: "number",
      unit: "nM",
      required: true,
      min: 0,
      max: 1000,
      allowed_values: null,
    });
    expect(fromCanonicalField(field)).toEqual({
      name: "value",
      description: "the measured value",
      type: "number",
      allowedValues: [],
      unit: "nM",
      required: true,
      min: 0,
      max: 1000,
      dateFormat: "",
    });
  });
});

describe("round-trip", () => {
  it("toFieldPayload(fromCanonicalField(f)) equals f minus its aliases", () => {
    const field = makeField({
      name: "assay_date",
      description: "when the assay ran",
      type: "date",
      unit: null,
      required: true,
      date_format: "%Y-%m-%d",
      aliases: [
        {
          vendor: "acme",
          source_column: "Date",
          provenance_kind: "manual",
          provenance_actor: "curator@example.com",
          created_at: "2026-07-12T00:00:00Z",
        },
      ],
    });
    const { aliases: _aliases, ...expected } = field;
    expect(toFieldPayload(fromCanonicalField(field))).toEqual(expected);
  });
});

describe("fieldSummaryLine", () => {
  it("shows type, unit, required, and alias count when all are present", () => {
    const field = makeField({ type: "number", unit: "nM", required: true, aliases: [{ vendor: "acme", source_column: "x", provenance_kind: "manual", provenance_actor: "a", created_at: "" }] });
    expect(fieldSummaryLine(field)).toBe("number · nM · required · 1 alias");
  });

  it("omits absent type/unit cleanly rather than rendering 'null'", () => {
    const field = makeField({ type: null, unit: null, required: true, aliases: [] });
    expect(fieldSummaryLine(field)).toBe("required · 0 aliases");
  });

  it("omits 'required' entirely for an optional field", () => {
    const field = makeField({ type: null, unit: null, required: false, aliases: [] });
    expect(fieldSummaryLine(field)).toBe("0 aliases");
  });

  it("pluralizes the alias count for N > 1", () => {
    const field = makeField({
      required: false,
      aliases: [
        { vendor: "a", source_column: "x", provenance_kind: "manual", provenance_actor: "a", created_at: "" },
        { vendor: "b", source_column: "y", provenance_kind: "manual", provenance_actor: "b", created_at: "" },
      ],
    });
    expect(fieldSummaryLine(field)).toBe("2 aliases");
  });
});

describe("canAddField", () => {
  it("is true below the field cap", () => {
    expect(canAddField(makeSchema(3))).toBe(true);
  });

  it("is false exactly at MAX_FIELDS", () => {
    expect(canAddField(makeSchema(MAX_FIELDS))).toBe(false);
  });

  it("is false above MAX_FIELDS", () => {
    expect(canAddField(makeSchema(MAX_FIELDS + 1))).toBe(false);
  });
});

describe("deleteFieldWarning", () => {
  it("pluralizes correctly for 0 aliases", () => {
    const field = makeField({ name: "compound_id", aliases: [] });
    expect(deleteFieldWarning(field)).toBe(
      "This removes 'compound_id' and its 0 vendor aliases from the Schema. Files already mapped with it are unaffected. This can't be undone."
    );
  });

  it("pluralizes correctly for exactly 1 alias", () => {
    const field = makeField({
      name: "compound_id",
      aliases: [{ vendor: "acme", source_column: "Cmpd ID", provenance_kind: "manual", provenance_actor: "a", created_at: "" }],
    });
    expect(deleteFieldWarning(field)).toBe(
      "This removes 'compound_id' and its 1 vendor alias from the Schema. Files already mapped with it are unaffected. This can't be undone."
    );
  });

  it("pluralizes correctly for N > 1 aliases", () => {
    const field = makeField({
      name: "compound_id",
      aliases: [
        { vendor: "acme", source_column: "Cmpd ID", provenance_kind: "manual", provenance_actor: "a", created_at: "" },
        { vendor: "nova", source_column: "Compound", provenance_kind: "manual", provenance_actor: "b", created_at: "" },
      ],
    });
    expect(deleteFieldWarning(field)).toBe(
      "This removes 'compound_id' and its 2 vendor aliases from the Schema. Files already mapped with it are unaffected. This can't be undone."
    );
  });
});
