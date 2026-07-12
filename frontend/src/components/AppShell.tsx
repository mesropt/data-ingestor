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
  /** An extra trailing group placed alongside the ThemeToggle at the bar's
   * right edge (Plan 06's SignedInIndicator). Kept in one flex group with
   * ThemeToggle so the header stays three justify-between clusters and the
   * load-bearing h-16/max-w-5xl bar geometry is unchanged. */
  trailing?: ReactNode;
}

/**
 * Top bar (wordmark, tab nav, theme toggle) + a bounded content area
 * (UI-SPEC Design System / Layout & Responsive Behavior: "the page body
 * itself never scrolls horizontally" -- enforced globally in index.css).
 *
 * Four tabs -- Schemas / Upload / Review / Documentation (D-10-09, Plan 10-06: Define
 * Fields is deleted, Registry is renamed to Schemas). No geometry change --
 * the bar's `h-16`/`max-w-5xl` sizing is unchanged; four tabs fit the
 * existing `TabsList` with room to spare (one fewer than the prior five).
 * The UI-SPEC's "Profiles" tab remains DESCOPED for v1 (W2): the learning
 * loop is surfaced via the Review screen's auto-apply banner instead of a
 * standalone management screen with no data behind it yet.
 */
export function AppShell({ tabs, activeTab, onTabChange, children, trailing }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-secondary">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-8 px-8">
          <span className="flex shrink-0 items-center gap-2">
            {/* Decorative: the wordmark beside it already names the product, so the
             * mark itself carries no information a screen reader needs to hear. */}
            <img src="/favicon.svg" alt="" aria-hidden="true" className="size-7 rounded-md" />
            <span className="text-heading text-primary">Data Ingestor</span>
          </span>
          <Tabs value={activeTab} onValueChange={(value) => onTabChange(String(value))}>
            <TabsList>
              {tabs.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {trailing}
          </div>
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
