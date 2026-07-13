import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Permanent gate against the D-10-02 copy regression (INGEST-01): "field
 * set"/"field sets" must never survive as USER-VISIBLE text anywhere under
 * `frontend/src/screens/` or `frontend/src/components/`. The Schema IS the
 * target fields now -- there is no user-facing "field set" concept.
 *
 * The regex requires a space-or-hyphen separator, which is what makes this
 * gate safe: internal identifiers (`FieldSet`, `fieldSet`, `field_set`,
 * `FieldSetPayload`) are camelCase/snake_case and carry NO separator, so
 * they structurally cannot match. Renaming those identifiers is explicitly
 * forbidden by D-10-02 -- this test must never create pressure to do it.
 *
 * Comment lines are stripped before scanning: what a developer reasons about
 * internally (in a `//` or `*`-continuation comment) is legitimate; only
 * what a user can READ in the rendered UI is in scope.
 */

const SCANNED_DIRS = ["screens", "components"];
const LEAK_PATTERN = /field[ -]sets?/i;

function walk(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(full));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

function isCommentLine(line: string): boolean {
  const trimmed = line.trimStart();
  return trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*");
}

function findLeaks(): string[] {
  const srcDir = path.resolve(__dirname, "..");
  const hits: string[] = [];
  for (const dirName of SCANNED_DIRS) {
    const dir = path.join(srcDir, dirName);
    if (!fs.existsSync(dir)) continue;
    for (const file of walk(dir)) {
      const rel = path.relative(srcDir, file);
      const lines = fs.readFileSync(file, "utf-8").split("\n");
      lines.forEach((line, idx) => {
        if (isCommentLine(line)) return;
        if (LEAK_PATTERN.test(line)) {
          hits.push(`${rel}:${idx + 1}: ${line.trim()}`);
        }
      });
    }
  }
  return hits;
}

describe("no user-visible 'field set' copy (D-10-02)", () => {
  it("has zero matches across screens/ and components/", () => {
    const hits = findLeaks();
    expect(hits, `Found user-visible "field set" copy:\n${hits.join("\n")}`).toEqual([]);
  });
});
