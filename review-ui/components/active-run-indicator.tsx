"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import type { RunState } from "@/lib/types";

export function ActiveRunIndicator() {
  const [active, setActive] = useState<RunState | null>(null);

  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const runs = await api.runs.list();
        if (!stop) setActive(runs.find((r) => r.status === "running" || r.status === "queued") ?? null);
      } catch {
        if (!stop) setActive(null);
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  if (!active) return null;
  const lastProgress = [...(active.events ?? [])].reverse().find((e) => e.type === "progress");
  return (
    <Link
      href={`/runs/${active.run_id}`}
      className="flex items-center gap-1.5 rounded border border-amber-800/60 bg-amber-950/20 px-2 py-1 font-mono text-[10px] uppercase text-amber-400"
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
      {active.phase}
      {lastProgress?.type === "progress" ? ` ${lastProgress.done}/${lastProgress.total}` : ""}
    </Link>
  );
}
