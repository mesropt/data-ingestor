import { useEffect, useReducer, useRef, useState } from "react";
import { Download, LayoutGrid, Loader2, Pencil, Plus, Upload as UploadIcon } from "lucide-react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SchemaFieldConstraintsForm } from "@/components/SchemaFieldConstraintsForm";
import { SchemaFieldRow } from "@/components/SchemaFieldRow";
import {
  ApiError,
  addSchemaField,
  getMasterMap,
  importMasterMap,
  listSchemas,
  masterMapDownloadUrl,
  promoteSchema,
  renameSchema,
} from "@/lib/api";
import type { CanonicalFieldPayload, FieldPayload, MasterMapEnvelope, SchemaOut } from "@/lib/types";
import { canAddField } from "@/state/schemaEdit";
import { initialSchemaState, schemaReducer } from "@/state/schema";

type SchemaBodyStatus =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "loaded"; fields: CanonicalFieldPayload[] };

/** A blank sentinel `CanonicalFieldPayload` -- seeds the "Add Field" form's
 * `SchemaFieldConstraintsForm` before the field exists server-side. Never
 * rendered as a real row; it only supplies `fromCanonicalField`'s defaults. */
const BLANK_FIELD: CanonicalFieldPayload = {
  name: "",
  description: null,
  type: null,
  allowed_values: null,
  unit: null,
  required: true,
  min: null,
  max: null,
  date_format: null,
  aliases: [],
};

function consequenceMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (err.detail && typeof err.detail === "object") return JSON.stringify(err.detail);
  }
  return fallback;
}

interface SchemasProps {
  /** Verified-user mirror (D-10-12): every mutating control on this page is
   * disabled with the existing tooltip pattern when `false`. `Schemas` only
   * ever renders while signed in (the app-wide `SignInRequiredGate` covers
   * the signed-out case, 10-UI-SPEC Discretion §3) -- this is the ONE
   * remaining auth dimension the screen itself needs. */
  verified: boolean;
}

/**
 * The Schemas screen (D-10-09/10/11, INGEST-05) -- replaces Define Fields and
 * Registry. One table per Schema, one row per canonical field, carrying both
 * the field's constraints (`SchemaFieldConstraintsForm`) and its vendor
 * aliases with provenance (`SchemaFieldAliasList`), both editable through
 * Plan 10-04's explicit edit endpoints.
 *
 * Carries Registry.tsx's own idioms forward verbatim: the Schema selector's
 * `latestRequestRef` race guard (a schema-switch race where a slower
 * response can land after a faster one), the `EmptyCard` pattern, and the
 * 3-`Skeleton` loading state -- this screen is Registry grown up, not a
 * rewrite. After every successful edit it re-renders from the server's
 * authoritative `SchemaOut`, never a locally patched copy.
 */
