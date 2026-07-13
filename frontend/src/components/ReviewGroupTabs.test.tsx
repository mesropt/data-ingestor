// @vitest-environment jsdom
/**
 * The ONE correctness hazard the tabbed Review exists to close (T-11-37,
 * UI-SPEC Discretion §2, 11-RESEARCH Pitfall 8): `Review` holds a curator's
 * amber resolutions in LOCAL state, so a tab whose pane unmounts on switch
 * SILENTLY DESTROYS THEIR WORK. Every pane is therefore kept mounted while
 * hidden, and each member's Review is keyed by its own upload token.
 *
 * That is a claim about React's MOUNT LIFECYCLE, which no pure function can
 * pin -- so this one file renders for real (jsdom) and drives the actual
 * hazard: resolve an amber field on Week 1, switch to Week 2, switch back,
 * and assert the resolution is still there. Every OTHER derivation in this
 * component (member status, the group gate, the pane key, N=1) is a pure
 * function tested under `environment: 'node'` in `state/review.test.ts`;
 * this file deliberately covers only what a DOM is genuinely required for.
 */

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExportBar } from "./ExportBar";
import { ReviewGroupTabs } from "./ReviewGroupTabs";
import type { FieldMappingOut, MappingResponse, SheetGroupResponse } from "@/lib/types";

function amberUnit(): FieldMappingOut {
  return {
    target_field: "unit",
    source_column: null,
    confidence: 0.41,
    reasoning: "no column clearly carries the unit",
    needs_confirmation: true,
    inferred_value: "nM",
    alternatives: [{ source_column: "Units", confidence: 0.62 }],
    validator_note: null,
  };
}

function clearCompound(): FieldMappingOut {
  return {
    target_field: "compound_id",
    source_column: "Compound ID",
    confidence: 0.98,
    reasoning: "header matches compound_id",
    needs_confirmation: false,
    inferred_value: null,
    alternatives: [],
    validator_note: null,
  };
}

function memberMapping(token: string): MappingResponse {
  return {
    kind: "mapping",
    ready: false,
    source_columns: ["Compound ID", "Units"],
    field_mappings: [clearCompound(), amberUnit()],
    provenance: "fresh-claude",
    upload_token: token,
    escalation: null,
    remembered_vendor: null,
    remembered_vendor_source: null,
    vendor_candidates: [],
    source_name: "zephyr_bio_ZB-2025.xlsx",
  };
}

const GROUP: SheetGroupResponse = {
  kind: "sheet_group",
  group_id: "4c7c2868-e3c6-4297-a22b-40ba22190a3d",
  source_name: "zephyr_bio_ZB-2025.xlsx",
  members: [
    { sheet_name: "Week 1", schema_name: "assay-potency", response: memberMapping("token-w1") },
    { sheet_name: "Week 2", schema_name: "assay-potency", response: memberMapping("token-w2") },
    { sheet_name: "Week 3", schema_name: "assay-potency", response: memberMapping("token-w3") },
  ],
};

