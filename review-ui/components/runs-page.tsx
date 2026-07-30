"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchJson } from "@/lib/api-client";
import { RunLauncherModal } from "@/components/run-launcher-modal";
import type { RunState } from "@/lib/types";

function fmtDate(iso?: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function summary(result?: Record<string, unknown> | null) {
  if (!result) return "-";
  return Object.entries(result)
    .filter(([, v]) => ["string", "number", "boolean"].includes(typeof v))
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(" / ");
}

function statusClass(status: string) {
  if (status === "succeeded") return "text-emerald-400";
  if (status === "failed") return "text-rose-400";
  if (status === "running") return "text-amber-400 animate-pulse";
  return "text-muted";
}

export function RunsPage() {
  const [runs, setRuns] = useState<RunState[]>([]);
  const [error, setError] = useState("");
  const [showLauncher, setShowLauncher] = useState(false);

  function load() {
    fetchJson<RunState[]>("/runs")
      .then(setRuns)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load runs"));
  }

  useEffect(() => { load(); }, []);

  return (
    <section className="min-h-full bg-background p-6">
      {showLauncher && (
        <RunLauncherModal
          onClose={() => { setShowLauncher(false); load(); }}
        />
      )}

      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted">Pipeline Audit</p>
          <h1 className="mt-1 text-2xl font-semibold text-[#f5f6f4]">Run History</h1>
          <p className="mt-1 text-sm text-muted">Every backend run with phase, status, logs, and result summary.</p>
        </div>
        <button
          onClick={() => setShowLauncher(true)}
          className="shrink-0 rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent"
        >
          ▶ New Run
        </button>
      </div>

      {error ? (
        <div className="mb-3 rounded-md border border-rose-900 bg-rose-950/30 p-3 text-sm text-rose-200">{error}</div>
      ) : null}

      <div className="overflow-hidden rounded-md border border-border bg-[#131412]">
        <div className="grid grid-cols-[1fr_0.7fr_0.7fr_1fr] border-b border-border bg-[#171815] px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-muted">
          <div>Run ID</div><div>Phase</div><div>Status</div><div>Created</div>
        </div>
        {runs.length > 0 ? (
          runs.map((run) => (
            <Link
              key={run.run_id}
              href={`/runs/${run.run_id}`}
              title={summary(run.result)}
              className="grid grid-cols-[1fr_0.7fr_0.7fr_1fr] gap-3 border-b border-border/40 px-4 py-3 text-sm last:border-b-0 hover:bg-[#1a1b18]/70"
            >
              <div className="truncate font-mono text-xs text-[#f5f6f4]" title={run.run_id}>{run.run_id}</div>
              <div className="text-xs text-muted">{run.phase}</div>
              <div className={`font-mono text-xs ${statusClass(run.status)}`}>{run.status}</div>
              <div className="font-mono text-xs text-muted">{fmtDate(run.created_at)}</div>
            </Link>
          ))
        ) : (
          <div className="p-8 text-center text-sm text-muted">No run history yet.</div>
        )}
      </div>
    </section>
  );
}
