import { describe, expect, it } from "vitest";

import { pathForTab, tabFromPath } from "./routing";

// This mirrors App.tsx's real TABS values, but is local test DATA only --
// production code always receives the live list as an argument (App.tsx's
// TABS), so this is not a second source of truth, just representative input.
const TAB_SLUGS = ["define-fields", "upload", "review", "registry", "docs"];

describe("tabFromPath", () => {
  it("resolves the root path to the default (first) tab", () => {
    expect(tabFromPath("/", TAB_SLUGS)).toBe("define-fields");
  });

  it("resolves an empty string to the default tab", () => {
    expect(tabFromPath("", TAB_SLUGS)).toBe("define-fields");
  });

  it("resolves a well-formed path to its slug", () => {
    expect(tabFromPath("/upload", TAB_SLUGS)).toBe("upload");
  });

  it("accepts a slug with no leading '/' (a caller may pass either form)", () => {
    expect(tabFromPath("upload", TAB_SLUGS)).toBe("upload");
  });

  it("tolerates a cosmetic trailing slash, not a 404", () => {
    expect(tabFromPath("/upload/", TAB_SLUGS)).toBe("upload");
  });

  it("preserves a hyphenated slug", () => {
    expect(tabFromPath("/define-fields", TAB_SLUGS)).toBe("define-fields");
  });

  it("normalizes case, since hand-typed paths vary but real slugs are lowercase", () => {
    expect(tabFromPath("/UPLOAD", TAB_SLUGS)).toBe("upload");
  });

  it("resolves /docs -- the path Task 1 freed from Swagger", () => {
    expect(tabFromPath("/docs", TAB_SLUGS)).toBe("docs");
  });

  it("falls back to the default tab for an unrecognized path", () => {
    expect(tabFromPath("/nonsense", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the default tab for a nested path (not a slug)", () => {
    expect(tabFromPath("/upload/extra", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the default tab for percent-encoded junk that fails the allowlist", () => {
    expect(tabFromPath("/%20upload", TAB_SLUGS)).toBe("define-fields");
  });

  it("falls back to the default tab for /verify -- not a tab (App.tsx checks pathname before the tab shell renders, D-2)", () => {
    expect(tabFromPath("/verify", TAB_SLUGS)).toBe("define-fields");
  });

  it("guard property: the result is always a member of the supplied tabs list", () => {
    const inputs = [
      "/",
      "",
      "/upload",
      "upload",
      "/upload/",
      "/define-fields",
      "/UPLOAD",
      "/docs",
      "/nonsense",
      "/upload/extra",
      "/%20upload",
      "/verify",
    ];
    for (const input of inputs) {
      expect(TAB_SLUGS).toContain(tabFromPath(input, TAB_SLUGS));
    }
  });
});

describe("pathForTab", () => {
  it("maps the default (first) tab to the canonical root, not its own slug (D-3)", () => {
    expect(pathForTab(TAB_SLUGS[0], TAB_SLUGS)).toBe("/");
  });

  it("maps a non-default tab to /<slug>", () => {
    expect(pathForTab("review", TAB_SLUGS)).toBe("/review");
  });

  it("maps the freed /docs tab to /docs", () => {
    expect(pathForTab("docs", TAB_SLUGS)).toBe("/docs");
  });
});

describe("round-trip", () => {
  it("recovers every slug via tabFromPath(pathForTab(slug, slugs), slugs), including the default's root round trip", () => {
    for (const slug of TAB_SLUGS) {
      expect(tabFromPath(pathForTab(slug, TAB_SLUGS), TAB_SLUGS)).toBe(slug);
    }
  });
});
