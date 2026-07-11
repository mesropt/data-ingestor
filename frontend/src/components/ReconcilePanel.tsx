import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ReconcileChoice, ReconcileQuestionResponse } from "@/lib/types";
import { buildResolvePayload, initialReconcileChoices, setChoice } from "@/state/reconcile";

interface ReconcilePanelProps {
  question: ReconcileQuestionResponse;
  submitting: boolean;
  onResolve: (choices: ReconcileChoice[]) => void;
}

/** Inline reconcile resolution (D-08-06, RECON-02) -- renders directly below
 * `UploadDropzone` in the SAME upload flow, mirroring `StructuralHintPanel`,
 * never a modal/wizard step. It lists each alias-target disagreement between
 * the uploaded map file and the master crosswalk and lets the human pick, per
 * conflict, keep-master (the master's stored field) or take-map-file (the map
 * file's asserted field for this run). Every conflict defaults to keep_master
 * (the safe no-op-against-master default, P1/D-08-02); the choices drive the
 * pure `state/reconcile.ts` model and re-submit via `onResolve`.
 *
 * All rendered vendor/column/field strings come straight off the server's
 * reconcile question and are UNTRUSTED crosswalk text -- rendered
 * escape-by-default by React, never via `dangerouslySetInnerHTML` (T-08-11).
 */
export function ReconcilePanel({ question, submitting, onResolve }: ReconcilePanelProps) {
  const [choices, setChoices] = useState<ReconcileChoice[]>(() =>
    initialReconcileChoices(question.conflicts)
  );

  function decisionFor(vendor: string, sourceColumn: string): "keep_master" | "take_map_file" {
    const choice = choices.find((c) => c.vendor === vendor && c.source_column === sourceColumn);
    return choice?.decision ?? "keep_master";
  }

  function handleSubmit() {
    onResolve(buildResolvePayload(question.upload_token, choices).choices);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-heading">Resolve map-file conflicts</CardTitle>
        <p className="text-body text-muted-foreground">
          The map file for <span className="font-medium">{question.vendor}</span> disagrees with the{" "}
          <span className="font-medium">{question.schema_name}</span> master crosswalk on{" "}
          {question.conflicts.length === 1
            ? "one column"
            : `${question.conflicts.length} columns`}
          . Pick which mapping to trust — nothing is saved until you choose.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {question.conflicts.map((conflict) => {
          const controlId = `reconcile-${conflict.vendor}-${conflict.source_column}`;
          return (
            <div
              key={`${conflict.vendor}::${conflict.source_column}`}
              className="flex flex-col gap-1.5 rounded-lg border border-border p-3"
            >
              <Label htmlFor={controlId} className="text-mono-label">
                {conflict.source_column}
                <span className="text-muted-foreground"> · {conflict.vendor}</span>
              </Label>
              <Select
                value={decisionFor(conflict.vendor, conflict.source_column)}
                onValueChange={(value) =>
                  setChoices((prev) =>
                    setChoice(
                      prev,
                      conflict.source_column,
                      conflict.vendor,
                      value as "keep_master" | "take_map_file"
                    )
                  )
                }
              >
                <SelectTrigger id={controlId} className="w-full sm:w-96">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="keep_master">Keep master → {conflict.master_field}</SelectItem>
                  <SelectItem value="take_map_file">
                    Take map file → {conflict.map_file_field}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          );
        })}

        <Button type="button" disabled={submitting} onClick={handleSubmit} className="self-start">
          {submitting && <Loader2 className="size-4 animate-spin" />}
          Apply and Continue
        </Button>
      </CardContent>
    </Card>
  );
}
