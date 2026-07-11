import type { ReactNode } from "react";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ThemeToggle } from "@/components/ThemeToggle";

export interface AppTab {
  value: string;
  label: string;
}

interface AppShellProps {
  tabs: AppTab[];
  activeTab: string;
  onTabChange: (value: string) => void;
  children: ReactNode;
}

/**
 * Top bar (wordmark, tab nav, theme toggle) + a bounded content area
 * (UI-SPEC Design System / Layout & Responsive Behavior: "the page body
 * itself never scrolls horizontally" -- enforced globally in index.css).
 *
 * Three tabs only -- Define Fields / Upload / Review. The UI-SPEC's fourth
 * "Profiles" tab is DESCOPED for v1 (W2): the learning loop is surfaced via
 * the Review screen's auto-apply banner (Plan 06) instead of a standalone
 * management screen with no data behind it yet.
 */
export function AppShell({ tabs, activeTab, onTabChange, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-secondary">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-8 px-8">
          <span className="text-heading text-primary">Data Ingestor</span>
          <Tabs value={activeTab} onValueChange={(value) => onTabChange(String(value))}>
            <TabsList>
              {tabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <ThemeToggle />
        </div>
      </header>
      <main className="flex-1 px-8 py-8">{children}</main>
      <footer className="border-t border-border bg-secondary">
        <div className="mx-auto flex max-w-5xl flex-col items-center gap-1 px-8 py-6 text-center text-mono-label text-muted-foreground">
          <p>
            Built by Mesrop Tarkhanyan with{" "}
            <a
              href="https://claude.com/claude-code"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2 hover:text-foreground"
            >
              Claude Code
            </a>
          </p>
          <p>for the Built with Claude: Life Sciences hackathon 2026 by Anthropic</p>
        </div>
      </footer>
    </div>
  );
}
