import { describe, expect, it } from "vitest";

import {
  initialSchemaState,
  schemaReducer,
  selectedSchema,
} from "./schema";
import type { SchemaSummary } from "../lib/types";

function makeSchema(overrides: Partial<SchemaSummary> = {}): SchemaSummary {
  return {
    id: "schema-1",
    name: "assay-potency",
    created_by: "curator@example.com",
    ...overrides,
  };
}

describe("schemaReducer LOADED", () => {
  it("loads the schema list, leaving selection null when nothing was selected", () => {
    const schemas = [makeSchema({ name: "assay-potency" }), makeSchema({ id: "schema-2", name: "reagent-inventory" })];

    const state = schemaReducer(initialSchemaState, { type: "LOADED", schemas });

    expect(state.schemas).toEqual(schemas);
    expect(state.selected).toBeNull();
  });

  it("keeps a still-present selection across a reload", () => {
    const loaded = schemaReducer(initialSchemaState, {
      type: "LOADED",
      schemas: [makeSchema({ name: "assay-potency" })],
    });
    const selected = schemaReducer(loaded, { type: "SELECT", name: "assay-potency" });

    const reloaded = schemaReducer(selected, {
      type: "LOADED",
      schemas: [makeSchema({ name: "assay-potency" }), makeSchema({ id: "schema-2", name: "reagent-inventory" })],
    });

    expect(reloaded.selected).toBe("assay-potency");
  });

  it("drops a selection that no longer exists after a reload", () => {
    const selected = schemaReducer(
      { schemas: [makeSchema({ name: "assay-potency" })], selected: "assay-potency" },
      { type: "LOADED", schemas: [makeSchema({ id: "schema-2", name: "reagent-inventory" })] }
    );

    expect(selected.selected).toBeNull();
  });
});

describe("schemaReducer SELECT", () => {
  it("selects a schema by name", () => {
    const loaded = schemaReducer(initialSchemaState, {
      type: "LOADED",
      schemas: [makeSchema({ name: "assay-potency" })],
    });

    const state = schemaReducer(loaded, { type: "SELECT", name: "assay-potency" });

    expect(state.selected).toBe("assay-potency");
  });
});

describe("schemaReducer CLEAR", () => {
  it("clears the current selection without dropping the loaded list", () => {
    const loaded = schemaReducer(initialSchemaState, {
      type: "LOADED",
      schemas: [makeSchema({ name: "assay-potency" })],
    });
    const selected = schemaReducer(loaded, { type: "SELECT", name: "assay-potency" });

    const cleared = schemaReducer(selected, { type: "CLEAR" });

    expect(cleared.selected).toBeNull();
    expect(cleared.schemas).toEqual(selected.schemas);
  });
});

describe("schemaReducer RENAMED", () => {
  it("renames the schema in the list and follows the selection to the new name", () => {
    const state = {
      schemas: [makeSchema({ name: "assay-potency" }), makeSchema({ id: "schema-2", name: "reagent-inventory" })],
      selected: "assay-potency",
    };

    const renamed = schemaReducer(state, { type: "RENAMED", from: "assay-potency", to: "potency-v2" });

    expect(renamed.schemas.map((s) => s.name)).toEqual(["potency-v2", "reagent-inventory"]);
    expect(renamed.selected).toBe("potency-v2");
  });

  it("keeps id and created_by untouched — only the label moves", () => {
    const state = { schemas: [makeSchema({ name: "assay-potency" })], selected: null };

    const renamed = schemaReducer(state, { type: "RENAMED", from: "assay-potency", to: "potency-v2" });

    expect(renamed.schemas[0]).toEqual(makeSchema({ name: "potency-v2" }));
  });

  it("leaves an unrelated selection alone", () => {
    const state = {
      schemas: [makeSchema({ name: "assay-potency" }), makeSchema({ id: "schema-2", name: "reagent-inventory" })],
      selected: "reagent-inventory",
    };

    const renamed = schemaReducer(state, { type: "RENAMED", from: "assay-potency", to: "potency-v2" });

    expect(renamed.selected).toBe("reagent-inventory");
  });
});

describe("selectedSchema", () => {
  it("returns the full summary for the selected name", () => {
    const state = {
      schemas: [makeSchema({ name: "assay-potency" }), makeSchema({ id: "schema-2", name: "reagent-inventory" })],
      selected: "reagent-inventory",
    };

    expect(selectedSchema(state)?.name).toBe("reagent-inventory");
  });

  it("returns null when nothing is selected", () => {
    const state = { schemas: [makeSchema()], selected: null };

    expect(selectedSchema(state)).toBeNull();
  });
});
