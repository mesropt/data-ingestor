import { useState } from "react";
import { Pencil, Trash2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SchemaFieldAliasList } from "@/components/SchemaFieldAliasList";
import { SchemaFieldConstraintsForm } from "@/components/SchemaFieldConstraintsForm";
import { ApiError, deleteSchemaField, updateSchemaField } from "@/lib/api";
import type { CanonicalFieldPayload, FieldPayload, SchemaOut } from "@/lib/types";
import { deleteFieldWarning, fieldSummaryLine } from "@/state/schemaEdit";

interface SchemaFieldRowProps {
  schemaName: string;
  field: CanonicalFieldPayload;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onCollapse: () => void;
  /** Verified-user mirror (D-10-12): gates ONLY Save Field / the delete
   * confirm's destructive action, never expanding the row to view it. */
  verified: boolean;
  /** The server's authoritative post-edit `SchemaOut` -- the Schemas screen
   * re-renders its field list from this, never a locally patched copy. */
  onSchemaUpdated: (schema: SchemaOut) => void;
}

function consequenceMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.detail && typeof err.detail === "object") return JSON.stringify(err.detail);
  }
  return fallback;
}

/**
 * One canonical field: a collapsed summary row (D-10-10) that expands
 * in-place into its editable constraints + vendor aliases -- one row open at
 * a time (10-UI-SPEC Discretion §1), owned by the parent `Schemas` screen via
 * `isExpanded`/`onToggleExpand`. A plain conditional-JSX accordion, no new
 * shadcn primitive (`Collapsible`/`Accordion` is not installed and stays
 * that way, per Registry Safety).
 */
export function SchemaFieldRow({
  schemaName,
  field,
  isExpanded,
  onToggleExpand,
  onCollapse,
  verified,
  onSchemaUpdated,
}: SchemaFieldRowProps) {
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  async function handleSave(payload: FieldPayload) {
    setSaving(true);
    setSaveError(null);
    try {
      const schema = await updateSchemaField(schemaName, field.name, payload);
      onSchemaUpdated(schema);
      onCollapse();
    } catch (err) {
      setSaveError(consequenceMessage(err, "Couldn't save this field. Nothing was changed."));
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      const schema = await deleteSchemaField(schemaName, field.name);
      onSchemaUpdated(schema);
      setConfirmDeleteOpen(false);
      onCollapse();
    } catch (err) {
      setDeleteError(consequenceMessage(err, "Couldn't delete this field. Nothing was changed."));
    } finally {
      setDeleting(false);
    }
  }

  const deleteActionButton = (
    <AlertDialogAction variant="destructive" disabled={deleting || !verified} onClick={handleConfirmDelete}>
      {deleting ? "Deleting…" : "Delete"}
    </AlertDialogAction>
  );

  return (
    <div className="flex flex-col gap-2">
      {deleteError && (
        <Alert variant="destructive">
          <AlertDescription>{deleteError}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate text-body font-semibold text-foreground">{field.name}</span>
              <span className="text-mono-label text-muted-foreground">{fieldSummaryLine(field)}</span>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Edit ${field.name}`}
                onClick={onToggleExpand}
              >
                <Pencil className="size-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Delete field ${field.name}`}
                className="text-destructive-text hover:bg-destructive-bg"
                onClick={() => setConfirmDeleteOpen(true)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </div>

          {isExpanded && (
            <div className="flex flex-col gap-6 border-t border-border pt-4">
              <SchemaFieldConstraintsForm
                formId={`schema-field-${field.name}`}
                field={field}
                saveDisabled={!verified}
                saveDisabledReason={verified ? null : "Verify your email to save this field."}
                saving={saving}
                error={saveError}
                onSave={handleSave}
                onRequestDelete={() => setConfirmDeleteOpen(true)}
                onCancel={onCollapse}
              />
              <SchemaFieldAliasList
                schemaName={schemaName}
                fieldName={field.name}
                aliases={field.aliases}
                verified={verified}
                onSchemaUpdated={onSchemaUpdated}
              />
            </div>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete field</AlertDialogTitle>
            <AlertDialogDescription>{deleteFieldWarning(field)}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {verified ? (
              deleteActionButton
            ) : (
              <Tooltip>
                <TooltipTrigger render={deleteActionButton} />
                <TooltipContent>Verify your email to delete this field.</TooltipContent>
              </Tooltip>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
