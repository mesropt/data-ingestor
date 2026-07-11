import { useState } from "react";

import { AppShell, type AppTab } from "@/components/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { DefineFields } from "@/screens/DefineFields";
import { Upload } from "@/screens/Upload";
import type { MappingResponse } from "@/lib/types";

const TABS: AppTab[] = [
  { value: "define-fields", label: "Define Fields" },
  { value: "upload", label: "Upload" },
  { value: "review", label: "Review" },
];

/** Plan 06 replaces this with the real Review screen -- for now, this
 * proves the Upload screen's navigation seam ("on a mapping response,
 * route to Review") without pre-building Plan 06's own UI-03/04/05 work. */
function ReviewPlaceholder({ mapping }: { mapping: MappingResponse | null }) {
  if (!mapping) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-2 py-16 text-center">
        <h2 className="text-heading">No file uploaded yet.</h2>
        <p className="max-w-md text-body text-muted-foreground">
          Upload a CSV or Excel file and choose a field set to see Claude's proposed mapping here.
        </p>
      </div>
    );
  }
  const clearCount = mapping.field_mappings.filter((m) => !m.needs_confirmation).length;
  return (
    <div className="mx-auto max-w-3xl text-body text-muted-foreground">
      Mapping received for upload token <span className="text-mono-label">{mapping.upload_token}</span> --{" "}
      {clearCount} of {mapping.field_mappings.length} fields resolved. The full Review screen (UI-03/04/05) is
      built in Plan 06.
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<string>(TABS[0].value);
  const [lastMapping, setLastMapping] = useState<MappingResponse | null>(null);

  function handleMapped(response: MappingResponse) {
    setLastMapping(response);
    setActiveTab("review");
  }

  return (
    <>
      <AppShell tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab}>
        {activeTab === "define-fields" && <DefineFields />}
        {activeTab === "upload" && <Upload onMapped={handleMapped} />}
        {activeTab === "review" && <ReviewPlaceholder mapping={lastMapping} />}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;
