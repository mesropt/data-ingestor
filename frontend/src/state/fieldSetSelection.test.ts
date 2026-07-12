import { describe, expect, it } from "vitest";

import { pickDefaultTemplateId, submitBlockedReason } from "./fieldSetSelection";
import type { FieldSetTemplate } from "../lib/types";

function template(id: string, name = id): FieldSetTemplate {
  return { id, name, field_set: { name, fields: [] } };
}

describe("pickDefaultTemplateId", () => {
  it("returns lastUsedId when a template with that id is present", () => {
    const templates = [template("a"), template("b")];

    expect(pickDefaultTemplateId(templates, "b")).toBe("b");
  });

  it("returns the first template's id when lastUsedId is null", () => {
    const templates = [template("a"), template("b")];

    expect(pickDefaultTemplateId(templates, null)).toBe("a");
  });

  it("returns the first template's id when lastUsedId is stale (deleted template)", () => {
    const templates = [template("a"), template("b")];

    expect(pickDefaultTemplateId(templates, "deleted-id")).toBe("a");
  });

  it("returns null for an empty template list -- the only honest blank picker", () => {
    expect(pickDefaultTemplateId([], "anything")).toBeNull();
    expect(pickDefaultTemplateId([], null)).toBeNull();
  });
});

describe("submitBlockedReason", () => {
  it("returns a short curator-facing string when the template is null", () => {
    const reason = submitBlockedReason(null);

    expect(typeof reason).toBe("string");
    expect(reason).not.toHaveLength(0);
  });

  it("returns null when a template is selected", () => {
    expect(submitBlockedReason(template("a"))).toBeNull();
  });
});
