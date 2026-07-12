import { useEffect, useState } from "react";
import { FileWarning } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FieldEditorRow } from "@/components/FieldEditorRow";
import { FieldSetToolbar } from "@/components/FieldSetToolbar";
import { ApiError, getFieldSet, listFieldSets, saveFieldSet } from "@/lib/api";
import type { FieldSetPayload, FieldSetTemplate } from "@/lib/types";
import {
  MAX_FIELDS,
  addField,
  createEmptyFieldSetDraft,
  editField,
  removeField,
  toFieldSetPayload,
  type DraftField,
  type FieldSetDraftState,
} from "@/state/fieldSet";

let _draftFieldId = 0;
function nextDraftFieldId(): string {
  _draftFieldId += 1;
  return `loaded-field-${_draftFieldId}`;
}

/** The inverse of `toFieldSetPayload` -- rebuilds editable draft state from
 * a saved template's `FieldSet.to_dict()` body (`GET /api/field-sets/{id}`).
 * Screen-local: nothing outside DefineFields ever needs to load a template
 * back into the editor, so this stays out of the tested pure-logic module
 * (state/fieldSet.ts) rather than growing that module's public surface for
 * a single caller. */
function fieldSetPayloadToDraft(name: string, payload: FieldSetPayload): FieldSetDraftState {
  const fields: DraftField[] = payload.fields.map((field) => ({
    id: nextDraftFieldId(),
    name: field.name,
    description: field.description ?? "",
    type: field.type ?? "none",
    allowedValues: field.allowed_values ?? [],
    unit: field.unit ?? "",
    required: field.required,
    min: field.min,
    max: field.max,
    dateFormat: field.date_format ?? "",
  }));
  return { name, fields };
}

function consequenceMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (error.detail && typeof error.detail === "object") return JSON.stringify(error.detail);
  }
  return fallback;
}

type ScreenError = { context: "load-templates" | "load-template" | "save"; message: string };

/**
 * Screen 1 (UI-01): create/edit a field set and save/load it as a named
 * template against the real `/api/field-sets` endpoints (Plan 03). The
 * `state/fieldSet.ts` reducer (Task 2, vitest-covered) is this screen's
 * single source of state -- every control here just calls one of its pure
 * functions and re-renders.
 */
export function DefineFields() {
  const [draft, setDraft] = useState<FieldSetDraftState>(createEmptyFieldSetDraft);
  const [templates, setTemplates] = useState<FieldSetTemplate[]>([]);
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ScreenError | null>(null);

  useEffect(() => {
    listFieldSets()
      .then(setTemplates)
      .catch((err: unknown) => {
        setError({
          context: "load-templates",
          message: consequenceMessage(err, "Couldn't load saved field sets right now."),
        });
      });
  }, []);

  async function handleLoadTemplate(templateId: string) {
    const template = templates.find((t) => t.id === templateId);
    if (!template) return;
    setLoadingTemplate(true);
    setError(null);
    try {
      const fieldSet = await getFieldSet(templateId);
      setDraft(fieldSetPayloadToDraft(template.name, fieldSet));
    } catch (err) {
      setError({
        context: "load-template",
        message: consequenceMessage(err, "This template couldn't be loaded. Nothing here was changed."),
      });
    } finally {
      setLoadingTemplate(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = toFieldSetPayload(draft);
      const { id } = await saveFieldSet(draft.name, payload);
      const savedTemplates = await listFieldSets();
      setTemplates(savedTemplates);
      const saved = savedTemplates.find((t) => t.id === id);
      if (saved) {
        setDraft((current) => ({ ...current, name: saved.name }));
      }
    } catch (err) {
      setError({
        context: "save",
        message: consequenceMessage(err, "This field set couldn't be saved. Nothing was changed."),
      });
    } finally {
      setSaving(false);
    }
  }

  const disabled = loadingTemplate;
  const atCap = draft.fields.length >= MAX_FIELDS;

  return (
    <div className="mx-auto flex max-w-[840px] flex-col gap-8">
      <h1 className="text-display">Define Fields</h1>

      {error && (
        <Alert variant="destructive">
          <FileWarning />
          <AlertTitle>
            {error.context === "save" ? "Couldn't save this field set" : "Couldn't load this field set"}
          </AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      <FieldSetToolbar
        name={draft.name}
        onNameChange={(name) => setDraft((current) => ({ ...current, name }))}
        templates={templates}
        onLoadTemplate={handleLoadTemplate}
        onAddField={() => setDraft((current) => addField(current))}
        addFieldDisabled={atCap}
        onSave={handleSave}
        saving={saving}
        disabled={disabled}
      />

      {loadingTemplate ? (
        <div className="flex flex-col gap-4" aria-label="Loading field set">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : draft.fields.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border py-16 text-center">
          <FileWarning className="size-8 text-muted-foreground" />
          <h2 className="text-heading">No fields defined yet.</h2>
          <p className="max-w-md text-body text-muted-foreground">
            Add your first field to start building a field set — give it a name, then optionally
            set a type, allowed values, or unit.
          </p>
          <Button type="button" onClick={() => setDraft((current) => addField(current))}>
            Add Field
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {draft.fields.map((field) => (
            <FieldEditorRow
              key={field.id}
              field={field}
              onChange={(patch) => setDraft((current) => editField(current, field.id, patch))}
              onDelete={() => setDraft((current) => removeField(current, field.id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
