"use client";
import type { HistoryEvent } from "@/lib/types";

const EVENT_COLORS: Record<string, string> = {
  gathered: "text-blue-400",
  vetted: "text-cyan-400",
  generated: "text-purple-400",
  reviewed: "text-amber-400",
  sent: "text-emerald-400",
  followup: "text-teal-400",
  regen: "text-orange-400",
};

function formatTs(ts: string) {
  try {
    return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}

export function HistoryTimeline({ events }: { events: HistoryEvent[] }) {
  if (events.length === 0) {
    return <p className="text-xs text-muted font-mono">No history recorded.</p>;
  }
  return (
    <ol className="relative border-l border-border/50 space-y-4 ml-2">
      {events.map((ev, i) => (
        <li key={i} className="ml-4">
          <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border border-border bg-[#131412]" />
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <span className={`font-mono text-[10px] uppercase font-semibold ${EVENT_COLORS[ev.event] ?? "text-muted"}`}>{ev.event}</span>
              {ev.detail && <p className="mt-0.5 text-xs text-foreground/80">{ev.detail}</p>}
              {ev.hint && <p className="mt-0.5 text-[10px] text-muted">{ev.hint}</p>}
            </div>
            <time className="shrink-0 font-mono text-[10px] text-muted/60">{formatTs(ev.at)}</time>
          </div>
        </li>
      ))}
    </ol>
  );
}
