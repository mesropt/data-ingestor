import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { FieldEditorRow } from "@/components/FieldEditorRow";
import type { CanonicalFieldPayload, FieldPayload } from "@/lib/types";
import type { DraftField } from "@/state/fieldSet";
import { fromCanonicalField, toFieldPayload, type SchemaFieldDraft } from "@/state/schemaEdit";

interface SchemaFieldConstraintsFormProps {
  /** A stable identity for this form's input ids/keys -- the field's
   * ORIGINAL name at the time the row opened, never re-derived from the
   * in-progress (possibly renamed) draft, so labels/ids stay stable while
   * editing (`"schema-new-field"` for the not-yet-created "Add Field" form). */
  formId: string;
  /** The last-saved `CanonicalFieldPayload` this form seeds from -- a blank
   * sentinel field for the "Add Field" (not-yet-created) case. */
  field: CanonicalFieldPayload;
  /** Verified-user mirror (D-10-12): disables ONLY the "Save Field" submit,
   * never the inputs themselves -- viewing/editing is unaffected by
   * verification (10-UI-SPEC Screens & States §1), only the mutation is.
   * `saveDisabledReason` is the tooltip copy, present only while disabled
   * for that reason (never shown while merely `saving`). */
  saveDisabled: boolean;
  saveDisabledReason: string | null;
  saving: boolean;
  error: string | null;
  onSave: (payload: FieldPayload) => void;
  /** `FieldEditorRow`'s own built-in delete affordance -- for an existing
   * field this opens the SAME destructive-confirm `SchemaFieldRow` owns for
   * its collapsed-row trash icon (two entry points, one action); for the
   * not-yet-created "Add Field" form this just cancels/dismisses it (nothing
   * exists yet to destructively confirm). */
  onRequestDelete: () => void;
  onCancel: () => void;
}

/**
 * The editable-constraints half of an expanded `SchemaFieldRow` (D-10-10,
 * D-10-11) -- `CanonicalField`'s constraints ARE `Field`'s constraints, so
 * this reuses `FieldEditorRow`'s exact grid (Name, Description, Type, Unit,
 * Min/Max, Date format, Allowed values, Required) verbatim rather than
 * re-deriving a second layout. Local draft state lives here (not lifted to
 * the parent) so a failed save preserves every in-progress edit untouched
 * (10-UI-SPEC error state contract).
 */
export function SchemaFieldConstraintsForm({
  formId,
  field,
  saveDisabled,
  saveDisabledReason,
  saving,
  error,
  onSave,
  onRequestDelete,
  onCancel,
}: SchemaFieldConstraintsFormProps) {
  const [draft, setDraft] = useState<SchemaFieldDraft>(() => fromCanonicalField(field));

  function handleChange(patch: Partial<Omit<DraftField, "id">>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function handleCancel() {
    setDraft(fromCanonicalField(field));
    onCancel();
  }

  const draftField: DraftField = { id: formId, ...draft };

  const saveButton = (
    <Button type="button" disabled={saving || saveDisabled} onClick={() => onSave(toFieldPayload(draft))}>
      {saving && <Loader2 className="size-4 animate-spin" />}
      Save Field
    </Button>
  );

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <FieldEditorRow field={draftField} onChange={handleChange} onDelete={onRequestDelete} />

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="outline" disabled={saving} onClick={handleCancel}>
          Cancel
        </Button>
        {saveDisabled && saveDisabledReason ? (
          <Tooltip>
            <TooltipTrigger render={saveButton} />
            <TooltipContent>{saveDisabledReason}</TooltipContent>
          </Tooltip>
        ) : (
          saveButton
        )}
      </div>
    </div>
  );
}
