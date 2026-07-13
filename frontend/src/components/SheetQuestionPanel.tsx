import { useEffect, useState } from "react";
import { Layers, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  ApiError,
  addSchemaAlias,
  addSchemaField,
  draftSchema,
  listSchemas,
  promoteSchema,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  FieldPayload,
  FieldType,
  SchemaDraftField,
  SchemaOut,
  SchemaSummary,
  SheetOut,
  SheetQuestionResponse,
  SheetSchemaProposal,
  SheetSelection,
} from "@/lib/types";
import {
  ALL_UNKNOWN_NOTICE,
  LAYOUT_DISAGREE_ACTION,
  LAYOUT_DISAGREE_ENGAGED_LINE,
  LAYOUT_DISAGREE_UNDO_ACTION,
  allUnknown,
  coverageLine,
  detectedHeadersCaption,
  initialSelections,
  isUnreadableShape,
  layoutLine,
  refusalLine,
  sheetBadge,
  sheetKey,
  sheetSubtitle,
  sheetTitle,
  showsAskLayoutAction,
  showsDetectedHeaders,
  showsSchemaSelect,
  submitBlockedReason,
  toResolvePayload,
  whyThisSchema,
  type SheetChoice,
} from "@/state/sheets";

interface SheetQuestionPanelProps {
  question: SheetQuestionResponse;
  /** The Schema chosen in the Upload dropdown, if any -- the D-11-16
   * fallback pre-selection for a sheet the scorer proposed nothing for. */
  defaultSchema: string | null;
  /** The vendor chosen on Upload. A confirmed near match is recorded in the
   * crosswalk UNDER THIS VENDOR: `Tset` means `Test` at Sequoia, and that is a
   * fact about Sequoia's files, not about every lab's. */
  vendor: string;
  submitting: boolean;
  /** The resolve failure's consequence-first message (UI-SPEC error state),
   * carried by the reducer's `sheetQuestion.errorMessage` -- rendered as a
   * destructive Alert while every selection is preserved. */
  errorMessage: string | null;
  onResolve: (selections: SheetSelection[]) => void;
}

/** The muted structural-fact badges vs the amber act-on-this ones vs the
 * secondary readable-fact one (UI-SPEC §Color): `no table found` /
 * `not a table` / `can't read this layout yet` are facts about the sheet,
 * not warnings to act on; `header unclear` / `layout unknown` are "the tool
 * is not sure, a human must act" -- the amber token's exact existing
 * meaning; `labels down the side` is a readable, positive fact -- neither
 * an alert nor an absence, the same variant the header chips use. Which
 * badge a sheet gets is `state/sheets.ts::sheetBadge`'s call; this renders
 * its tone. */
function StatusBadge({ sheet }: { sheet: SheetOut }) {
  const badge = sheetBadge(sheet);
  if (badge === null) return null;
  switch (badge.tone) {
    case "secondary":
      return <Badge variant="secondary">{badge.label}</Badge>;
    case "muted":
      return (
        <Badge variant="outline" className="text-muted-foreground">
          {badge.label}
        </Badge>
      );
    case "amber":
      return (
        <Badge className="border-transparent bg-uncertain-bg text-uncertain-foreground">
          {badge.label}
        </Badge>
      );
  }
}

/** The per-sheet layout verdict line (UI-SPEC §Screens 1, card item 2) --
 * the kind phrase strong, the reasoning at label size (a checkable footnote
 * to the verdict, not a paragraph), the confidence mono/tabular-nums. Muted
 * by default (a confident verdict is a quiet fact); amber ONLY when the
 * server-sent `needs_confirmation` gate says so, or for the unknown state.
 * The disagree action is a REAL button with visible text, 32px hit area,
 * inline with the line -- and once engaged, the engaged copy plus the undo
 * REPLACES the line entirely. All copy comes from `state/sheets.ts`. */
function LayoutLine({
  sheet,
  askLayout,
  disabled,
  onAskLayoutChange,
}: {
  sheet: SheetOut;
  askLayout: boolean;
  disabled: boolean;
  onAskLayoutChange: (askLayout: boolean) => void;
}) {
  const line = layoutLine(sheet);
  if (line === null) return null;

  if (askLayout) {
    return (
      <p className="text-label text-muted-foreground">
        {LAYOUT_DISAGREE_ENGAGED_LINE}
        {" · "}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onAskLayoutChange(false)}
          className="min-h-8 align-baseline underline underline-offset-2 hover:text-foreground"
        >
          {LAYOUT_DISAGREE_UNDO_ACTION}
        </button>
      </p>
    );
  }

  return (
    <p className={cn("text-label", line.amber ? "text-uncertain-foreground" : "text-muted-foreground")}>
      {line.judged ? (
        <>
          {line.lead}
          <span className="font-semibold">{line.kindPhrase}</span>
          {line.rest}
          <span className="text-mono-label tabular-nums">{line.confidence}</span>
          {line.trailer}
        </>
      ) : (
        line.text
      )}
      {showsAskLayoutAction(sheet) && (
        <>
          {" "}
          <button
            type="button"
            disabled={disabled}
            onClick={() => onAskLayoutChange(true)}
            className="min-h-8 align-baseline underline underline-offset-2 hover:text-foreground"
          >
            {LAYOUT_DISAGREE_ACTION}
          </button>
        </>
      )}
    </p>
  );
}

