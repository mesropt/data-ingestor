import { useState } from "react";
import { ArrowLeft, Check, FileArchive } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DateFormatQuestionPanel } from "@/components/DateFormatQuestionPanel";
import { ReconcilePanel } from "@/components/ReconcilePanel";
import { StructuralHintPanel } from "@/components/StructuralHintPanel";
import { Review } from "@/screens/Review";
import {
  ApiError,
  downloadGroupArchive,
  resolveDateFormat,
  resolveHint,
  resolveReconcile,
} from "@/lib/api";
import type {
  FieldMappingOut,
  SheetGroupResponse,
  SheetMemberResponse,
  UploadResponse,
} from "@/lib/types";
import {
  groupExportBlockedReason,
  memberPaneKey,
  memberStatus,
  showTabStrip,
  type GroupMemberView,
  type MemberStatus,
} from "@/state/review";

interface ReviewGroupTabsProps {
  /** Back to the table/sheet selection this group came from. Optional so the
   * component stays usable (and testable) with no navigation to go back TO. */
  onBack?: () => void;
  /** The `kind:"sheet_group"` response: N INDEPENDENT datasets (D-11-08).
   * Nothing here merges anything -- each member confirms on its own gate. */
  group: SheetGroupResponse;
  /** The Schema the human chose for each sheet on the selection panel
   * (`SheetQuestionPanel`'s own submitted selections, threaded through
   * `Upload.tsx` -> `App.tsx`) -- each member's Review shows it read-only
   * and builds its `/api/confirm` request from it, exactly as the
   * single-dataset path does. */
  schemasBySheet: Record<string, string>;
  /** The upload's headers-only choice (P2) -- a member whose arm is still a
   * question renders its panel with the SAME privacy rule the Upload
   * screen's own panels enforce. */
  headersOnly: boolean;
  /** The source label the curator named on Upload -- every member of the group
   * came from the SAME file, so they share one vendor. Threaded, never re-asked. */
  vendor: string;
  /** Auth mirror threaded into each member's Review (the server re-checks
   * every confirm regardless, P1). */
  signedIn: boolean;
  verified: boolean;
  onRequireSignIn: () => void;
}

function consequenceMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && typeof error.detail === "string") return error.detail;
  return fallback;
}

/** One tab trigger's status indicator (UI-SPEC Copywriting Contract): the
 * amber "{n} to resolve" badge, the amber "question pending" dot, or the
 * green "confirmed" check. Every icon-only glyph carries an `aria-label`
 * -- tab status is never conveyed by colour or shape alone. A `ready`
 * member shows no glyph: its own ConfirmGate carries that state. */
function statusIndicator(status: MemberStatus) {
  switch (status.kind) {
    case "question":
      return (
        <span
          role="img"
          aria-label="question pending"
          className="size-2 shrink-0 rounded-full bg-uncertain"
        />
      );
    case "resolve":
      return (
        <Badge className="border-transparent bg-uncertain-bg text-uncertain-foreground">
          {status.count} to resolve
        </Badge>
      );
    case "confirmed":
      return <Check role="img" aria-label="confirmed" className="size-4 shrink-0 text-success" />;
    case "ready":
      return null;
  }
}

/**
 * The tabbed Review over N independent datasets (D-11-10, UI-SPEC
 * Discretion §2) -- one tab per sheet-group member, each holding the WHOLE
 * existing Review: its own table, escalation line, vendor input, 4-tier
 * ConfirmGate and ExportBar. The gate is per member and never aggregated
 * (D-11-08); the group "Download All" bar is a convenience lookup over the
 * per-member confirms, never a bypass (T-11-38 -- the server refuses the
 * archive independently).
 *
 * The one correctness hazard this component exists to close (T-11-37):
 * `Review` holds a curator's amber resolutions in local state, so a
 * remounting tab silently destroys their work. Every pane therefore stays
 * mounted while hidden, and each member's Review is keyed by its OWN
 * upload token (`memberPaneKey`, pure and tab-blind) -- a tab switch can
 * change neither the mount nor the key.
 *
 * N=1 renders with no tab strip and no group bar -- visually today's
 * Review plus the provenance line (SHEET-01's no-regression clause).
 */
