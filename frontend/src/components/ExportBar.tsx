import { Download } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

interface ExportBarProps {
  exportUrls: Record<string, string>;
}

const EXPORT_LINKS: { label: string; key: string }[] = [
  { label: "Export CSV", key: "csv_url" },
  { label: "Export Excel", key: "xlsx_url" },
  { label: "Export JSON", key: "json_url" },
  { label: "Download Manifest", key: "manifest_url" },
];

/**
 * Post-confirm export actions (UI-05) -- shown only after a 200 from
 * `/api/confirm` (`Review.tsx` never renders this from its own local
 * `isReady`, only from the server's own successful `ConfirmResponse`).
 * Each is a plain `<a href>` GET to the URL the server already returned
 * (`/api/export/{run_id}/{fmt}`) -- no client-side file construction, no
 * second request to figure out where the file lives.
 */
export function ExportBar({ exportUrls }: ExportBarProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {EXPORT_LINKS.map(({ label, key }) => {
          const url = exportUrls[key];
          if (!url) return null;
          return (
            <a key={key} href={url} download className={buttonVariants({ variant: "outline" })}>
              <Download className="size-4" />
              {label}
            </a>
          );
        })}
      </div>
      {/* D-11-12/15 (SHEET-03): the reserved provenance column is written on
       * EVERY export, single-sheet and CSV included -- this one line makes
       * sure its first appearance in a downloaded file is never a surprise. */}
      <p className="text-label text-muted-foreground">
        Exports include a reserved __source_sheet column recording each row's source sheet.
      </p>
    </div>
  );
}
