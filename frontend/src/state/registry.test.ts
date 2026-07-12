import { describe, expect, it } from "vitest";

import {
  formatProvenance,
  formatWhen,
  groupFieldRows,
  isSchemaEmpty,
} from "./registry";
import type {
  AliasPayload,
  CanonicalFieldPayload,
  MasterMapEnvelope,
} from "../lib/types";

function makeAlias(overrides: Partial<AliasPayload> = {}): AliasPayload {
  return {
    vendor: "novascreen",
    source_column: "Cmpd ID",
    provenance_kind: "manual",
    provenance_actor: "curator@example.com",
    created_at: "2026-07-11T14:32:05Z",
    ...overrides,
  };
}

function makeField(overrides: Partial<CanonicalFieldPayload> = {}): CanonicalFieldPayload {
  return {
    name: "compound_id",
    description: null,
    type: "text",
    allowed_values: null,
    unit: null,
    required: true,
    min: null,
    max: null,
    date_format: null,
    aliases: [],
    ...overrides,
  };
}

function makeEnvelope(fields: CanonicalFieldPayload[]): MasterMapEnvelope {
  return {
    schema_version: 1,
    id: "schema-1",
    name: "assay-potency",
    created_by: "curator@example.com",
    created_at: "2026-07-11T14:00:00Z",
    fields,
  };
}

describe("groupFieldRows", () => {
  it("returns one row per canonical field in the envelope's field order, never re-sorted", () => {
    const envelope = makeEnvelope([
      makeField({ name: "value" }),
      makeField({ name: "compound_id" }),
      makeField({ name: "assay_type" }),
    ]);

    const rows = groupFieldRows(envelope);

    expect(rows.map((r) => r.name)).toEqual(["value", "compound_id", "assay_type"]);
  });

  it("carries each field's quiet metadata (type, unit, allowed_values, min, max) and aliases verbatim", () => {
    const alias = makeAlias({ vendor: "acme", source_column: "MW" });
    const envelope = makeEnvelope([
      makeField({
        name: "value",
        type: "number",
        unit: "uM",
        allowed_values: ["a", "b"],
        min: 0,
        max: 100,
        aliases: [alias],
      }),
    ]);

    const [row] = groupFieldRows(envelope);

    expect(row.metadata).toEqual({ type: "number", unit: "uM", allowedValues: ["a", "b"], min: 0, max: 100 });
    expect(row.aliases).toEqual([alias]);
    expect(row.hasAliases).toBe(true);
  });

  it("flags a field with an empty aliases array as hasAliases:false and never drops it", () => {
    const envelope = makeEnvelope([makeField({ name: "target", aliases: [] })]);

    const rows = groupFieldRows(envelope);

    expect(rows).toHaveLength(1);
    expect(rows[0].hasAliases).toBe(false);
    expect(rows[0].aliases).toEqual([]);
  });
});

describe("formatProvenance", () => {
  it("maps a manual alias to label 'manual' with the actor as the user", () => {
    const prov = formatProvenance(makeAlias({ provenance_kind: "manual", provenance_actor: "curator@example.com" }));

    expect(prov.kind).toBe("manual");
    expect(prov.label).toBe("manual");
    expect(prov.actor).toBe("curator@example.com");
    expect(prov.when).toBe("2026-07-11 14:32 UTC");
  });

  it("maps a from_map_file alias to label 'from map file' with the actor as the source", () => {
    const prov = formatProvenance(
      makeAlias({ provenance_kind: "from_map_file", provenance_actor: "novascreen-2025.json" })
    );

    expect(prov.kind).toBe("from_map_file");
    expect(prov.label).toBe("from map file");
    expect(prov.actor).toBe("novascreen-2025.json");
  });

  it("falls back to the raw kind text for an unknown provenance_kind, never throwing", () => {
    const prov = formatProvenance(makeAlias({ provenance_kind: "imported_from_elsewhere" }));

    expect(prov.label).toBe("imported_from_elsewhere");
    expect(prov.kind).toBe("imported_from_elsewhere");
  });
});

describe("formatWhen", () => {
  it("humanises an ISO-8601 timestamp to a stable locale-independent UTC form", () => {
    expect(formatWhen("2026-07-11T14:32:05Z")).toBe("2026-07-11 14:32 UTC");
  });

  it("normalises a non-UTC offset to UTC deterministically", () => {
    expect(formatWhen("2026-07-11T16:32:00+02:00")).toBe("2026-07-11 14:32 UTC");
  });

  it("returns a safe fallback for an empty created_at, never throwing", () => {
    expect(formatWhen("")).toBe("unknown date");
  });

  it("returns a safe fallback for an invalid created_at, never throwing", () => {
    expect(formatWhen("not-a-date")).toBe("unknown date");
  });
});

describe("isSchemaEmpty", () => {
  it("is true when the envelope has zero canonical fields", () => {
    expect(isSchemaEmpty(makeEnvelope([]))).toBe(true);
  });

  it("is true when every field has zero aliases", () => {
    const envelope = makeEnvelope([makeField({ name: "value", aliases: [] }), makeField({ name: "unit", aliases: [] })]);

    expect(isSchemaEmpty(envelope)).toBe(true);
  });

  it("is false when at least one field carries an alias", () => {
    const envelope = makeEnvelope([
      makeField({ name: "value", aliases: [] }),
      makeField({ name: "unit", aliases: [makeAlias()] }),
    ]);

    expect(isSchemaEmpty(envelope)).toBe(false);
  });
});
