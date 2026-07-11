import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FieldSetTemplate } from "@/lib/types";

interface FieldSetPickerProps {
  templates: FieldSetTemplate[];
  value: string | null;
  onChange: (templateId: string) => void;
  disabled?: boolean;
}

/**
 * Choose which saved field set (UI-01 template, D-03) this upload maps
 * onto (UI-02 Screen 2, top control). The chosen template's id is resolved
 * to a `FieldSetPayload` by the Upload screen before calling
 * `api.uploadFile` -- this component only ever surfaces the choice.
 */
export function FieldSetPicker({ templates, value, onChange, disabled }: FieldSetPickerProps) {
  const empty = templates.length === 0;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="upload-field-set">Field set</Label>
      <Select
        value={value ?? undefined}
        onValueChange={(next) => onChange(String(next))}
        disabled={disabled || empty}
      >
        <SelectTrigger id="upload-field-set" className="w-full">
          <SelectValue placeholder={empty ? "No saved field sets yet — define one first" : "Choose a field set…"} />
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
  );
}