const SINGLE_MEMBER_GROUP: SheetGroupResponse = {
  ...GROUP,
  members: [{ sheet_name: "Sheet1", schema_name: "assay-potency", response: memberMapping("token-only") }],
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  // Review fetches the governed Schema list once on mount (only to build
  // /api/confirm's field_set body) -- stubbed so these renders make no real
  // network call. The confirm gate itself is never driven here.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }))
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

function render(group: SheetGroupResponse) {
  act(() => {
    root.render(
      <ReviewGroupTabs
        group={group}
        schemasBySheet={Object.fromEntries(group.members.map((m) => [m.sheet_name, "assay-potency"]))}
        headersOnly={false}
        vendor="novascreen"
        signedIn
        verified
        onRequireSignIn={() => {}}
      />
    );
  });
}

/** A tab trigger by its sheet name. */
function tab(name: string): HTMLElement {
  const found = Array.from(container.querySelectorAll('[data-slot="tabs-trigger"]')).find((el) =>
    el.textContent?.includes(name)
  );
  if (!found) throw new Error(`no tab trigger for '${name}'`);
  return found as HTMLElement;
}

/** One member's pane (kept in the DOM even while hidden -- that IS the
 * contract under test, so this must never filter on visibility). */
function pane(index: number): HTMLElement {
  const panes = container.querySelectorAll('[data-slot="tabs-content"]');
  const found = panes[index];
  if (!found) throw new Error(`no pane at index ${index} (found ${panes.length})`);
  return found as HTMLElement;
}

function click(el: HTMLElement) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

/** The "Accept" control of the amber `unit` row inside one member's pane
 * (D-02b: keeps Claude's proposal as-is and clears amber for that field). */
function acceptButton(memberPane: HTMLElement): HTMLElement {
  const found = Array.from(memberPane.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "Accept"
  );
  if (!found) throw new Error("no Accept control in this member's pane");
  return found;
}

/** How many fields this member's pane still reports as unresolved -- read
 * from its OWN ConfirmGate progress line ("{clear} of {total} resolved"),
 * the same number the curator sees. */
function resolvedLine(memberPane: HTMLElement): string {
  const text = memberPane.textContent ?? "";
  const match = text.match(/\d+ of \d+ (?:fields )?resolved/i);
  return match ? match[0] : text;
}

describe("ReviewGroupTabs — a tab switch must never destroy a curator's work (T-11-37)", () => {
  it("keeps an amber resolution made on Week 1 after switching to Week 2 and back", () => {
    render(GROUP);

    // Week 1 starts with one amber field (unit) of two.
    expect(resolvedLine(pane(0))).toMatch(/1 of 2/);

    // Resolve it on Week 1 (D-02b Accept).
    click(acceptButton(pane(0)));
    expect(resolvedLine(pane(0))).toMatch(/2 of 2/);

    // Switch to Week 2, then back to Week 1.
    click(tab("Week 2"));
    click(tab("Week 1"));

    // THE ASSERTION THIS COMPONENT EXISTS FOR: the resolution survived.
    // If the pane had remounted, Review's local `mappings` state would be
    // re-seeded from the wire response and this would read "1 of 2" again.
    expect(resolvedLine(pane(0))).toMatch(/2 of 2/);
  });

  it("keeps every member's pane mounted while inactive (the structural reason the resolution survives)", () => {
    render(GROUP);
    // All three panes are in the DOM from the first render -- the inactive
    // two are hidden, never unmounted.
    expect(container.querySelectorAll('[data-slot="tabs-content"]')).toHaveLength(3);
    expect(pane(1).hasAttribute("hidden")).toBe(true);

    click(tab("Week 2"));

    expect(container.querySelectorAll('[data-slot="tabs-content"]')).toHaveLength(3);
    expect(pane(1).hasAttribute("hidden")).toBe(false);
    // Week 1's pane is now hidden but STILL MOUNTED -- it still renders its
    // own Review content, which is where its resolutions live.
    expect(pane(0).hasAttribute("hidden")).toBe(true);
    expect(pane(0).textContent).toMatch(/Review Mapping/);
  });

  it("resolving one member never resolves another (the gate is per dataset, never aggregated)", () => {
    render(GROUP);
    click(acceptButton(pane(0)));

    expect(resolvedLine(pane(0))).toMatch(/2 of 2/);
    expect(resolvedLine(pane(1))).toMatch(/1 of 2/);
    expect(resolvedLine(pane(2))).toMatch(/1 of 2/);
  });
});

describe("ReviewGroupTabs — the group export bar is a lookup over per-member gates, never a bypass", () => {
  it("blocks Download All while no member is confirmed, naming how many datasets must be confirmed", () => {
    render(GROUP);
    const download = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Download All")
    );
    expect(download).toBeDefined();
    expect(download?.disabled).toBe(true);
    expect(container.textContent).toContain("Confirm all 3 datasets to download the archive.");
    // While blocked it is a disabled Button, never an <a href> to the archive.
    expect(container.querySelector('a[href*="/api/export/group/"]')).toBeNull();
  });

  it("blocks Download All even after a member's amber field is resolved — resolved is not confirmed", () => {
    render(GROUP);
    click(acceptButton(pane(0)));

    const download = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Download All")
    );
    expect(download?.disabled).toBe(true);
    expect(container.querySelector('a[href*="/api/export/group/"]')).toBeNull();
  });
});

describe("ReviewGroupTabs — N=1 (SHEET-01's no-regression clause)", () => {
  it("renders a single-member group with no tab strip and no group bar", () => {
    render(SINGLE_MEMBER_GROUP);

    expect(container.querySelector('[data-slot="tabs-list"]')).toBeNull();
    expect(container.textContent).not.toContain("Download All");
    // ...but the Review itself is there, with its D-11-15 provenance line.
    expect(container.textContent).toMatch(/Review Mapping/);
    expect(container.textContent).toContain("sheet Sheet1");
  });
});

describe("provenance is visible on every ingest (D-11-15)", () => {
  it("shows each member's own source sheet in its own tab", () => {
    render(GROUP);
    expect(pane(0).textContent).toContain("sheet Week 1");
    expect(pane(1).textContent).toContain("sheet Week 2");
    expect(pane(2).textContent).toContain("sheet Week 3");
  });

  it("ExportBar tells the curator the export carries the reserved __source_sheet column", () => {
    act(() => {
      root.render(<ExportBar exportUrls={{ csv_url: "/api/export/run-1/csv" }} />);
    });
    expect(container.textContent).toContain(
      "Exports include a reserved __source_sheet column recording each row's source sheet."
    );
  });
});
