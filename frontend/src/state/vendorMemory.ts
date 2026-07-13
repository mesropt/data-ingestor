import type { MappingResponse } from "@/lib/types";

/**
 * The remembered-vendor presentation decision (10-09/INGEST-02) -- pure
 * logic, no React, mirroring `state/dateFormat.ts`'s own "logic is tested,
 * rendering is gsd-ui-checker-validated" split (the frontend suite has no
 * DOM tests, so this decision must live here to be testable at all).
 *
 * The vendor is a human assertion the tool can never read from the file
 * itself -- but once a column signature has been confirmed once, asking
 * again is friction this removes. `Review.tsx` reads both functions below
 * to pre-fill the Vendor input and explain WHY it is pre-filled (or, on a
 * genuinely ambiguous match, why it deliberately is NOT).
 */

/** The Vendor input's initial value -- `mapping.remembered_vendor` when the
 * server resolved one (unambiguous profile or crosswalk match), empty
 * string otherwise. Never the Schema's own name (the bug this task kills):
 * a blank default is honest; a fabricated one is a silent wrong guess. */
export function initialVendor(mapping: MappingResponse): string {
  return mapping.remembered_vendor ?? "";
}

/** The muted helper line beneath the Vendor input explaining WHY it is
 * pre-filled (or, on ambiguity, why it deliberately is not) -- `null` when
 * there is nothing to explain (a fresh file matching no known vendor). */
export function vendorHint(mapping: MappingResponse): string | null {
  if (mapping.remembered_vendor_source === "profile") {
    return "Remembered from the last file with these columns — change it if this file is from a different vendor.";
  }
  if (mapping.remembered_vendor_source === "crosswalk") {
    return "Remembered from this Schema's crosswalk — change it if this file is from a different vendor.";
  }
  if (mapping.vendor_candidates.length >= 2) {
    return `These columns match ${mapping.vendor_candidates.join(" and ")} — we won't guess which. Pick one.`;
  }
  return null;
}
