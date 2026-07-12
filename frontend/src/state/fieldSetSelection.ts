/**
 * Upload screen field-set selection -- pure logic (no React), so vitest
 * covers it under the `node` test environment with no DOM (quick task
 * 260712-e0e; mirrors `state/fieldSet.ts`'s "pure reducer/helper, no
 * React dependency" framing).
 *
 * Fixes the reported dead end: `Upload.tsx` used to initialise
 * `selectedTemplateId` to `null` and never default it, so a curator landed
 * on a blank required picker, clicked the enabled-looking "Upload & Map",
 * and `!selectedTemplate`'s early-return silently swallowed the click. This
 * module is what the screen now derives its default selection and the
 * button's disabled state from -- the same value the submit guard checks,
 * so the two can never disagree again.
 */

import type { FieldSetTemplate } from "../lib/types";

const STORAGE_KEY = "assayingest-last-template-id";

/**
 * The template id the Upload screen should land on: `lastUsedId` if a
 * template with that id still exists, else the first available template,
 * else `null` if the list is empty -- the one case where a blank picker is
 * honest rather than a bug.
 */
export function pickDefaultTemplateId(
  templates: FieldSetTemplate[],
  lastUsedId: string | null
): string | null {
  if (lastUsedId !== null && templates.some((t) => t.id === lastUsedId)) {
    return lastUsedId;
  }
  return templates.length > 0 ? templates[0].id : null;
}

/**
 * The reason "Upload & Map" cannot act right now, phrased as the
 * consequence the curator reads -- `null` once a field set is resolved.
 */
export function submitBlockedReason(selectedTemplate: FieldSetTemplate | null): string | null {
  if (selectedTemplate !== null) return null;
  return "Choose a field set first — Claude needs to know which fields to map onto.";
}

/** The last field-set template id the curator used, or `null` if none was
 * ever recorded (or `window` doesn't exist -- the node vitest environment).
 * Mirrors `components/ThemeToggle.tsx`'s `readStoredTheme` idiom: touch
 * `window` only inside the function, never at module scope. */
export function readLastTemplateId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

/** Persists the curator's chosen template id so the next visit to Upload
 * lands on it (via `pickDefaultTemplateId`). A no-op where `window` doesn't
 * exist. */
export function writeLastTemplateId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, id);
}
