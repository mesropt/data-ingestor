import { describe, expect, it } from "vitest";

import type { MappingResponse } from "@/lib/types";

import { initialVendor, vendorHint } from "./vendorMemory";

function makeMapping(overrides: Partial<MappingResponse> = {}): MappingResponse {
  return {
    kind: "mapping",
    ready: true,
    source_columns: ["cmpd", "value"],
    field_mappings: [],
    provenance: "fresh-claude",
    upload_token: "token-1",
    escalation: null,
    remembered_vendor: null,
    remembered_vendor_source: null,
    vendor_candidates: [],
    ...overrides,
  };
}

describe("initialVendor", () => {
  it("returns the remembered vendor when the server resolved one", () => {
    const mapping = makeMapping({ remembered_vendor: "novascreen", remembered_vendor_source: "profile" });
    expect(initialVendor(mapping)).toBe("novascreen");
  });

  it("returns empty string when nothing was remembered", () => {
    expect(initialVendor(makeMapping())).toBe("");
  });

  it("returns empty string on an ambiguous match -- never a guess", () => {
    const mapping = makeMapping({
      remembered_vendor: null,
      vendor_candidates: ["novascreen", "zephyr"],
    });
    expect(initialVendor(mapping)).toBe("");
  });
});

describe("vendorHint", () => {
  it("explains a profile-sourced match", () => {
    const mapping = makeMapping({ remembered_vendor: "novascreen", remembered_vendor_source: "profile" });
    expect(vendorHint(mapping)).toBe(
      "Remembered from the last file with these columns — change it if this file is from a different vendor."
    );
  });

  it("explains a crosswalk-sourced match", () => {
    const mapping = makeMapping({ remembered_vendor: "novascreen", remembered_vendor_source: "crosswalk" });
    expect(vendorHint(mapping)).toBe(
      "Remembered from this Schema's crosswalk — change it if this file is from a different vendor."
    );
  });

  it("names both candidates on an ambiguous match, joined with 'and'", () => {
    const mapping = makeMapping({ vendor_candidates: ["novascreen", "zephyr"] });
    expect(vendorHint(mapping)).toBe(
      "These columns match novascreen and zephyr — we won't guess which. Pick one."
    );
  });

  it("returns null when there is nothing to explain", () => {
    expect(vendorHint(makeMapping())).toBeNull();
  });
});
