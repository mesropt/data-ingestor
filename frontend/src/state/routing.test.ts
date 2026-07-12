import { describe, expect, it } from "vitest";

import { hashForTab, tabFromHash } from "./routing";

// This mirrors App.tsx's real TABS values, but is local test DATA only --
// production code always receives the live list as an argument (App.tsx's
// TABS), so this is not a second source of truth, just representative input.
const TAB_SLUGS = ["define-fields", "upload", "review", "registry", "docs"];

describe("tabFromHash", () => {
  it("resolves a well-formed hash to its slug", () => {
    expect(tabFromHash("#upload", TAB_SLUGS)).toBe("upload");
  });

  it("accepts a slug with no leading '#' (a caller may pass either form)", () => {
    expect(tabFromHash("upload", TAB_SLUGS)).toBe("upload");
  });

  it("preserves a hyphenated slug", () => {
    expect(tabFromHash("#define-fields", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the first tab for an unrecognized hash", () => {
    expect(tabFromHash("#nonsense", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the first tab for a bare '#'", () => {
    expect(tabFromHash("#", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the first tab for an empty string", () => {
    expect(tabFromHash("", TAB_SLUGS)).toBe("define-fields");
  });

  it("tolerates a stray leading slash instead of treating it as a 404", () => {
    expect(tabFromHash("#/review", TAB_SLUGS)).toBe("review");
  });

  it("normalizes case, since hand-typed hashes vary but real slugs are lowercase", () => {
    expect(tabFromHash("#UPLOAD", TAB_SLUGS)).toBe("upload");
  });

  it("falls back to the first tab for percent-encoded junk that fails the allowlist", () => {
    expect(tabFromHash("#%20upload", TAB_SLUGS)).toBe("define-fields");
  });

  it("guard property: the result is always a member of the supplied tabs list", () => {
    const inputs = [
      "#upload",
      "upload",
      "#define-fields",
      "#nonsense",
      "#",
      "",
      "#/review",
      "#UPLOAD",
      "#%20upload",
    ];
    for (const input of inputs) {
      expect(TAB_SLUGS).toContain(tabFromHash(input, TAB_SLUGS));
    }
  });
});

describe("hashForTab", () => {
  it("prefixes a tab value with '#'", () => {
    expect(hashForTab("review")).toBe("#review");
  });
});

describe("round-trip", () => {
  it("recovers every slug via tabFromHash(hashForTab(slug), slugs)", () => {
    for (const slug of TAB_SLUGS) {
      expect(tabFromHash(hashForTab(slug), TAB_SLUGS)).toBe(slug);
    }
  });
});
