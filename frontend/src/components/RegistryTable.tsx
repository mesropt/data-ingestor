import { Badge } from "@/components/ui/badge";
import { formatProvenance, type FieldRow } from "@/state/registry";
import type { AliasPayload } from "@/lib/types";

interface RegistryTableProps {
  /** The shaped crosswalk rows (from `state/registry.ts::groupFieldRows`),
   * already in the envelope's canonical-field order. */
  rows: FieldRow[];
}

/**
 * The read-only crosswalk table (REG-01, REG-02, D-09-03) -- one row group per
 * canonical field: the field's name + quiet mono metadata on the left, its
 * vendor aliases + legible provenance on the right. Mirrors `ReviewTable`'s
 * idiom + tokens (rounded-xl border bg-card, `text-heading` headers,
 * `text-mono-label` for column/vendor names, `text-label text-muted-foreground`
 * for quiet metadata and empty states); it invents no new palette.
 *
 * Every crosswalk value (canonical field name, vendor, source_column, and the
 * provenance label/actor/timestamp) is untrusted DB/map-file content, rendered
 * as plain escaped JSX children only -- no raw-HTML injection prop anywhere
 * (the escape-by-default idiom; the T-09-01 mitigation).
 */
export function RegistryTable({ rows }: RegistryTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="grid grid-cols-[minmax(0,1fr)] divide-y divide-border md:grid-cols-1">
        {rows.map((row) => (
          <FieldGroup key={row.name} row={row} />
        ))}
      </div>
    </div>
  );
}

/** One canonical field and all its vendor aliases -- a left identity pane and a
 * right aliases pane, stacking below `md`. */
function FieldGroup({ row }: { row: FieldRow }) {
  return (
    <div className="flex flex-col gap-4 p-4 md:flex-row md:gap-6">
      <div className="w-full shrink-0 md:w-[30%] md:border-r md:border-border md:pr-6">
        <div className="flex items-center gap-2">
          <span className="text-mono-label text-foreground">{row.name}</span>
          {row.required && <Badge variant="outline">required</Badge>}
        </div>
        <FieldMetadataLine row={row} />
      </div>

      <div className="min-w-0 flex-1">
        {row.hasAliases ? (
          <ul className="flex flex-col gap-3">
            {row.aliases.map((alias, index) => (
              <AliasRow key={`${alias.vendor}:${alias.source_column}:${index}`} alias={alias} />
            ))}
          </ul>
        ) : (
          <p className="text-label text-muted-foreground">no vendor aliases recorded yet</p>
        )}
      </div>
    </div>
  );
}

/** The quiet mono metadata under a canonical field name -- each part rendered
 * only when the field actually carries it (D-09-03). */
function FieldMetadataLine({ row }: { row: FieldRow }) {
  const { type, unit, allowedValues, min, max } = row.metadata;
  const parts: string[] = [];
  if (type) {
    parts.push(type);
  }
  if (unit) {
    parts.push(unit);
  }
  if (min !== null) {
    parts.push(`min ${min}`);
  }
  if (max !== null) {
    parts.push(`max ${max}`);
  }
  if (allowedValues && allowedValues.length > 0) {
    parts.push(`allowed: ${allowedValues.join(", ")}`);
  }

  if (parts.length === 0 && !row.description) {
    return null;
  }

  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {parts.length > 0 && <p className="text-mono-label text-muted-foreground">{parts.join(" · ")}</p>}
      {row.description && <p className="text-label text-muted-foreground">{row.description}</p>}
    </div>
  );
}

/** One vendor alias: the vendor + its raw source column on the left of the
 * line, a compact provenance cell (label · actor · when, each an escaped span)
 * on the right. */
function AliasRow({ alias }: { alias: AliasPayload }) {
  const provenance = formatProvenance(alias);
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-border/60 bg-background/40 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-mono-label text-foreground">{alias.vendor}</span>
        <span className="text-label text-muted-foreground">maps</span>
        <span className="truncate text-mono-label text-foreground">{alias.source_column}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-label text-muted-foreground">
        <Badge variant="outline">{provenance.label}</Badge>
        <span className="truncate">{provenance.actor}</span>
        <span aria-hidden>·</span>
        <span className="whitespace-nowrap">{provenance.when}</span>
      </div>
    </li>
  );
}