export function ReviewGroupTabs({
  group,
  schemasBySheet,
  headersOnly,
  vendor,
  signedIn,
  verified,
  onBack,
  onRequireSignIn,
}: ReviewGroupTabsProps) {
  const [active, setActive] = useState<string>(group.members[0]?.sheet_name ?? "");
  // A member's CURRENT arm: a question resolve swaps it in place (the tab
  // then shows the normal Review content), seeded from the group response.
  const [responses, setResponses] = useState<Record<string, SheetMemberResponse>>(() =>
    Object.fromEntries(group.members.map((m) => [m.sheet_name, m.response]))
  );
  // Mirrors only -- each member's Review OWNS its resolution state and
  // reports it up (`onMappingsChange`/`onConfirmed`); these maps exist so
  // the tab badges and the group bar can read live per-member verdicts
  // without controlling (and thereby risking a remount of) any member.
  const [mappingsBySheet, setMappingsBySheet] = useState<Record<string, FieldMappingOut[]>>({});
  const [confirmedSheets, setConfirmedSheets] = useState<Record<string, boolean>>({});
  const [resolvingSheet, setResolvingSheet] = useState<string | null>(null);

  const views: GroupMemberView[] = group.members.map((member) => {
    const response = responses[member.sheet_name] ?? member.response;
    return {
      sheetName: member.sheet_name,
      schemaName: member.schema_name ?? null,
      response,
      mappings:
        mappingsBySheet[member.sheet_name] ??
        (response.kind === "mapping" ? response.field_mappings : []),
      confirmed: confirmedSheets[member.sheet_name] ?? false,
    };
  });

  /** One member's question resolve, inside its own tab. On success the
   * member's arm is swapped IN PLACE (question -> mapping, or a follow-up
   * question -- the server is allowed to still be unsure); no sibling is
   * touched. A group can never nest (`SheetMemberResponse` excludes both
   * group kinds by type), so a group-shaped result is treated as the
   * failure it would be. */
  async function resolveMember(sheetName: string, call: () => Promise<UploadResponse>) {
    setResolvingSheet(sheetName);
    try {
      const result = await call();
      if (result.kind === "sheet_question" || result.kind === "sheet_group") {
        toast.error("Couldn't apply your resolution — the server answered out of order. Nothing was saved.");
        return;
      }
      setResponses((prev) => ({ ...prev, [sheetName]: result }));
      if (result.kind === "mapping") {
        setMappingsBySheet((prev) => ({ ...prev, [sheetName]: result.field_mappings }));
      }
    } catch (err) {
      toast.error(
        consequenceMessage(
          err,
          "Couldn't apply your resolution right now. Nothing was saved — retry, or try again in a moment."
        )
      );
    } finally {
      setResolvingSheet(null);
    }
  }

  /** One member's pane content: the whole existing Review when its arm is a
   * mapping; its OWN question panel, verbatim, in place of the table while
   * its arm is still a question (SHEET-04 -- the recursive-arm shape). */
  function memberContent(view: GroupMemberView) {
    const { sheetName, response } = view;
    switch (response.kind) {
      case "mapping":
        return (
          <Review
            key={memberPaneKey(view)}
            mapping={response}
            schemaName={view.schemaName ?? schemasBySheet[sheetName] ?? null}
            vendor={vendor}
            sheetName={sheetName}
            signedIn={signedIn}
            verified={verified}
            onRequireSignIn={onRequireSignIn}
            onMappingsChange={(mappings) =>
              setMappingsBySheet((prev) => ({ ...prev, [sheetName]: mappings }))
            }
            onConfirmed={() => setConfirmedSheets((prev) => ({ ...prev, [sheetName]: true }))}
          />
        );
      case "structural_question":
        return (
          <StructuralHintPanel
            question={response}
            headersOnly={headersOnly}
            submitting={resolvingSheet === sheetName}
            onResolve={(hint) =>
              resolveMember(sheetName, () => resolveHint(response.upload_token, hint))
            }
          />
        );
      case "date_question":
        return (
          <DateFormatQuestionPanel
            question={response}
            headersOnly={headersOnly}
            submitting={resolvingSheet === sheetName}
            onResolve={(choices) =>
              resolveMember(sheetName, () => resolveDateFormat(response.upload_token, choices))
            }
          />
        );
      case "reconcile_question":
        // Structurally unreachable for a member (map files ride /api/upload
        // only), but the union honestly includes it -- render the existing
        // panel verbatim rather than a dead end.
        return (
          <ReconcilePanel
            question={response}
            submitting={resolvingSheet === sheetName}
            onResolve={(choices) =>
              resolveMember(sheetName, () => resolveReconcile(response.upload_token, choices))
            }
          />
        );
    }
  }

  // SHEET-01 no-regression: a single-member group renders with no tab strip
  // and no group bar -- exactly today's Review plus the provenance line.
  if (!showTabStrip(group.members)) {
    const only = views[0];
    return only ? <>{memberContent(only)}</> : null;
  }

  const blockedReason = groupExportBlockedReason(views);
  const downloadLabel = `Download All (${group.members.length} datasets)`;

  return (
    <div className="flex flex-col gap-4">
      {/* The group bar: an in-flow block ABOVE the strip, never a second
       * sticky footer (two sticky footers would compete for the same edge).
       * Enabled ONLY when every member is confirmed -- a convenience over
       * the per-member gates, never a bypass (T-11-38: the server refuses
       * the archive independently while any member has no recorded run). */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Back to the table/sheet selection. Nothing is discarded: the workbook
            is still retained server-side under the same token, and every amber
            field already resolved in a tab stays resolved, because neither this
            screen nor Upload ever unmounts. */}
        {onBack && (
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft className="size-4" />
            Back to sheets
          </Button>
        )}
        {blockedReason === null ? (
          <a href={downloadGroupArchive(group.group_id)} download className={buttonVariants()}>
            <FileArchive className="size-4" />
            {downloadLabel}
          </a>
        ) : (
          <>
            <Button disabled>
              <FileArchive className="size-4" />
              {downloadLabel}
            </Button>
            <p className="text-body text-muted-foreground">{blockedReason}</p>
          </>
        )}
      </div>

      <Tabs value={active} onValueChange={(value) => setActive(String(value))}>
        {/* WRAPS rather than scrolls (T-11-39): every member stays visible
         * -- a hidden member is a silently-forgotten dataset, which this
         * phase exists to prevent. */}
        <TabsList className="h-auto flex-wrap">
          {views.map((view) => (
            <TabsTrigger key={view.sheetName} value={view.sheetName} className="min-h-8 gap-1.5">
              <span className="text-mono-label">{view.sheetName}</span>
              {statusIndicator(memberStatus(view))}
            </TabsTrigger>
          ))}
        </TabsList>
        {views.map((view) => (
          /* forceMount, structurally (T-11-37): every pane stays mounted
           * while inactive -- the installed primitive is @base-ui/react,
           * whose Tabs.Panel spells Radix's `forceMount` as `keepMounted`
           * (it renders the inactive pane with `hidden` + `inert` itself).
           * `Review` holds a curator's amber resolutions in local state; a
           * pane that unmounted on a tab switch would silently destroy
           * their work, which is a correctness failure, not a UX nit. */
          <TabsContent key={view.sheetName} value={view.sheetName} keepMounted>
            {memberContent(view)}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
