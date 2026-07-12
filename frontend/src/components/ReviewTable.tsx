import { FieldRow } from "@/components/FieldRow";
import type { AlternativeOut, FieldMappingOut } from "@/lib/types";

interface ReviewTableProps {
  sourceColumns: string[];
  mappings: FieldMappingOut[];
  onResolveByChip: (targetField: string, candidate: AlternativeOut) => void;
  onResolveByAccept: (targetField: string) => void;
  onResolveByDropdown: (targetField: string, column: string) => void;
  onReopen: (targetField: string) => void;
}

/**
 * The side-by-side two-pane review region (UI-03). Left pane -- Source
 * Columns (~32%, read-only, mono/Label list of `source_columns` names).
 * `/api/upload`'s `MappingResponse` carries only the column NAMES, never
 * the underlying cell values (`lib/types.ts::MappingResponse.source_columns:
 * string[]`) -- so unlike 04-UI-SPEC.md's literal "1-2 truncated sample
 * values" description, this pane is names-only for every upload (not just
 * under headers-only); a short muted note says so rather than silently
 * omitting the sample-values sub-bullet with no explanation. Right pane --
 * Target Fields (~68%), one `FieldRow` per `FieldMapping` in the order the
 * user declared their fields (`MappingProposal.field_mappings`'s own
 * order, never re-sorted). Below 1024px the inner grid becomes a
 * horizontally-scrolling container with a `min-width` floor -- the page
 * body itself never scrolls horizontally (04-UI-SPEC.md Layout &
 * Responsive Behavior); the outer wrapper also owns its own vertical
 * scroll so the sticky `ConfirmGate` footer (a sibling in `Review.tsx`)
 * never needs to be scrolled into view.
 */
export function ReviewTable({
  sourceColumns,
  mappings,
  onResolveByChip,
  onResolveByAccept,
  onResolveByDropdown,
  onReopen,
}: ReviewTableProps) {
  return (
    <div className="h-full overflow-x-auto overflow-y-auto rounded-xl border border-border bg-card">
      <div className="flex min-w-[960px]">
        <div className="w-[32%] shrink-0 border-r border-border p-4">
          <h2 className="mb-3 text-heading">Source Columns</h2>
          <ul className="flex flex-col gap-2">
            {sourceColumns.map((column) => (
              <li key={column} className="truncate text-mono-label text-foreground">
                {column}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-label text-muted-foreground">
            Column names only — sample values aren't part of this response.
          </p>
        </div>
        <div className="flex w-[68%] flex-col divide-y divide-border">
          <h2 className="px-4 pt-4 text-heading">Target Fields</h2>
          {mappings.map((mapping) => (
            <FieldRow
              key={mapping.target_field}
              mapping={mapping}
              sourceColumns={sourceColumns}
              onResolveByChip={(candidate) => onResolveByChip(mapping.target_field, candidate)}
              onResolveByAccept={() => onResolveByAccept(mapping.target_field)}
              onResolveByDropdown={(column) => onResolveByDropdown(mapping.target_field, column)}
              onReopen={() => onReopen(mapping.target_field)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
