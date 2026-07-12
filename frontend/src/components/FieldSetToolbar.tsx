import { Loader2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { FieldSetTemplate } from "@/lib/types";

interface FieldSetToolbarProps {
  name: string;
  onNameChange: (name: string) => void;
  templates: FieldSetTemplate[];
  onLoadTemplate: (templateId: string) => void;
  onAddField: () => void;
  addFieldDisabled: boolean;
  onSave: () => void;
  saving: boolean;
  disabled: boolean;
}

/**
 * Add/save/load controls for a field set (UI-01 Screen 1, pinned at the
 * top). "Save Field Set" is the Copywriting Contract's verbatim Primary
 * CTA for this screen; the field-cap tooltip text is verbatim too.
 */
export function FieldSetToolbar({
  name,
  onNameChange,
  templates,
  onLoadTemplate,
  onAddField,
  addFieldDisabled,
  onSave,
  saving,
  disabled,
}: FieldSetToolbarProps) {
  const addFieldButton = (
    <Button type="button" variant="outline" disabled={addFieldDisabled || disabled} onClick={onAddField}>
      <Plus className="size-4" />
      Add Field
    </Button>
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex flex-1 flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="field-set-load">Load a saved field set</Label>
          <Select
            value={undefined}
            onValueChange={(value) => onLoadTemplate(String(value))}
            disabled={disabled || templates.length === 0}
          >
            <SelectTrigger id="field-set-load" className="w-56">
              <SelectValue placeholder="Choose a template…" />
            </SelectTrigger>
            <SelectContent>
              {templates.map((template) => (
                <SelectItem key={template.id} value={template.id}>
                  {template.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="field-set-name">Field set name</Label>
          <Input
            id="field-set-name"
            value={name}
            placeholder="e.g. novascreen-v1"
            disabled={disabled}
            className="w-56"
            onChange={(event) => onNameChange(event.target.value)}
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        {addFieldDisabled ? (
          <Tooltip>
            <TooltipTrigger render={addFieldButton} />
            <TooltipContent>Field sets are capped at 50 fields.</TooltipContent>
          </Tooltip>
        ) : (
          addFieldButton
        )}
        <Button type="button" disabled={disabled || saving} onClick={onSave}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save Field Set
        </Button>
      </div>
    </div>
  );
}
