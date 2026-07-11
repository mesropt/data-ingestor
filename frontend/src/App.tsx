import { useState } from "react";

import { AppShell, type AppTab } from "@/components/AppShell";
import { Toaster } from "@/components/ui/sonner";
import { DefineFields } from "@/screens/DefineFields";

const TABS: AppTab[] = [
  { value: "define-fields", label: "Define Fields" },
  { value: "upload", label: "Upload" },
  { value: "review", label: "Review" },
];

function ComingSoonPanel({ label }: { label: string }) {
  return (
    <div className="mx-auto max-w-3xl text-body text-muted-foreground">
      {label} is built in a later plan of this phase.
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<string>(TABS[0].value);

  return (
    <>
      <AppShell tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab}>
        {activeTab === "define-fields" && <DefineFields />}
        {activeTab === "upload" && <ComingSoonPanel label="Upload" />}
        {activeTab === "review" && <ComingSoonPanel label="Review" />}
      </AppShell>
      <Toaster />
    </>
  );
}

export default App;
