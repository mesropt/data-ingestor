import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/**
 * The in-app Documentation screen (DOCS-01, D-09-04) -- a pure static content
 * page: a how-to walking the CURRENT end-to-end flow (post Phase 10: the
 * three-control Upload, the Python -> Claude -> human escalation, the date
 * fail-closed rule, headers-only as a first-class privacy mode, inferred
 * values in the manifest) and a glossary of the four locked
 * governed-vocabulary terms, so a curator learns the terms without leaving
 * the app.
 *
 * Every claim on this page is verified against the code it describes (quick
 * 260712): the Upload controls against `Upload.tsx`, the escalation order
 * against `service._prefill_coverage`/`Escalation`, the confirm gate against
 * `service.confirm`, dates against `parsing/structure/date_order.py` +
 * `canonical.py`, headers-only against `mapping/mapper._render_table`,
 * inferred values against `canonical.value_source` +
 * `export/writers.build_manifest`, and the learning loop against
 * `service._record_aliases`/`save_profile_if_ready`. Do not edit the copy
 * without re-verifying the claim.
 *
 * All copy is developer-authored literal JSX text rendered escape-by-default;
 * no backend calls, no markdown dependency, no raw-HTML injection (T-09-04).
 * Organization is explicitly marked future so a curator is not misled into
 * looking for org features (T-09-05). The page stays open signed-out
 * (10-UI-SPEC Discretion 3) -- a prospective user may read what the tool
 * does before creating an account.
 */
export function Documentation() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-display">Documentation</h1>
        <p className="text-body text-muted-foreground">
          How the end-to-end flow works, and the vocabulary the app is governed by.
        </p>
      </header>

      <HowToCard />
      <BehavioursCard />
      <ManifestCard />
      <GlossaryCard />
    </div>
  );
}

/** Section 1 -- the end-to-end flow as a short ordered walkthrough, matching
 * what the Upload / Review / Schemas screens actually do today. */
function HowToCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">How it works</CardTitle>
        <CardDescription>
          From a messy vendor file to a governed, auditable export — in one pass.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-body text-muted-foreground marker:text-foreground">
          <li>
            <span className="text-label-strong text-foreground">Create or choose a Schema</span> — on the
            Schemas page: the canonical fields your files must resolve to, and every vendor's recorded alias
            for each. Both are editable there.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Upload a CSV or Excel file</span> — the Upload
            screen asks for exactly three things: the target Schema, an optional map file to seed the
            crosswalk, and the headers-only privacy toggle. Then drop the file.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Escalate only as far as needed</span> —
            deterministic Python runs first, matching the file's headers against the Schema's crosswalk
            aliases with no Claude call. Claude is asked only about the fields Python could not resolve. The
            human resolves only what Claude could not resolve confidently. The Review screen reports the
            split, so you can see how much never needed the model at all.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Review the uncertain fields</span> — anything
            unresolved is flagged amber with its reasoning. Nothing is saved until every amber field is
            cleared, and the server re-validates everything on confirm — it never trusts the client's claim
            that a field is clear.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Confirm</span> — you must be signed in and
            verified; the confirmation is attributed to you for provenance, and a required vendor label
            records whose format this file was.
          </li>
          <li>
            <span className="text-label-strong text-foreground">The tool learns</span> — confirming records
            each resolved source column as that vendor's alias on the Schema's crosswalk, with provenance
            (who confirmed it, when). The next file with the same column signature from the same source maps
            automatically — no Claude call, no amber fields to re-resolve.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Export</span> — CSV, Excel, and JSON, plus an
            audit manifest recording where every value came from. The files are named after the data they
            hold — vendor, source file, worksheet, and the table within it — so a folder of exports stays
            readable without opening any of them.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Move the crosswalk around</span> — a Schema's
            JSON export is its master map file. Download it, hand it to a teammate, or import one — imports
            only ever add fields and aliases, never overwrite or delete what a human recorded.
          </li>
        </ol>
      </CardContent>
    </Card>
  );
}

/** Section 2 -- the behaviours a curator should know about, each one a real,
 * verified property of the tool rather than a marketing line. */
function BehavioursCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">What the tool guarantees</CardTitle>
        <CardDescription>Four behaviours worth knowing before you trust it with a file.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">
            Privacy mode: headers-only <span className="text-mono-label">(--headers-only)</span>
          </p>
          <p className="text-body text-muted-foreground">
            With the headers-only toggle on, Claude sees only the file's column NAMES — never a cell value.
            The server itself still reads the whole file, so date and locale detection work exactly as they
            do without the toggle: it restricts what leaves for the LLM, not what the tool can do. Even the
            example values in a date-order question are hidden from the screen while it is on. Use it when a
            file's contents are sensitive but its column names are not.
          </p>
        </div>
        <Separator />
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">Dates are normalised — and never guessed</p>
          <p className="text-body text-muted-foreground">
            Every date column is converted to ISO 8601 in the export. An unambiguous format converts
            automatically. An ambiguous one — is 03/04/2025 the 3rd of April or March 4th? — fails closed and
            asks you once per column before anything proceeds. A date format declared on the Schema is a
            human claim, not a fact: it is checked against the column's actual values, and a contradiction
            flags the field amber instead of being silently trusted.
          </p>
        </div>
        <Separator />
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">Inferred values are labelled as inferences</p>
          <p className="text-body text-muted-foreground">
            A field with no column in the file — say a unit of nM deduced from the values' magnitude — can be
            proposed as an inferred value. It is checked against the field's declared constraints, written to
            every row of the export, and recorded in the audit manifest as{" "}
            <span className="text-mono-label">value_source: inferred</span> — so an auditor can always tell a
            value Claude deduced from a value the file contained.
          </p>
        </div>
        <Separator />
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">Learning and auto-map</p>
          <p className="text-body text-muted-foreground">
            Once you confirm a file, its column signature is remembered and each resolved column becomes a
            vendor alias on the Schema's crosswalk, with provenance. The next file with the same signature
            from that source auto-maps at full confidence, and a known vendor's headers match in plain Python
            before Claude is ever asked.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/** Section 3 -- what the manifest is FOR. Every claim here names a key
 * `export/writers.build_manifest` actually writes: `source_file`,
 * `source_sheet`, `schema_name`, `vendor`, `confirmed_by`, `exported_at`,
 * per-field `value_source` (from `canonical.value_source`),
 * `fields_absent_from_source`, `columns_not_in_schema`. Do not add a key to
 * this copy that the builder does not emit. */
function ManifestCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">What the manifest is for</CardTitle>
        <CardDescription>
          So that six months from now you can prove where a number came from — without opening the source
          file.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-body text-muted-foreground">
          The data files answer <span className="text-label-strong text-foreground">what came out</span>. The
          manifest, exported alongside them, answers{" "}
          <span className="text-label-strong text-foreground">why it came out that way, and who is answerable
          for it</span>.
        </p>
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">Where this dataset came from</p>
          <p className="text-body text-muted-foreground">
            The source file, the worksheet, and — when one worksheet held several tables — which table.
            Which Schema it was mapped against, which vendor's format it was, who confirmed it, and when.
          </p>
        </div>
        <Separator />
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">Where each individual value came from</p>
          <p className="text-body text-muted-foreground">
            Field by field: which source column it was read from (
            <span className="text-mono-label">value_source: column</span>), where the value was an inference a
            human accepted (<span className="text-mono-label">inferred</span>), and where the file had no
            column for it at all (<span className="text-mono-label">fields_absent_from_source</span>).
          </p>
        </div>
        <Separator />
        <div className="flex flex-col gap-1">
          <p className="text-label-strong">What was left behind</p>
          <p className="text-body text-muted-foreground">
            The columns your file carried that no field claimed (
            <span className="text-mono-label">columns_not_in_schema</span>) — the half of a mismatch that
            leaves no visible hole in the output, and would otherwise be dropped in silence.
          </p>
        </div>
        <Separator />
        <p className="text-body text-muted-foreground">
          Without it, an empty cell in the export is indistinguishable from data that was lost, and "trust the
          numbers" is only a slogan: a number is worth exactly as much as your ability to check where it came
          from.
        </p>
      </CardContent>
    </Card>
  );
}

/** Section 4 -- the four locked terms with their exact locked definitions
 * (REQUIREMENTS.md "Locked terminology", D-09-04). Organization carries a
 * visible future marker. */
function GlossaryCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">Glossary</CardTitle>
        <CardDescription>The four locked terms the app is governed by.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col gap-4">
          <GlossaryEntry
            term="Schema"
            definition="One canonical model per domain; its JSON export is the master map file."
          />
          <Separator />
          <GlossaryEntry term="Field" definition="A canonical field in a Schema." />
          <Separator />
          <GlossaryEntry term="Alias" definition="A vendor's name for a field, with provenance." />
          <Separator />
          <GlossaryEntry
            term="Organization"
            definition="Owner of a set of Schemas."
            marker="Future — not yet in the app"
          />
        </dl>
      </CardContent>
    </Card>
  );
}

/** One term/definition pair; an optional muted marker badge flags terms that
 * are defined but not yet implemented. */
function GlossaryEntry({
  term,
  definition,
  marker,
}: {
  term: string;
  definition: string;
  marker?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="flex items-center gap-2">
        <span className="text-label-strong">{term}</span>
        {marker && (
          <Badge variant="outline" className="text-muted-foreground">
            {marker}
          </Badge>
        )}
      </dt>
      <dd className="text-body text-muted-foreground">{definition}</dd>
    </div>
  );
}
