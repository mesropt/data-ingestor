/**
 * Pure hash <-> tab translation for the five-tab shell (App.tsx's `TABS`).
 *
 * These functions are deliberately `window`-free: `frontend/vite.config.ts`
 * runs vitest in `environment: 'node'` (no DOM), so a function that read
 * `window.location.hash` internally could never be unit-tested here. Instead
 * the hash is always a plain `string` argument, and the thin `window` wiring
 * (reading/writing `location.hash`, subscribing to `hashchange`) lives in
 * App.tsx as the untested seam.
 */

/** Strips the parts of a hash that are cosmetic, not semantic: a leading
 * '#' (how the browser reports `location.hash`), an accidental leading '/'
 * (a stray "#/review" should route like "#review", not 404), and casing
 * (hand-typed hashes vary; the real slugs are all lowercase). */
function _normalizeHash(hash: string): string {
  return hash.trim().replace(/^#/, "").replace(/^\//, "").toLowerCase();
}

/**
 * Resolves a raw `location.hash` value to one of `tabs`, defaulting to
 * `tabs[0]` for anything unrecognized -- by convention the same default
 * App.tsx's `useState(TABS[0].value)` already used before routing existed.
 *
 * The allowlist check is the whole safety story: a hash that isn't a member
 * of `tabs` can only ever resolve to `tabs[0]`, so no attacker- or
 * user-controlled hash value can ever select a screen that doesn't exist
 * (there is no rendering, markup, or request-URL use of the raw hash).
 */
export function tabFromHash(hash: string, tabs: readonly string[]): string {
  const normalized = _normalizeHash(hash);
  return tabs.includes(normalized) ? normalized : tabs[0];
}

/** The trivial inverse of `tabFromHash` -- exists so callers never
 * string-concatenate a '#' by hand. */
export function hashForTab(tab: string): string {
  return `#${tab}`;
}