export function Schemas({ verified }: SchemasProps) {
  const [schemaState, schemaDispatch] = useReducer(schemaReducer, initialSchemaState);
  const [status, setStatus] = useState<SchemaBodyStatus>({ kind: "idle" });
  // Guards against a schema-switch race: selecting A then quickly B can let
  // A's slower response land after B's, clobbering the crosswalk currently
  // shown (carried forward from Registry.tsx verbatim).
  const latestRequestRef = useRef<string | null>(null);

  const [expandedFieldName, setExpandedFieldName] = useState<string | null>(null);
  const [addingField, setAddingField] = useState(false);
  const [addFieldSaving, setAddFieldSaving] = useState(false);
  const [addFieldError, setAddFieldError] = useState<string | null>(null);

  const [newSchemaName, setNewSchemaName] = useState("");
  const [creatingSchema, setCreatingSchema] = useState(false);

  // The rename affordance (quick 260712): renaming the SELECTED Schema is a
  // different act from creating a new one, so it gets its own explicit
  // inline form (conditional JSX + local state, the same idiom the
  // add-field form below uses) -- never a second meaning smuggled into the
  // "Create New Schema" input.
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);

  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    reloadSchemas();
  }, []);

  function reloadSchemas() {
    listSchemas()
      .then((schemas) => schemaDispatch({ type: "LOADED", schemas }))
      .catch(() => {
        // A schema-list failure just leaves the selector empty; the
        // first-run empty state below covers it (mirrors Registry.tsx).
      });
  }

  function loadSchemaFields(name: string) {
    latestRequestRef.current = name;
    setStatus({ kind: "loading" });
    getMasterMap(name)
      .then((envelope: MasterMapEnvelope) => {
        if (latestRequestRef.current !== name) return;
        setStatus({ kind: "loaded", fields: envelope.fields });
      })
      .catch(() => {
        if (latestRequestRef.current !== name) return;
        setStatus({ kind: "error" });
      });
  }

  function handleSelect(name: string) {
    schemaDispatch({ type: "SELECT", name });
    setExpandedFieldName(null);
    setAddingField(false);
    setAddFieldError(null);
    setRenaming(false);
    loadSchemaFields(name);
  }

  function handleSchemaUpdated(schema: SchemaOut) {
    setStatus({ kind: "loaded", fields: schema.fields });
  }

  async function handleCreateSchema() {
    const name = newSchemaName.trim();
    if (!name) {
      toast.error("Name the Schema before creating it.");
      return;
    }
    setCreatingSchema(true);
    try {
      await promoteSchema(name, { name: null, fields: [] });
      toast.success(`Created "${name}".`);
      setNewSchemaName("");
      reloadSchemas();
      handleSelect(name);
    } catch (err) {
      toast.error(consequenceMessage(err, "Couldn't create this Schema. Nothing was changed."));
    } finally {
      setCreatingSchema(false);
    }
  }

  function startRename() {
    if (!schemaState.selected) return;
    setRenameValue(schemaState.selected);
    setRenaming(true);
  }

  async function handleRenameSchema() {
    if (!schemaState.selected) return;
    const from = schemaState.selected;
    const to = renameValue.trim();
    if (!to) {
      toast.error("Name the Schema before renaming it. Nothing was changed.");
      return;
    }
    if (to === from) {
      setRenaming(false);
      return;
    }
    setRenameSaving(true);
    try {
      await renameSchema(from, to);
      toast.success(`Renamed "${from}" to "${to}". Its fields, aliases, and learned profiles are untouched.`);
      // Follow the selection to the new name immediately (the reducer's
      // RENAMED patch), then reload the authoritative list from the server.
      schemaDispatch({ type: "RENAMED", from, to });
      setRenaming(false);
      reloadSchemas();
    } catch (err) {
      toast.error(consequenceMessage(err, "Couldn't rename this Schema. Nothing was changed."));
    } finally {
      setRenameSaving(false);
    }
  }

  async function handleAddField(payload: FieldPayload) {
    if (!schemaState.selected) return;
    setAddFieldSaving(true);
    setAddFieldError(null);
    try {
      const schema = await addSchemaField(schemaState.selected, payload);
      handleSchemaUpdated(schema);
      setAddingField(false);
    } catch (err) {
      setAddFieldError(consequenceMessage(err, "Couldn't add this field. Nothing was changed."));
    } finally {
      setAddFieldSaving(false);
    }
  }

  async function handleImportFile(file: File) {
    if (!schemaState.selected) {
      toast.error("Select a Schema to import into first.");
      return;
    }
    setImporting(true);
    try {
      const text = await file.text();
      const envelope = JSON.parse(text) as MasterMapEnvelope;
      const schema = await importMasterMap(schemaState.selected, envelope);
      toast.success(`Augmented "${schemaState.selected}" from ${file.name}.`);
      handleSchemaUpdated(schema);
    } catch (err) {
      if (err instanceof SyntaxError) {
        toast.error("That file isn't valid JSON. Nothing was imported.");
      } else {
        toast.error(consequenceMessage(err, "Import failed. Nothing was imported."));
      }
    } finally {
      setImporting(false);
    }
  }

  function onFileChosen(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset the input so choosing the same file twice still fires onChange.
    event.target.value = "";
    if (file) {
      void handleImportFile(file);
    }
  }

  const hasSchemas = schemaState.schemas.length > 0;
  const fields = status.kind === "loaded" ? status.fields : [];
  const canAdd =
    schemaState.selected !== null &&
    canAddField({ id: "", name: schemaState.selected, created_by: null, fields });

  const createSchemaButton = (
    <Button type="button" disabled={creatingSchema} onClick={handleCreateSchema}>
      {creatingSchema && <Loader2 className="size-4 animate-spin" />}
      Create Schema
    </Button>
  );

  const renameSchemaButton = (
    <Button
      type="button"
      variant="outline"
      disabled={!verified || !schemaState.selected || renaming}
      onClick={startRename}
    >
      <Pencil className="size-4" />
      Rename Schema
    </Button>
  );

  const importButton = (
    <Button
      type="button"
      variant="outline"
      disabled={importing || !schemaState.selected}
      onClick={() => fileInputRef.current?.click()}
    >
      {importing ? <Loader2 className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}
      Import master map
    </Button>
  );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 py-4">
      <header className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-display">
          <LayoutGrid className="size-6 text-muted-foreground" aria-hidden />
          Schemas
        </h1>
        <p className="text-body text-muted-foreground">
          The canonical fields future uploads map onto, and every vendor's alias for each — edit both here.
        </p>
      </header>

      <div className="flex flex-col gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="schemas-select">Schema</Label>
            <Select
              value={schemaState.selected ?? undefined}
              onValueChange={(value) => handleSelect(String(value))}
              disabled={!hasSchemas}
            >
              <SelectTrigger id="schemas-select" className="w-64">
                <SelectValue placeholder={hasSchemas ? "Choose a Schema…" : "No schemas yet."} />
              </SelectTrigger>
              <SelectContent>
                {schemaState.schemas.map((schema) => (
                  <SelectItem key={schema.id} value={schema.name}>
                    {schema.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            {/* Unambiguously a CREATION control (quick 260712): this input
             * never touches the Schema selected on the left -- renaming that
             * one is the separate "Rename Schema" affordance below. */}
            <Label htmlFor="schemas-new-name">Create New Schema</Label>
            <Input
              id="schemas-new-name"
              value={newSchemaName}
              placeholder="Name for a brand-new Schema, e.g. assay-potency"
              className="w-72"
              onChange={(event) => setNewSchemaName(event.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {verified ? (
            createSchemaButton
          ) : (
            <Tooltip>
              <TooltipTrigger render={createSchemaButton} />
              <TooltipContent>Verify your email to create a Schema.</TooltipContent>
            </Tooltip>
          )}

          {!verified ? (
            <Tooltip>
              <TooltipTrigger render={renameSchemaButton} />
              <TooltipContent>Verify your email to rename a Schema.</TooltipContent>
            </Tooltip>
          ) : !schemaState.selected ? (
            <Tooltip>
              <TooltipTrigger render={renameSchemaButton} />
              <TooltipContent>Select a Schema to rename it.</TooltipContent>
            </Tooltip>
          ) : (
            renameSchemaButton
          )}

          {schemaState.selected ? (
            <a
              href={masterMapDownloadUrl(schemaState.selected)}
              download
              className={buttonVariants({ variant: "outline" })}
            >
              <Download className="size-4" />
              Download master map
            </a>
          ) : (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button type="button" variant="outline" disabled>
                    <Download className="size-4" />
                    Download master map
                  </Button>
                }
              />
              <TooltipContent>Select a Schema to download its master map.</TooltipContent>
            </Tooltip>
          )}

          {!verified ? (
            <Tooltip>
              <TooltipTrigger render={importButton} />
              <TooltipContent>Verify your email to import a master map.</TooltipContent>
            </Tooltip>
          ) : !schemaState.selected ? (
            <Tooltip>
              <TooltipTrigger render={importButton} />
              <TooltipContent>Select a Schema to import into first.</TooltipContent>
            </Tooltip>
          ) : (
            importButton
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={onFileChosen}
          />
        </div>

        {renaming && schemaState.selected && (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="schemas-rename-name">New name for "{schemaState.selected}"</Label>
              <Input
                id="schemas-rename-name"
                value={renameValue}
                className="w-72"
                onChange={(event) => setRenameValue(event.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" disabled={renameSaving} onClick={handleRenameSchema}>
                {renameSaving && <Loader2 className="size-4 animate-spin" />}
                Rename Schema
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={renameSaving}
                onClick={() => setRenaming(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      <SchemaFieldsSection
        hasSchemas={hasSchemas}
        selected={schemaState.selected}
        status={status}
        verified={verified}
        expandedFieldName={expandedFieldName}
        onToggleExpand={(name) => setExpandedFieldName((current) => (current === name ? null : name))}
        onCollapse={() => setExpandedFieldName(null)}
        onSchemaUpdated={handleSchemaUpdated}
        onRetry={() => schemaState.selected && loadSchemaFields(schemaState.selected)}
        canAdd={canAdd}
        addingField={addingField}
        onStartAddField={() => setAddingField(true)}
        onCancelAddField={() => {
          setAddingField(false);
          setAddFieldError(null);
        }}
        addFieldSaving={addFieldSaving}
        addFieldError={addFieldError}
        onSaveNewField={handleAddField}
      />
    </div>
  );
}

interface SchemaFieldsSectionProps {
  hasSchemas: boolean;
  selected: string | null;
  status: SchemaBodyStatus;
  verified: boolean;
  expandedFieldName: string | null;
  onToggleExpand: (name: string) => void;
  onCollapse: () => void;
  onSchemaUpdated: (schema: SchemaOut) => void;
  onRetry: () => void;
  canAdd: boolean;
  addingField: boolean;
  onStartAddField: () => void;
  onCancelAddField: () => void;
  addFieldSaving: boolean;
  addFieldError: string | null;
  onSaveNewField: (payload: FieldPayload) => void;
}

/** The main region below the toolbar -- resolves every state (no schemas,
 * nothing selected, loading, error, empty Schema, populated field list) to a
 * visible, calm surface, mirroring `Registry.tsx`'s own `RegistryBody`. */
function SchemaFieldsSection({
  hasSchemas,
  selected,
  status,
  verified,
  expandedFieldName,
  onToggleExpand,
  onCollapse,
  onSchemaUpdated,
  onRetry,
  canAdd,
  addingField,
  onStartAddField,
  onCancelAddField,
  addFieldSaving,
  addFieldError,
  onSaveNewField,
}: SchemaFieldsSectionProps) {
  if (!hasSchemas) {
    return (
      <EmptyCard
        title="No schemas yet."
        hint="Create a Schema to define the target fields future uploads map onto."
      />
    );
  }

  if (!selected || status.kind === "idle") {
    return (
      <EmptyCard
        title="Choose a Schema"
        hint="Pick a Schema above to see its canonical fields and every vendor alias mapped into it."
      />
    );
  }

  if (status.kind === "loading") {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (status.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn't load this Schema's fields.</CardTitle>
          <CardDescription>
            The Schemas page couldn't reach the server for this Schema. Nothing else on this page is
            affected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  const addFieldButton = (
    <Button type="button" variant="outline" disabled={!canAdd} onClick={onStartAddField}>
      <Plus className="size-4" />
      Add Field
    </Button>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        {canAdd ? (
          addFieldButton
        ) : (
          <Tooltip>
            <TooltipTrigger render={addFieldButton} />
            <TooltipContent>A Schema is capped at 50 fields.</TooltipContent>
          </Tooltip>
        )}
      </div>

      {addingField && (
        <Card>
          <CardContent>
            <SchemaFieldConstraintsForm
              formId="schema-new-field"
              field={BLANK_FIELD}
              saveDisabled={!verified}
              saveDisabledReason={verified ? null : "Verify your email to add a field."}
              saving={addFieldSaving}
              error={addFieldError}
              onSave={onSaveNewField}
              onRequestDelete={onCancelAddField}
              onCancel={onCancelAddField}
            />
          </CardContent>
        </Card>
      )}

      {status.fields.length === 0 && !addingField ? (
        <EmptyCard
          title="No fields in this Schema yet."
          hint="Add your first field — give it a name, then optionally set a type, allowed values, unit, or date format."
          cta={{ label: "Add Field", onClick: onStartAddField }}
        />
      ) : (
        status.fields.map((field) => (
          <SchemaFieldRow
            key={field.name}
            schemaName={selected}
            field={field}
            isExpanded={expandedFieldName === field.name}
            onToggleExpand={() => onToggleExpand(field.name)}
            onCollapse={onCollapse}
            verified={verified}
            onSchemaUpdated={onSchemaUpdated}
          />
        ))
      )}
    </div>
  );
}

/** A calm empty/first-run card carrying a one-line consequence-free hint,
 * with an optional CTA (mirrors `Registry.tsx`'s own `EmptyCard`). */
function EmptyCard({
  title,
  hint,
  cta,
}: {
  title: string;
  hint: string;
  cta?: { label: string; onClick: () => void };
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{hint}</CardDescription>
      </CardHeader>
      {cta && (
        <CardContent>
          <Button type="button" onClick={cta.onClick}>
            {cta.label}
          </Button>
        </CardContent>
      )}
    </Card>
  );
}
