import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

/**
 * The in-app Documentation screen (DOCS-01, D-09-04) -- a pure static content
 * page: a how-to walking the end-to-end flow and a glossary of the four locked
 * governed-vocabulary terms, so a curator learns the terms without leaving the
 * app.
 *
 * All copy is developer-authored literal JSX text rendered escape-by-default;
 * no backend calls, no markdown dependency, no raw-HTML injection (T-09-04).
 * Organization is explicitly marked future so a curator is not misled into
 * looking for org features (T-09-05). The page is always open -- no sign-in
 * gate (D-09-05).
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
      <GlossaryCard />
    </div>
  );
}

/** Section 1 -- the end-to-end flow as a short ordered walkthrough, plus the
 * two behaviours a curator should know about: the headers-only privacy mode
 * and the learning / auto-map loop. */
function HowToCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">How it works</CardTitle>
        <CardDescription>
          From a messy vendor file to a governed master map, in one pass.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-body text-muted-foreground marker:text-foreground">
          <li>
            <span className="text-label-strong text-foreground">Create or choose a Schema</span> — build the
            canonical fields your files must resolve to on the Schemas page, or select one of the four shipped
            presets.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Upload a CSV or Excel file</span> — optionally
            attaching a map file alongside it to seed the mapping.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Review the uncertain fields</span> — anything
            the mapper is not sure about is flagged yellow with its reasoning; resolve each one. Nothing is
            trusted until every field is clear.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Confirm</span> — you must be signed in;
            the confirmation is attributed to you for provenance.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Learn the crosswalk</span> — confirming a
            mapping records the file's columns as that vendor's aliases on the Schema's crosswalk, so the next
            file from the same vendor maps deterministically with no Claude call.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Download or import the master map</span> — the
            Schema's JSON export is its master map file; move it between environments or hand it to a teammate.
          </li>
          <li>
            <span className="text-label-strong text-foreground">Reconcile the next file</span> — a known
            vendor's next file is checked against the Schema's recorded aliases instead of starting from
            scratch.
          </li>
        </ol>

        <Separator />

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <p className="text-label-strong">
              Privacy mode: <span className="text-mono-label">--headers-only</span>
            </p>
            <p className="text-body text-muted-foreground">
              With the <span className="text-mono-label">--headers-only</span> flag, mapping is proposed from
              the column headers alone — no cell values are sent to Claude. Use it when a file's contents are
              sensitive but its column names are not.
            </p>
          </div>
          <div className="flex flex-col gap-1">
            <p className="text-label-strong">Learning and auto-map</p>
            <p className="text-body text-muted-foreground">
              Once you confirm a vendor's file, its column signature is remembered. The next file with the
              same signature from that vendor auto-maps at full confidence — no further Claude call, no yellow
              fields to re-resolve.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** Section 2 -- the four locked terms with their exact locked definitions
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
