/**
 * Pure path <-> tab translation for the five-tab shell (App.tsx's `TABS`).
 *
 * These functions are deliberately `window`-free: `frontend/vite.config.ts`
 * runs vitest in `environment: 'node'` (no DOM), so a function that read
 * `window.location.pathname` internally could never be unit-tested here.
 * Instead the path is always a plain `string` argument, and the thin
 * `window` wiring (reading/writing `history`, subscribing to `popstate`)
 * lives in App.tsx as the untested seam.
 *
 * `tabs[0]` is the default by convention, matching App.tsx's own TABS
 * ordering. The default tab is canonical at `/` -- there is exactly one URL
 * per screen (it is never also reachable at `/<its-own-slug>` from in-app
 * navigation; see `pathForTab`).
 */

/** Strips the parts of a path that are cosmetic, not semantic: a leading
 * and trailing '/' (a stray "/review/" should route like "review", not
 * 404), and casing (hand-typed paths vary; the real slugs are all
 * lowercase). */
function _normalizePath(pathname: string): string {
  return pathname.trim().replace(/^\/+/, "").replace(/\/+$/, "").toLowerCase();
}

/**
 * Resolves a raw `location.pathname` value to one of `tabs`, defaulting to
 * `tabs[0]` for anything unrecognized -- the root path "/" included, since
 * it normalizes to the empty string, which is never a member of `tabs`.
 *
 * The allowlist check is the whole safety story: a path that isn't a member
 * of `tabs` can only ever resolve to `tabs[0]`, so no attacker- or
 * user-controlled path can ever select a screen that doesn't exist (there
 * is no rendering, markup, or request-URL use of the raw path).
 */
export function tabFromPath(pathname: string, tabs: readonly string[]): string {
  const normalized = _normalizePath(pathname);
  return tabs.includes(normalized) ? normalized : tabs[0];
}

/**
 * The inverse of `tabFromPath`. Takes the `tabs` list too (symmetric with
 * `tabFromPath`) precisely so the canonical-root rule lives HERE, inside
 * this pure, unit-tested module, rather than as an `if` in App.tsx: the
 * default tab maps to "/", every other tab to `/<tab>`.
 */
export function pathForTab(tab: string, tabs: readonly string[]): string {
  return tab === tabs[0] ? "/" : `/${tab}`;
}
