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
import { ApiError, listSchemas } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SchemaSummary, SheetOut, SheetQuestionResponse, SheetSelection } from "@/lib/types";
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
  showsAskLayoutAction,
  showsDetectedHeaders,
  showsSchemaSelect,
  submitBlockedReason,
  toResolvePayload,
  type SheetChoice,
} from "@/state/sheets";

interface SheetQuestionPanelProps {
  question: SheetQuestionResponse;
  /** The Schema chosen in the Upload dropdown, if any -- the D-11-16
   * fallback pre-selection for a sheet the scorer proposed nothing for. */
  defaultSchema: string | null;
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

interface SheetCardProps {
  sheet: SheetOut;
  choice: SheetChoice;
  schemas: SchemaSummary[];
  disabled: boolean;
  onTickedChange: (ticked: boolean) => void;
  onSchemaChange: (schemaName: string) => void;
  onAskLayoutChange: (askLayout: boolean) => void;
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
  disabled,
  onTickedChange,
  onSchemaChange,
  onAskLayoutChange,
}: SheetCardProps) {
  const top = sheet.proposals[0] ?? null;
  const second = sheet.proposals[1] ?? null;
  const unreadable = isUnreadableShape(sheet);
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
        <span className="text-mono-label font-semibold">{sheet.sheet_name}</span>
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
        // not an achievement: muted, never amber, never accent.
        <p className="text-body text-muted-foreground">
          No canonical fields matched any Schema — proposed: skip this sheet.
        </p>
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
          {top.matched.map((pair) => (
            <p key={pair.field} className="text-mono-label">
              {pair.field} ← {pair.header}
            </p>
          ))}
          {top.uncovered.length > 0 && (
            <p className="text-mono-label text-muted-foreground">
              Not matched: {top.uncovered.join(", ")}
            </p>
          )}
        </div>
      )}

      {showsSchemaSelect(sheet) && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`sheet-schema-${sheet.sheet_name}`}>Schema for this sheet</Label>
          <Select
            value={choice.schemaName ?? undefined}
            onValueChange={(next) => onSchemaChange(String(next))}
            disabled={disabled || schemas.length === 0}
          >
            <SelectTrigger id={`sheet-schema-${sheet.sheet_name}`} className="w-full">
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

  function setTicked(sheetName: string, ticked: boolean) {
    setChoices((prev) =>
      prev.map((choice) => (choice.sheetName === sheetName ? { ...choice, ticked } : choice))
    );
  }

  function setSchema(sheetName: string, schemaName: string) {
    setChoices((prev) =>
      prev.map((choice) => (choice.sheetName === sheetName ? { ...choice, schemaName } : choice))
    );
  }

  function setAskLayout(sheetName: string, askLayout: boolean) {
    setChoices((prev) =>
      prev.map((choice) => (choice.sheetName === sheetName ? { ...choice, askLayout } : choice))
    );
  }

  function handleSubmit() {
    onResolve(toResolvePayload(question.upload_token, choices).selections);
  }

  const blockedReason = submitBlockedReason(choices);
  const tickedCount = choices.filter((choice) => choice.ticked).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-heading">
          <Layers className="size-5" />
          Choose sheets to ingest
        </CardTitle>
        <p className="text-body text-muted-foreground">
          This workbook has {question.sheets.length} worksheets. Tick the ones to ingest — each
          becomes its own independent dataset with its own Schema. Nothing is ingested until you
          confirm.
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
          const choice = choices.find((entry) => entry.sheetName === sheet.sheet_name);
          if (choice === undefined) return null;
          return (
            <SheetCard
              key={sheet.sheet_name}
              sheet={sheet}
              choice={choice}
              schemas={schemas}
              disabled={submitting}
              onTickedChange={(ticked) => setTicked(sheet.sheet_name, ticked)}
              onSchemaChange={(schemaName) => setSchema(sheet.sheet_name, schemaName)}
              onAskLayoutChange={(askLayout) => setAskLayout(sheet.sheet_name, askLayout)}
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
