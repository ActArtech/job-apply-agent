import Link from "next/link";
import type { ReactNode } from "react";
import { ReviewQueueBadge } from "@/components/review-queue-badge";
import { ActiveRunIndicator } from "@/components/active-run-indicator";

const navGroups = [
  {
    name: "pipeline",
    items: [
      { key: "phase-1", label: "1 · Gather",   href: "/phase/1" },
      { key: "phase-2", label: "2 · Vet",      href: "/phase/2" },
      { key: "phase-3", label: "3 · Generate", href: "/phase/3" },
      { key: "phase-4", label: "4 · Contacts", href: "/phase/4" },
      { key: "review",  label: "5 · Review & Send", href: "/review" },
    ],
  },
  {
    name: "monitor",
    items: [
      { key: "runs", label: "Runs", href: "/runs" },
      { key: "tracking", label: "Tracking", href: "/tracking" },
      { key: "analytics", label: "Analytics", href: "/analytics" },
    ],
  },
  {
    name: "config",
    items: [{ key: "settings", label: "Settings", href: "/settings" }],
  },
];

export function DashboardFrame({ active, children }: { active: string; children: ReactNode }) {
  return (
    <main className="h-screen bg-background text-foreground flex flex-col font-sans select-none overflow-hidden">
      <header className="border-b border-border px-6 py-4 flex justify-between items-center bg-[#131412] shrink-0">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <svg viewBox="0 0 40 40" className="w-6 h-6 text-foreground fill-none stroke-current stroke-2">
              <ellipse cx="20" cy="20" rx="14" ry="7" transform="rotate(-30 20 20)" className="opacity-80" />
              <ellipse cx="20" cy="20" rx="7" ry="14" transform="rotate(-30 20 20)" className="stroke-accent" />
            </svg>
            <span className="font-mono text-sm tracking-wider font-semibold">APPLY_CONTROL</span>
          </Link>
          <nav className="flex items-center gap-4 text-sm font-medium">
            <Link
              href="/"
              className={`pb-4 pt-1 px-1 font-sans tracking-wide transition ${
                active === "overview" ? "text-[#f5f6f4] border-b-2 border-accent" : "text-muted hover:text-foreground"
              }`}
            >
              Overview
            </Link>
            {navGroups.map((group) => (
              <div key={group.name} className="flex items-center gap-4 border-l border-border/60 pl-4">
                {group.items.map((item) => (
                  <Link
                    key={item.key}
                    href={item.href}
                    className={`pb-4 pt-1 px-1 font-sans tracking-wide transition ${
                      active === item.key
                        ? "text-[#f5f6f4] border-b-2 border-accent"
                        : "text-muted hover:text-foreground"
                    }`}
                  >
                    {item.label}
                    {item.key === "review" && <ReviewQueueBadge />}
                  </Link>
                ))}
              </div>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-4 text-[10px] font-mono text-muted">
          <ActiveRunIndicator />
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            <span>API ACTIVE</span>
          </div>
          <span className="opacity-40">|</span>
          <span>STABLE RELEASE v1.0.0</span>
        </div>
      </header>
      <div data-testid="route-body" className="flex-1 min-h-0 overflow-auto">{children}</div>
    </main>
  );
}
