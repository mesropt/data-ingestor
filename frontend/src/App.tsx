import { useState } from "react";

import { AppShell, type AppTab } from "@/components/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { DefineFields } from "@/screens/DefineFields";
import { Review } from "@/screens/Review";
import { Upload } from "@/screens/Upload";
import type { FieldSetPayload, MappingResponse } from "@/lib/types";

const TABS: AppTab[] = [
  { value: "define-fields", label: "Define Fields" },
  { value: "upload", label: "Upload" },
  { value: "review", label: "Review" },
];

function App() {
  const [activeTab, setActiveTab] = useState<string>(TABS[0].value);
  const [lastMapping, setLastMapping] = useState<MappingResponse | null>(null);
  const [lastFieldSet, setLastFieldSet] = useState<FieldSetPayload | null>(null);

  function handleMapped(response: MappingResponse, fieldSet: FieldSetPayload) {
    setLastMapping(response);
    setLastFieldSet(fieldSet);
    setActiveTab("review");
  }

  return (
    <>
      <AppShell tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab}>
        {activeTab === "define-fields" && <DefineFields />}
        {activeTab === "upload" && <Upload onMapped={handleMapped} />}
        {activeTab === "review" && (
          // Keyed by upload_token so a fresh upload (including a
          // same-signature re-upload for the UI-06 money shot) always
          // remounts Review with fresh local resolution state, rather
          // than this screen trying to detect "a new mapping arrived"
          // via an effect.
          <Review key={lastMapping?.upload_token ?? "empty"} mapping={lastMapping} fieldSet={lastFieldSet} />
        )}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;
