import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

interface HeadersOnlyToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

/**
 * P2 privacy toggle (UI-02) -- sent as `/api/upload`'s `headers_only` form
 * field. Copy is verbatim from 04-UI-SPEC.md's Copywriting Contract; this
 * is the same toggle state `StructuralHintPanel`'s evidence preview must
 * honor (P2/CR-01) so the preview and the request never disagree.
 */
export function HeadersOnlyToggle({ checked, onCheckedChange, disabled }: HeadersOnlyToggleProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex flex-col gap-1">
        <Label htmlFor="headers-only-toggle">Headers only</Label>
        <p className="text-body text-muted-foreground">
          Claude sees column names only — no cell values leave this server. Turn off to let Claude
          use example values for ambiguous columns too.
        </p>
      </div>
      <Switch
        id="headers-only-toggle"
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      />
    </div>
  );
}
