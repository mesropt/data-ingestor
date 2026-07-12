import { useState } from "react";
import { Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { MAX_NAME_LENGTH, type DraftField, type DraftFieldType } from "@/state/fieldSet";

const TYPE_OPTIONS: { value: DraftFieldType; label: string }[] = [
  { value: "none", label: "None" },
  { value: "number", label: "Number" },
  { value: "integer", label: "Integer" },
  { value: "date", label: "Date" },
  { value: "text", label: "Text" },
];

interface FieldEditorRowProps {
  field: DraftField;
  onChange: (patch: Partial<Omit<DraftField, "id">>) => void;
  onDelete: () => void;
}

/**
 * One field's full declaration (UI-01) -- maps 1:1 to
 * `fields/models.py::Field`. Every control is a UX convenience over the
 * server's authoritative validation (`fields/loader.py`); nothing here
 * blocks a Save, it only guides the curator toward a valid one.
 */
export function FieldEditorRow({ field, onChange, onDelete }: FieldEditorRowProps) {
  const [draftAllowedValue, setDraftAllowedValue] = useState("");
  const isNumeric = field.type === "number" || field.type === "integer";
  const isDate = field.type === "date";

  function commitAllowedValue() {
    const value = draftAllowedValue.trim();
    if (value.length === 0) return;
    if (field.allowedValues.includes(value)) {
      setDraftAllowedValue("");
      return;
    }
    onChange({ allowedValues: [...field.allowedValues, value] });
    setDraftAllowedValue("");
  }

  function removeAllowedValue(value: string) {
    onChange({ allowedValues: field.allowedValues.filter((v) => v !== value) });
  }

  return (
    <Card>
      <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${field.id}-name`}>Name</Label>
          <Input
            id={`${field.id}-name`}
            value={field.name}
            maxLength={MAX_NAME_LENGTH}
            placeholder="e.g. compound_id"
            onChange={(event) => onChange({ name: event.target.value })}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${field.id}-description`}>Description</Label>
          <Input
            id={`${field.id}-description`}
            value={field.description}
            placeholder="Optional"
            onChange={(event) => onChange({ description: event.target.value })}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${field.id}-type`}>Type</Label>
          <Select
            value={field.type}
            onValueChange={(value) => onChange({ type: value as DraftFieldType })}
          >
            <SelectTrigger id={`${field.id}-type`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${field.id}-unit`}>Unit</Label>
          <Input
            id={`${field.id}-unit`}
            value={field.unit}
            placeholder="Optional, e.g. nM"
            onChange={(event) => onChange({ unit: event.target.value })}
          />
        </div>

        {isNumeric && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`${field.id}-min`}>Min</Label>
              <Input
                id={`${field.id}-min`}
                type="number"
                value={field.min ?? ""}
                onChange={(event) =>
                  onChange({ min: event.target.value === "" ? null : Number(event.target.value) })
                }
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`${field.id}-max`}>Max</Label>
              <Input
                id={`${field.id}-max`}
                type="number"
                value={field.max ?? ""}
                onChange={(event) =>
                  onChange({ max: event.target.value === "" ? null : Number(event.target.value) })
                }
              />
            </div>
          </>
        )}

        {isDate && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${field.id}-date-format`}>Date format</Label>
            <Input
              id={`${field.id}-date-format`}
              value={field.dateFormat}
              placeholder="e.g. %Y-%m-%d"
              aria-describedby={`${field.id}-date-format-hint`}
              onChange={(event) => onChange({ dateFormat: event.target.value })}
            />
            <p id={`${field.id}-date-format-hint`} className="text-mono-label text-muted-foreground">
              Required to auto-clear a date field. Leave it blank and every row
              stays flagged for manual confirmation — the tool never guesses a
              date format.
            </p>
          </div>
        )}

        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor={`${field.id}-allowed-values`}>Allowed values</Label>
          <div className="flex flex-wrap items-center gap-2">
            {field.allowedValues.map((value) => (
              <Badge key={value} variant="secondary" className="gap-1">
                <span className="text-mono-label">{value}</span>
                <button
                  type="button"
                  aria-label={`Remove allowed value ${value}`}
                  onClick={() => removeAllowedValue(value)}
                >
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
            <Input
              id={`${field.id}-allowed-values`}
              value={draftAllowedValue}
              placeholder="Type a value, press Enter"
              className="w-40"
              onChange={(event) => setDraftAllowedValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === ",") {
                  event.preventDefault();
                  commitAllowedValue();
                }
              }}
              onBlur={commitAllowedValue}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 sm:col-span-2">
          <div className="flex items-center gap-2">
            <Switch
              id={`${field.id}-required`}
              checked={field.required}
              onCheckedChange={(checked) => onChange({ required: checked })}
            />
            <Label htmlFor={`${field.id}-required`}>Required</Label>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Delete field ${field.name || "(unnamed)"}`}
            className="text-destructive-text hover:bg-destructive-bg"
            onClick={onDelete}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