/** Bolds the Schema's name inside the why-this-Schema sentence, without the
 * sentence itself having to know it will be rendered as JSX (`whyThisSchema`
 * stays a pure string, which is what its tests assert against).
 *
 * Only the FIRST occurrence is bolded — the name leads the sentence, and a
 * runner-up Schema named later in the same breath must not be given the same
 * weight as the one actually chosen. Untrusted text either way: both halves are
 * rendered as text children, never as markup. */
function BoldSchemaName({ text, schemaName }: { text: string; schemaName: string }) {
  const at = text.indexOf(schemaName);
  if (at === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <span className="font-semibold text-foreground">{schemaName}</span>
      {text.slice(at + schemaName.length)}
    </>
  );
}

/** The picker's escape hatch: this column belongs to no field the Schema has. */
const NEW_FIELD = "__new__";

/** A header as a plausible field name: `Ref Lo` -> `ref_lo`. A starting point the
 * curator edits, never a name applied for them — `Ref Lo` is really
 * `reference_low`, and only they know that. */
function suggestFieldName(header: string): string {
  return header
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/**
 * Add the field the Schema is missing, without leaving the upload.
 *
 * This exists because "— not in this Schema" was a DEAD END: the honest answer to
 * "which field is this?" is sometimes "none of them, yet", and the only way to act
 * on it was to abandon a half-answered upload, go to the Schemas page, and come
 * back to start over. A tool that makes the honest answer the expensive one
 * teaches people to give a dishonest one — to shove `Ref Lo` into
 * `reference_range` because that is the option in front of them.
 *
 * The TYPE is asked for, and is not optional. That was the whole objection to a
 * bare text box here: a field with no type is a field the validator cannot check,
 * so `Ref Lo` would arrive as a string, silently, and every numeric guard would
 * pass by being skipped. Two clicks buys the guard.
 */
function NewFieldForm({
  header,
  schemaName,
  busy,
  taken,
  onCancel,
  onCreate,
}: {
  header: string;
  schemaName: string;
  busy: boolean;
  taken: string[];
  onCancel: () => void;
  onCreate: (field: string, type: FieldType) => void;
}) {
  const [name, setName] = useState(() => suggestFieldName(header));
  const [type, setType] = useState<FieldType>("text");

  const clash = taken.includes(name);
  const blocked = name === "" || clash;

  return (
    <div className="mt-2 flex flex-col gap-2 rounded-md border border-border bg-background p-2">
      <input
        aria-label={`New field name for column ${header}`}
        className="w-full rounded-md border border-border bg-background px-2 py-1 text-mono-label"
        value={name}
        disabled={busy}
        onChange={(event) => setName(suggestFieldName(event.target.value))}
      />
      <select
        aria-label={`Type of the new field for column ${header}`}
        className="w-full rounded-md border border-border bg-background px-2 py-1 text-mono-label"
        value={type}
        disabled={busy}
        onChange={(event) => setType(event.target.value as FieldType)}
      >
        <option value="text">text</option>
        <option value="number">number</option>
        <option value="integer">integer</option>
        <option value="date">date</option>
      </select>
      {clash ? (
        <p className="text-mono-label text-uncertain-foreground">
          {schemaName} already has a field called {name}. Pick it from the list instead.
        </p>
      ) : (
        <p className="text-mono-label text-muted-foreground">
          Added to {schemaName} as an optional field — other vendors' files may not have
          this column.
        </p>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          className="h-6 px-2"
          disabled={busy || blocked}
          onClick={() => onCreate(name, type)}
        >
          {busy ? <Loader2 className="size-3 animate-spin" /> : "Add and map"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 px-2"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}

/**
 * The coverage evidence, as ONE table showing BOTH directions of the match.
 *
 * The three stacked lists it replaces read in three different directions, and
 * one of them read backwards: "Not matched: method" looked like the FILE had a
 * `method` column the tool could not place, when the truth is the opposite --
 * the SCHEMA has the field and the file has no column for it.
 *
 * Every column the tool could NOT place gets one amber row with a picker over
 * the Schema's still-free fields. A near match (`Tset` for `Test`) merely
 * PRE-FILLS that picker rather than living in a row of its own: accepting the
 * tool's guess and overriding it are the same question, and splitting them into
 * two row kinds put one field in two places at once (`analyte?` above, `analyte
 * — no column in this file` below) and made the table argue with itself.
 *
 * The picker deliberately offers no free-text field name. A Schema field has a
 * type, a unit and a required-ness; one invented on the ingest screen would
 * arrive with none of them and break the validator exactly where it is supposed
 * to protect. New fields are created on the Schemas page. "— not in this Schema"
 * stays available, and is honest: the column is simply not ingested.
 */
function CoverageTable({
  sheet,
  proposal,
  vendor,
}: {
  sheet: SheetOut;
  proposal: SheetSchemaProposal;
  vendor: string;
}) {
  // A column the curator has MAPPED, this session: header -> field. The confirm
  // also wrote the header into the crosswalk as a real alias under this vendor,
  // so the next file from them with the same column matches deterministically
  // and never asks again.
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});
  // What the picker currently shows for each unmapped column. A near match seeds
  // it -- the suggestion IS a pre-filled answer to the same question, not a
  // separate one, so accepting it and overriding it are one gesture, not two.
  const [picked, setPicked] = useState<Record<string, string>>(() =>
    Object.fromEntries(proposal.near_matches.map((suggestion) => [suggestion.header, suggestion.field])),
  );
  const [confirming, setConfirming] = useState<string | null>(null);
  // Fields CREATED from this screen, this session. The manifest was scored before
  // they existed, so `proposal.uncovered` cannot know about them -- they are kept
  // here and offered beside it.
  const [created, setCreated] = useState<string[]>([]);
  // Which column, if any, has the new-field form open under it.
  const [creatingFor, setCreatingFor] = useState<string | null>(null);

  const suggestions = new Map(proposal.near_matches.map((one) => [one.header, one]));
  const matchedHeaders = new Set(proposal.matched.map((pair) => pair.header));
  // Blank headers are not a column the curator can reason about ("" has no name
  // to show them), so they are never offered for mapping.
  const unmapped = sheet.headers.filter(
    (header) => header !== "" && !matchedHeaders.has(header) && !(header in confirmed),
  );
  // The fields still going begging -- and therefore exactly the fields a column
  // may be mapped ONTO. A field already taken is not offered twice.
  const available = [...proposal.uncovered, ...created].filter(
    (field) => !Object.values(confirmed).includes(field),
  );

  async function confirmColumn(header: string, field: string) {
    setConfirming(header);
    try {
      await addSchemaAlias(proposal.schema_name, field, { vendor, source_column: header });
      setConfirmed((previous) => ({ ...previous, [header]: field }));
      toast.success(`'${header}' now reads as ${field} for ${vendor}.`);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : `'${header}' was not recorded as ${field} — the Schema is unchanged.`,
      );
    } finally {
      setConfirming(null);
    }
  }

  /** Create the field the Schema is missing, then map this column onto it — in
   * one gesture, without leaving the upload.
   *
   * The field is created NOT REQUIRED, always, and that is not a shortcut: this
   * column exists in THIS vendor's file, and a field made required from one
   * vendor's layout would block the confirm gate on every other file that
   * legitimately has no such column. Making it required is a governance decision
   * about all files, and it belongs on the Schemas page, not here.
   */
  async function createAndMap(header: string, field: string, type: FieldType) {
    setConfirming(header);
    try {
      await addSchemaField(proposal.schema_name, {
        name: field,
        description: `Added while ingesting ${vendor}'s column '${header}'.`,
        type,
        allowed_values: null,
        unit: null,
        required: false,
        min: null,
        max: null,
        date_format: null,
      });
      await addSchemaAlias(proposal.schema_name, field, { vendor, source_column: header });
      setCreated((previous) => [...previous, field]);
      setConfirmed((previous) => ({ ...previous, [header]: field }));
      setCreatingFor(null);
      toast.success(`${field} added to ${proposal.schema_name}, and '${header}' now reads as it.`);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : `${field} was not added — the Schema is unchanged.`,
      );
    } finally {
      setConfirming(null);
    }
  }

  // Every row is bordered the same way and every cell is padded the same way, so
  // the reader's eye can run down either column without the grid shifting under
  // it. `[&>tr>td]` reaches the rows generated in the maps below without
  // repeating the class list on each of them — the sections are a detail of how
  // the rows are BUILT, and the table must not look like it.
  return (
    <div className="overflow-hidden rounded-lg ring-1 ring-border">
      <table className="w-full border-collapse text-mono-label">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-muted-foreground">
            <th className="w-1/2 border-r border-border px-2.5 py-1.5 text-left font-normal">
              Schema field
            </th>
            <th className="px-2.5 py-1.5 text-left font-normal">Column in this file</th>
          </tr>
        </thead>
        <tbody className="[&>tr>td]:border-border [&>tr>td]:px-2.5 [&>tr>td]:py-1.5 [&>tr>td]:align-top [&>tr>td:first-child]:border-r [&>tr:not(:last-child)>td]:border-b">
          {proposal.matched.map((pair) => (
            <tr key={`m-${pair.field}`}>
              <td>{pair.field}</td>
              <td>{pair.header}</td>
            </tr>
          ))}

          {Object.entries(confirmed).map(([header, field]) => (
            <tr key={`c-${header}`}>
              <td>{field}</td>
              <td>{header}</td>
            </tr>
          ))}

          {/* Amber, and a question. EVERY column the tool could not place gets
              the same row and the same picker — a near match only pre-fills it.
              A column with no suggestion (`LOINC`) is the more dangerous of the
              two: a missing field is a hole you can see in the output, while an
              unclaimed column is data the curator brought that will simply not be
              ingested, with nothing on screen having said so. Nothing is mapped
              until they choose and click, and none of this is counted in the
              coverage score — a guess is a question, not evidence. */}
          {unmapped.map((header) => {
            const suggestion = suggestions.get(header);
            const choice = picked[header] ?? "";
            const busy = confirming === header;
            return (
              <tr key={`n-${header}`} className="bg-uncertain-bg">
                <td>
                  <select
                    aria-label={`Schema field for column ${header}`}
                    className="w-full rounded-md border border-border bg-background px-2 py-1 text-mono-label disabled:opacity-50"
                    value={creatingFor === header ? NEW_FIELD : choice}
                    disabled={confirming !== null}
                    onChange={(event) => {
                      const next = event.target.value;
                      // "the Schema has no field for this" is a real answer, and
                      // until now it was a dead end that sent the curator to
                      // another page mid-upload. It is now the start of one.
                      setCreatingFor(next === NEW_FIELD ? header : null);
                      if (next !== NEW_FIELD) {
                        setPicked((previous) => ({ ...previous, [header]: next }));
                      }
                    }}
                  >
                    <option value="">— not in this Schema</option>
                    {available.map((field) => (
                      <option key={field} value={field}>
                        {field}
                      </option>
                    ))}
                    <option value={NEW_FIELD}>+ Add a field to this Schema…</option>
                  </select>
                  {creatingFor === header && (
                    <NewFieldForm
                      header={header}
                      schemaName={proposal.schema_name}
                      busy={busy}
                      taken={[...proposal.matched.map((p) => p.field), ...available]}
                      onCancel={() => setCreatingFor(null)}
                      onCreate={(field, type) => createAndMap(header, field, type)}
                    />
                  )}
                </td>
                <td>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span>{header}</span>
                    {/* The known spelling is an ALIAS, not a field — and saying
                        only "looks like 'test'" sent the curator hunting for a
                        `test` option the picker does not have and never could.
                        The sentence has to carry both halves: the spelling it
                        resembles AND the field this Schema reads that spelling
                        as, which is the option already selected on the left. */}
                    {suggestion ? (
                      <span className="text-muted-foreground">
                        — looks like '{suggestion.resembles}', which this Schema reads as{" "}
                        {suggestion.field}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">— not ingested unless mapped</span>
                    )}
                    {creatingFor === header ? null : choice === "" ? (
                      <span className="text-muted-foreground">· left out</span>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-6 px-2"
                        disabled={confirming !== null}
                        onClick={() => confirmColumn(header, choice)}
                      >
                        {busy ? <Loader2 className="size-3 animate-spin" /> : `Confirm as ${choice}`}
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}

          {available.map((field) => (
            <tr key={`u-${field}`}>
              <td>{field}</td>
              <td className="text-muted-foreground">— no column in this file</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The draft-a-Schema form: what to do when the honest answer to "which Schema
 * is this sheet?" is "none of them".
 *
 * "Proposed: skip this sheet" was a dead end wearing a verdict's clothes. It is
 * the RIGHT answer — a sheet whose columns match nothing has no business being
 * forced into a Schema built for another file — but the only move it left the
 * curator was to abandon a half-answered upload, build a Schema by hand on
 * another screen, and start the upload over. The same lesson as the missing
 * FIELD (`NewFieldForm`), one level up: a tool that makes the honest answer the
 * expensive one is teaching people to give a dishonest one.
 *
 * So the tool drafts the Schema this sheet WOULD need, from the sheet in front
 * of them — and drafts it as a PROPOSAL. Every row here is editable: the field
 * name, its type, whether it is required, and whether the column is kept at all.
 * The type is Claude's guess and is labelled with what it was guessed FROM
 * (`reason`), because a type nobody can check is a type nobody should trust —
 * and the validator will enforce whatever survives this form on every value.
 * Nothing exists until "Create Schema" is pressed, and what is created is
 * attributed to the human who pressed it.
 */
function DraftSchemaForm({
  uploadToken,
  sheet,
  onCreated,
  onCancel,
}: {
  uploadToken: string;
  sheet: SheetOut;
  onCreated: (schema: SchemaOut) => void;
  onCancel: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [rows, setRows] = useState<DraftRow[]>([]);

  useEffect(() => {
    let live = true;
    draftSchema(uploadToken, sheet.sheet_name, sheet.table_index)
      .then((draft) => {
        if (!live) return;
        setName(draft.name);
        setRows(draft.fields.map((field) => ({ ...field, keep: true })));
      })
      .catch((err: unknown) => {
        if (!live) return;
        const fallback = "Couldn't draft a Schema for this sheet right now.";
        toast.error(err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback);
        onCancel();
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
    // The draft is a function of the SHEET, and the sheet does not change while
    // this form is open: re-running it on every render of the parent would spend
    // a model call to redraw a form the human is already editing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadToken, sheet.sheet_name, sheet.table_index]);

  function patch(index: number, change: Partial<DraftRow>) {
    setRows((prev) => prev.map((row, at) => (at === index ? { ...row, ...change } : row)));
  }

  const kept = rows.filter((row) => row.keep);
  const blocked = name.trim() === "" || kept.length === 0 || hasDuplicateName(kept);

  async function handleCreate() {
    setCreating(true);
    try {
      const schema = await promoteSchema(name.trim(), {
        name: name.trim(),
        fields: kept.map(toFieldPayload),
      });
      onCreated(schema);
    } catch (err: unknown) {
      const fallback = "Nothing was created — the Schema couldn't be saved.";
      toast.error(err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback);
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-body text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Drafting a Schema from this sheet's columns…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-background p-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`draft-name-${sheetKey(sheet)}`}>New Schema name</Label>
        <input
          id={`draft-name-${sheetKey(sheet)}`}
          className="w-full rounded-md border border-border bg-background px-2 py-1 text-mono-label"
          value={name}
          disabled={creating}
          onChange={(event) => setName(event.target.value)}
        />
      </div>

      <p className="text-body text-muted-foreground">
        Drafted from this sheet's columns — nothing is created until you press Create Schema.
        Types are proposals: the validator will enforce whatever you leave here on every value.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-mono-label">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-1 pr-2 font-normal">Keep</th>
              <th className="py-1 pr-2 font-normal">Column in this file</th>
              <th className="py-1 pr-2 font-normal">Field name</th>
              <th className="py-1 pr-2 font-normal">Type</th>
              <th className="py-1 pr-2 font-normal">Required</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.source_header}-${index}`} className="border-b border-border/50 align-top">
                <td className="py-1 pr-2">
                  <Checkbox
                    aria-label={`Keep the column ${row.source_header}`}
                    checked={row.keep}
                    disabled={creating}
                    onCheckedChange={(checked) => patch(index, { keep: Boolean(checked) })}
                  />
                </td>
                <td className="py-1 pr-2">
                  {row.source_header === "" ? "(blank header)" : row.source_header}
                  {/* The evidence behind the type, in the row it justifies: a
                      curator who cannot see WHY a column was called a number
                      can only accept the guess, which is not a review. */}
                  <p className="text-muted-foreground">{row.reason}</p>
                </td>
                <td className="py-1 pr-2">
                  <input
                    aria-label={`Field name for column ${row.source_header}`}
                    className="w-full rounded-md border border-border bg-background px-2 py-1"
                    value={row.name}
                    disabled={creating || !row.keep}
                    onChange={(event) => patch(index, { name: suggestFieldName(event.target.value) })}
                  />
                </td>
                <td className="py-1 pr-2">
                  <select
                    aria-label={`Type of the field for column ${row.source_header}`}
                    className="rounded-md border border-border bg-background px-2 py-1"
                    value={row.type}
                    disabled={creating || !row.keep}
                    onChange={(event) => patch(index, { type: event.target.value as FieldType })}
                  >
                    <option value="text">text</option>
                    <option value="number">number</option>
                    <option value="integer">integer</option>
                    <option value="date">date</option>
                  </select>
                </td>
                <td className="py-1 pr-2">
                  <Checkbox
                    aria-label={`Require the field for column ${row.source_header}`}
                    checked={row.required}
                    disabled={creating || !row.keep}
                    onCheckedChange={(checked) => patch(index, { required: Boolean(checked) })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasDuplicateName(kept) && (
        <p className="text-mono-label text-uncertain-foreground">
          Two kept columns have the same field name — rename one, or stop keeping it.
        </p>
      )}

      <div className="flex gap-2">
        <Button type="button" size="sm" disabled={creating || blocked} onClick={handleCreate}>
          {creating ? <Loader2 className="size-3 animate-spin" /> : "Create Schema"}
        </Button>
        <Button type="button" size="sm" variant="ghost" disabled={creating} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** One editable row of the draft form: Claude's proposed field, plus the human's
 * "keep this column at all?" answer, which is theirs alone and has no wire
 * counterpart — a dropped column is simply never sent. */
interface DraftRow extends SchemaDraftField {
  keep: boolean;
}

function hasDuplicateName(rows: DraftRow[]): boolean {
  const names = rows.map((row) => row.name);
  return new Set(names).size !== names.length;
}

/** A drafted row -> the `FieldPayload` the create-Schema body takes. Only the
 * four attributes the draft actually established are set; every other constraint
 * (`min`, `max`, `unit`, `allowed_values`, `date_format`) is left `null` rather
 * than invented, and stays a decision for the Schemas page, where the curator can
 * see the whole Schema at once. */
function toFieldPayload(row: DraftRow): FieldPayload {
  return {
    name: row.name,
    description: null,
    type: row.type,
    allowed_values: null,
    unit: null,
    required: row.required,
    min: null,
    max: null,
    date_format: null,
  };
}

interface SheetCardProps {
  sheet: SheetOut;
  choice: SheetChoice;
  schemas: SchemaSummary[];
  uploadToken: string;
  vendor: string;
  disabled: boolean;
  onTickedChange: (ticked: boolean) => void;
  onSchemaChange: (schemaName: string) => void;
  onAskLayoutChange: (askLayout: boolean) => void;
  onSchemaCreated: (schema: SchemaOut) => void;
}

/**
 * One sheet's bordered block (12-UI-SPEC §Screens 1, top to bottom):
 * selection row -> layout line -> detected headers/labels -> proposal +
 * coverage -> Schema select. The proposal/coverage block is ALWAYS visible,
 * never behind a disclosure -- D-11-24 made the coverage number the only
 * thing the human has to go on when deciding whether a sheet is a data sheet
 * ("1/7" beside "6/7" is what tells them LEGEND is a legend), so it is the
 * control, not decoration. Sheet names, headers, labels, and Claude's
 * reasoning are untrusted text, rendered as text children only (T-11-33 --
 * React escapes by default; no innerHTML anywhere).
 *
 * A sheet whose layout VERDICT is unreadable is the one case where the
 * middle two blocks collapse to a single honest refusal line: it is not a
 * table this tool can read, so it has no headers to detect and no coverage
 * to report, and a Schema chosen for it would answer a question the tool has
 * just said it cannot ask. The checkbox STAYS -- the human may still insist,
 * and fail-closed covers them if they do (nothing maps, every field goes
 * amber, the confirm gate blocks the export). Marked, never dropped, never
 * disabled away (SHEET-04). A `key_value` sheet is NOT that case: it renders
 * its labels, its coverage, and its Schema select like any readable sheet.
 */
function SheetCard({
  sheet,
  choice,
  schemas,
  uploadToken,
  vendor,
  disabled,
  onTickedChange,
  onSchemaChange,
  onAskLayoutChange,
  onSchemaCreated,
}: SheetCardProps) {
  const top = sheet.proposals[0] ?? null;
  const second = sheet.proposals[1] ?? null;
  const unreadable = isUnreadableShape(sheet);
  const [drafting, setDrafting] = useState(false);
  // coverageLine's profile/crosswalk copy always leads with the count --
  // split it out so the count renders emphasized (600, tabular-nums, accent)
  // without a second, hand-built copy of the contract string.
  const countPrefix = top !== null ? `${top.matched_count}/${top.total_fields}` : null;

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border p-3">
      <label className="flex min-h-8 cursor-pointer flex-wrap items-center gap-1">
        <Checkbox
          checked={choice.ticked}
          onCheckedChange={(checked) => onTickedChange(Boolean(checked))}
          disabled={disabled}
        />
        <span className="text-mono-label font-semibold">{sheetTitle(sheet)}</span>
        {sheetSubtitle(sheet) && (
          <span className="ml-2 text-mono-label text-muted-foreground">{sheetSubtitle(sheet)}</span>
        )}
        <span className="ml-2 text-mono-label tabular-nums text-muted-foreground">
          {sheet.row_count} rows
        </span>
        <span className="ml-2">
          <StatusBadge sheet={sheet} />
        </span>
      </label>

      <LayoutLine
        sheet={sheet}
        askLayout={choice.askLayout}
        disabled={disabled}
        onAskLayoutChange={onAskLayoutChange}
      />

      {sheet.status === "header_uncertain" && (
        <p className="text-body text-muted-foreground">
          If you ingest this sheet, you'll be asked to point out its header row.
        </p>
      )}

      {showsDetectedHeaders(sheet) && (
        <div className="flex flex-col gap-2">
          <span className="text-label text-muted-foreground">{detectedHeadersCaption(sheet)}</span>
          <div className="flex flex-wrap gap-2">
            {sheet.headers.map((header, index) => (
              <Badge key={`${header}-${index}`} variant="secondary" className="text-mono-label">
                {header === "" ? "(blank header)" : header}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {unreadable ? (
        // Claude's VERDICT says there is nothing here this tool can read as a
        // table, so the card has NO answer here -- not a header list (those
        // cells would be values), not a Schema, not a coverage number. One
        // honest per-kind refusal line takes their place. Muted, like every
        // other absence: a structural fact, not a warning to act on -- the
        // disagree action on the layout line above is the human's recourse.
        <p className="text-body text-muted-foreground">{refusalLine(sheet)}</p>
      ) : top === null ? (
        // `proposals: []` IS the propose-skip signal (D-11-06) -- an absence,
        // not an achievement: muted, never amber, never accent. But an absence
        // the human can now ACT on: skipping is still the proposal, and drafting
        // the Schema this sheet would need is the way out that used to mean
        // abandoning the upload.
        <div className="flex flex-col gap-2">
          <p className="text-body text-muted-foreground">
            No canonical fields matched any Schema — proposed: skip this sheet.
          </p>
          {drafting ? (
            <DraftSchemaForm
              uploadToken={uploadToken}
              sheet={sheet}
              onCancel={() => setDrafting(false)}
              onCreated={(schema) => {
                setDrafting(false);
                onSchemaCreated(schema);
              }}
            />
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="self-start"
              disabled={disabled}
              onClick={() => setDrafting(true)}
            >
              Draft a Schema from this sheet
            </Button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {top.source === "claude" ? (
            // D-11-19's last-resort ranking carries no crosswalk evidence at
            // all -- the label IS the disclosure that nothing is behind it.
            <p className="text-body">{coverageLine(top)}</p>
          ) : (
            <p className="text-body">
              <span className="font-semibold tabular-nums text-primary">{countPrefix}</span>
              {coverageLine(top).slice(countPrefix?.length ?? 0)}
            </p>
          )}
          {sheet.tie && second !== null && (
            <p className="text-body text-uncertain-foreground">
              Tie — {top.schema_name} and {second.schema_name} both match {top.matched_count}/
              {top.total_fields}. Choose one to ingest this sheet.
            </p>
          )}
          {/* WHY, not just what. The coverage number says what the tool
              concluded; this says what it concluded it FROM — which is the only
              thing that lets the curator disagree with it. */}
          <p className="text-body text-muted-foreground">
            <BoldSchemaName text={whyThisSchema(top, second)} schemaName={top.schema_name} />
          </p>
          {top.matched.length > 0 || top.uncovered.length > 0 ? (
            <CoverageTable sheet={sheet} proposal={top} vendor={vendor} />
          ) : null}
        </div>
      )}

      {showsSchemaSelect(sheet) && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`sheet-schema-${sheetKey(sheet)}`}>Schema for this sheet</Label>
          <Select
            value={choice.schemaName ?? undefined}
            onValueChange={(next) => onSchemaChange(String(next))}
            disabled={disabled || schemas.length === 0}
          >
            <SelectTrigger id={`sheet-schema-${sheetKey(sheet)}`} className="w-full">
              <SelectValue placeholder="Choose a Schema…" />
            </SelectTrigger>
            <SelectContent>
              {schemas.map((schema) => (
                <SelectItem key={schema.id} value={schema.name}>
                  {schema.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}

/**
 * The `kind:"sheet_question"` manifest panel (SHEET-01, UI-SPEC §Screens 1)
 * -- the 4th inline question sibling, rendered below `UploadDropzone` in the
 * SAME flow, never a modal. One bordered block per sheet, ONE submit for all
 * sheets: `DateFormatQuestionPanel`'s multi-item/single-submit shape with a
 * checkbox and a Schema `Select` where the date panel has two option buttons.
 * The tool proposes (pre-ticks, pre-selects) and the human disposes -- a
 * proposal never auto-applies (D-11-06), a tie arrives with an EMPTY Select,
 * a gate-failed sheet is marked but still tickable, and nothing is ingested
 * until the human confirms. Every decision lives in `state/sheets.ts`; this
 * component holds only the answers array and renders.
 */
export function SheetQuestionPanel({
  question,
  defaultSchema,
  vendor,
  submitting,
  errorMessage,
  onResolve,
}: SheetQuestionPanelProps) {
  const [choices, setChoices] = useState<SheetChoice[]>(() =>
    initialSelections(question, defaultSchema)
  );
  const [schemas, setSchemas] = useState<SchemaSummary[]>([]);

  useEffect(() => {
    listSchemas()
      .then(setSchemas)
      .catch((err: unknown) => {
        const fallback = "Couldn't load Schemas right now.";
        toast.error(err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback);
      });
  }, []);

  function setTicked(key: string, ticked: boolean) {
    setChoices((prev) =>
      prev.map((choice) => (sheetKey(choice) === key ? { ...choice, ticked } : choice))
    );
  }

  function setSchema(key: string, schemaName: string) {
    setChoices((prev) =>
      prev.map((choice) => (sheetKey(choice) === key ? { ...choice, schemaName } : choice))
    );
  }

  function setAskLayout(key: string, askLayout: boolean) {
    setChoices((prev) =>
      prev.map((choice) => (sheetKey(choice) === key ? { ...choice, askLayout } : choice))
    );
  }

  /** A Schema drafted for THIS sheet and created by the human: add it to the
   * selector and select it for the sheet it was drafted from. Selecting it is
   * not an assumption — it is the only reason they created it — and the sheet
   * still has to be ticked and submitted like any other. */
  function handleSchemaCreated(key: string, schema: SchemaOut) {
    setSchemas((prev) =>
      prev.some((existing) => existing.id === schema.id) ? prev : [...prev, schema]
    );
    setSchema(key, schema.name);
    toast.success(`Created the Schema ${schema.name}.`);
  }

  function handleSubmit() {
    onResolve(toResolvePayload(question.upload_token, choices).selections);
  }

  const blockedReason = submitBlockedReason(choices);
  const tickedCount = choices.filter((choice) => choice.ticked).length;

  // A CSV (and a one-sheet workbook) reaches this screen too, since a Schema is
  // no longer demanded before upload. There is nothing to CHOOSE between there
  // -- calling one CSV "1 worksheets" of a "workbook" would be the screen
  // describing something that isn't in front of the curator.
  const isSingleSource = question.sheets.length === 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-heading">
          <Layers className="size-5" />
          {isSingleSource ? "Confirm what was read" : "Choose sheets to ingest"}
        </CardTitle>
        <p className="text-body text-muted-foreground">
          {isSingleSource ? (
            <>
              Here is what the tool read, and the Schema it proposes. Nothing is ingested until you
              confirm.
            </>
          ) : (
            <>
              This workbook has {question.sheets.length} worksheets. Tick the ones to ingest — each
              becomes its own independent dataset with its own Schema. Nothing is ingested until you
              confirm.
            </>
          )}
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {allUnknown(question.sheets) && (
          // The judge-was-unreachable state, designed for rather than merely
          // survived (D-12-16): ONE amber notice at workbook level, and the
          // cards below stay quiet -- no per-card repetition of the story.
          <p className="rounded-lg bg-uncertain-bg p-3 text-body text-uncertain-foreground">
            {ALL_UNKNOWN_NOTICE}
          </p>
        )}

        {question.sheets.map((sheet) => {
          const key = sheetKey(sheet);
          const choice = choices.find((entry) => sheetKey(entry) === key);
          if (choice === undefined) return null;
          return (
            <SheetCard
              key={key}
              sheet={sheet}
              choice={choice}
              schemas={schemas}
              uploadToken={question.upload_token}
              vendor={vendor}
              disabled={submitting}
              onTickedChange={(ticked) => setTicked(key, ticked)}
              onSchemaChange={(schemaName) => setSchema(key, schemaName)}
              onAskLayoutChange={(askLayout) => setAskLayout(key, askLayout)}
              onSchemaCreated={(schema) => handleSchemaCreated(key, schema)}
            />
          );
        })}

        {errorMessage !== null && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        )}

        <Button
          type="button"
          disabled={submitting || blockedReason !== null}
          onClick={handleSubmit}
          className="self-start"
        >
          {submitting && <Loader2 className="size-4 animate-spin" />}
          Ingest {tickedCount} Selected Sheet(s)
        </Button>
        {blockedReason !== null && (
          <p className="text-mono-label text-muted-foreground">{blockedReason}</p>
        )}
      </CardContent>
    </Card>
  );
}
