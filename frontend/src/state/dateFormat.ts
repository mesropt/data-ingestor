/**
 * The date-order question's pure preview/validation/payload/escalation
 * logic (D-10-07, INGEST-02) -- a module with NO React import, so vitest
 * covers it under the `node` test environment (`vite.config.ts`'s
 * `test.environment: 'node'`), mirroring `state/upload.ts`/`state/reconcile.ts`'s
 * own "logic is tested, rendering is gsd-ui-checker-validated" split.
 *
 * Two invariants this module enforces structurally:
 * - `previewFor` never guesses silently (principle 2): an evidence value it
 *   cannot confidently interpret under a candidate order returns `null`,
 *   and the panel omits the preview line rather than showing garbage.
 * - `toResolvePayload` carries NO format-string field at all (T-10-31) --
 *   only an `order` per column ever leaves the client; the server derives
 *   the concrete strptime format itself from its own re-classification.
 */

import type { DateFormatChoice, DateFormatColumn, DateFormatOrder, Escalation } from "../lib/types";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** Splits a `DD/MM/YYYY`-shaped (or `-`/`.`-delimited) evidence value into
 * its three numeric parts, in the order they appear on the wire -- `null`
 * if the value isn't shaped like a 3-part date at all. */
function parseParts(value: string): [number, number, number] | null {
  const match = value.trim().match(/^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$/);
  if (!match) return null;
  const [, first, second, third] = match;
  return [Number(first), Number(second), Number(third)];
}

/** Renders the concrete preview one evidence value would resolve to under a
 * candidate order -- `"03/04/2025"` + `day_first` -> `"3 April 2025"`;
 * + `month_first` -> `"March 4, 2025"`. A value that isn't shaped like a
 * date, or whose day/month falls outside a valid range under the chosen
 * order (e.g. reading "13" as a month), returns `null` -- the panel then
 * omits the preview line entirely rather than showing a garbage date. */
export function previewFor(exampleValue: string, order: DateFormatOrder): string | null {
  const parts = parseParts(exampleValue);
  if (!parts) return null;
  const [first, second, year] = parts;
  const day = order === "day_first" ? first : second;
  const month = order === "day_first" ? second : first;
  if (month < 1 || month > 12 || day < 1 || day > 31 || year < 1) return null;
  const monthName = MONTH_NAMES[month - 1];
  return order === "day_first" ? `${day} ${monthName} ${year}` : `${monthName} ${day}, ${year}`;
}

/** `false` until EVERY ambiguous column has an order -- the submit button's
 * disabled state mirrors the server's own fail-closed 422
 * (`resolve_date_formats` / `UnresolvedDateColumnsError`, T-10-34); it never
 * relies on the server alone to catch a partial answer. */
export function allColumnsAnswered(
  columns: DateFormatColumn[],
  answers: Record<string, DateFormatOrder>
): boolean {
  return columns.every((column) => answers[column.target_field] !== undefined);
}

/** The full `POST /api/date-format/resolve` request body -- mirrors
 * `api/wire.py::DateFormatResolveRequest`. */
export interface DateFormatResolvePayload {
  upload_token: string;
  choices: DateFormatChoice[];
}

/** Builds exactly `{upload_token, choices: [{target_field, order}]}` -- no
 * format-string key at all (T-10-31): the client structurally cannot send
 * a strptime format, only the human's chosen ORDER per column. */
export function toResolvePayload(
  uploadToken: string,
  answers: Record<string, DateFormatOrder>
): DateFormatResolvePayload {
  return {
    upload_token: uploadToken,
    choices: Object.entries(answers).map(([target_field, order]) => ({ target_field, order })),
  };
}

/** The escalation-summary line (UI-SPEC Copywriting Contract) -- the one
 * visible proof of INGEST-02's Python-before-Claude mapping order. The
 * `{claude}` clause is OMITTED ENTIRELY when zero Claude calls were made --
 * the omission is the whole point of the line, not an edge case to gloss
 * over (Review's escalation summary; also this module's home per the
 * plan's own artifact list). */
export function escalationLine({ python, claude, total }: Escalation): string {
  const base = `${python} of ${total} field(s) matched from the Schema's crosswalk`;
  return claude === 0 ? `${base} — 0 Claude calls.` : `${base}. ${claude} required Claude.`;
}
