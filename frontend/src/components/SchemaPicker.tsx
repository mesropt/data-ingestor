import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, listSchemas } from "@/lib/api";
import type { SchemaSummary } from "@/lib/types";

interface SchemaPickerProps {
  value: string | null;
  onChange: (schemaName: string) => void;
  disabled?: boolean;
}

/**
 * Choose which governed Schema (D-10-02) this upload maps onto -- the
 * FIRST of Upload's exactly three controls (D-10-01), replacing
 * `FieldSetPicker` 1:1 in position. The chosen Schema's own canonical
 * fields ARE the target fields; this component never surfaces the
 * internal `FieldSet` concept in any visible text.
 *
 * Fresh and un-auto-selecting by design (10-UI-SPEC Discretion §5, fully
 * reverting quick task 260712-e0e): no last-used memory, no
 * pick-if-only-one-exists default -- the curator always picks explicitly.
 */
export function SchemaPicker({ value, onChange, disabled }: SchemaPickerProps) {
  const [schemas, setSchemas] = useState<SchemaSummary[]>([]);

  useEffect(() => {
    listSchemas()
      .then(setSchemas)
      .catch((err: unknown) => {
        const fallback = "Couldn't load Schemas right now.";
        toast.error(err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback);
      });
  }, []);

  const empty = schemas.length === 0;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="upload-schema">Schema</Label>
      <Select
        value={value ?? undefined}
        onValueChange={(next) => onChange(String(next))}
        disabled={disabled || empty}
      >
        <SelectTrigger id="upload-schema" className="w-full">
          <SelectValue
            placeholder={empty ? "No Schemas yet — create one on the Schemas page first." : "Choose a Schema…"}
          />
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
  );
}
