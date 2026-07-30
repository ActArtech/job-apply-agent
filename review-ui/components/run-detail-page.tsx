"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchJson } from "@/lib/api-client";
import { useRunEvents } from "@/lib/run-events";
import { notifyRunDone } from "@/lib/notifications";
import { toast } from "@/components/ui/toast";
import type { RunState, RunEvent } from "@/lib/types";

const jobIdKeys = ["job_id","job_ids","new_job_ids","already_found_job_ids","approved_job_ids","rejected_job_ids","error_job_ids","generated_job_ids","selected"];

const resultStyles: Record<string, string> = {
  approved: "text-emerald-400 border-emerald-800/60",
  generated: "text-emerald-400 border-emerald-800/60",
  found: "text-emerald-400 border-emerald-800/60",
  new: "text-emerald-400 border-emerald-800/60",
  rejected: "text-rose-400 border-rose-800/60",
  failed: "text-rose-400 border-rose-800/60",
  error: "text-amber-400 border-amber-800/60",
  partial: "text-amber-400 border-amber-800/60",
  duplicate: "text-muted border-border",
  not_found: "text-muted border-border",
};

const resultIcons: Record<string, string> = {
  approved: "✓", generated: "✓", found: "✓", new: "+",
  rejected: "✗", failed: "✗", error: "⚠", partial: "◐",
  duplicate: "=", not_found: "—",
};

function primitiveSummary(result?: Record<string, unknown> | null) {
  if (!result) return [];
  return Object.entries(result)
    .filter(([, v]) => ["string", "number", "boolean"].includes(typeof v))
    .map(([k, v]) => [k.replace(/_/g, " "), String(v)] as const);
}

function linkedJobIds(result?: Record<string, unknown> | null) {
  if (!result) return [];
  const ids = new Set<string>();
  for (const key of jobIdKeys) {
    const val = result[key];
    if (typeof val === "string" && val !== "none") ids.add(val);
    if (Array.isArray(val)) val.forEach((i) => typeof i === "string" && ids.add(i));
  }
  return Array.from(ids);
}

function runIdSuffixJob(runId: string): string | null {
  const i = runId.indexOf(":");
  if (i === -1) return null;
  const suffix = runId.slice(i + 1).trim();
  return suffix && suffix !== "none" ? suffix : null;
}

function statusBadge(status: string) {
  if (status === "succeeded") return "text-emerald-400 border-emerald-800/60 bg-emerald-950/20";
  if (status === "failed") return "text-rose-400 border-rose-800/60 bg-rose-950/20";
  if (status === "running") return "text-amber-400 border-amber-800/60 bg-amber-950/20 animate-pulse";
  return "text-muted border-border";
}

export function RunDetailPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunState | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"feed" | "logs" | "result">("feed");
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchJson<RunState>(`/runs/${runId}`)
      .then(setRun)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load run"));
  }, [runId]);

  const isLive = run?.status === "running" || run?.status === "queued";

  const events = useRunEvents(isLive ? runId : null, (state) => {
    const phase = run?.phase ?? "Run";
    toast(`${phase} ${state.status}`, state.status === "succeeded" ? "success" : "error");
    notifyRunDone(phase, state.status);
  });

  const displayLogs = isLive ? events.logs : (run?.logs ?? []);
  const displayStatus = (isLive && events.status !== "queued") ? events.status : (run?.status ?? "queued");
  const displayEvents: RunEvent[] = isLive ? events.events : (run?.events ?? []);
  const jobResults = displayEvents.filter((e) => e.type === "job_result");
  const lastProgress = [...displayEvents].reverse().find((e) => e.type === "progress");
  const phaseStart = displayEvents.find((e) => e.type === "phase_start");
  const engine = phaseStart?.type === "phase_start" ? phaseStart.engine : undefined;

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayLogs.length, jobResults.length]);

  const summary = useMemo(() => primitiveSummary(run?.result), [run?.result]);
  const jobIds = useMemo(() => linkedJobIds(run?.result), [run?.result]);
  const jobLinks = useMemo(() => {
    const map = new Map<string, string | null>();
    for (const e of displayEvents) {
      if (e.type === "job_result" && !map.get(e.job_id)) {
        map.set(e.job_id, [e.company, e.title].filter(Boolean).join(" — ") || null);
      }
    }
    for (const id of linkedJobIds(run?.result)) if (!map.has(id)) map.set(id, null);
    const suffix = run ? runIdSuffixJob(run.run_id) : null;
    if (suffix && !map.has(suffix)) map.set(suffix, null);
    return Array.from(map, ([id, label]) => ({ id, label }));
  }, [displayEvents, run?.result, run?.run_id]);

  if (error) return (
    <section className="min-h-full bg-background p-6">
      <div className="rounded-md border border-rose-900 bg-rose-950/30 p-4 text-sm text-rose-200">{error}</div>
    </section>
  );

  if (!run) return (
    <section className="min-h-full bg-background p-6">
      <div className="rounded-md border border-border bg-[#131412] p-6 text-sm text-muted">Loading…</div>
    </section>
  );

  return (
    <section className="min-h-full bg-background p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Runs / {run.run_id}</div>
          <h1 className="mt-1 text-2xl font-semibold text-[#f5f6f4]">{run.phase}</h1>
          <p className="mt-1 text-sm text-muted">Backend audit trail, logs, and result payload.</p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${statusBadge(displayStatus)}`}>
            {displayStatus}
          </span>
          <Link href="/runs" className="rounded border border-border px-3 py-2 font-mono text-xs text-[#bfc2b9] hover:border-accent/60 hover:text-accent">
            ← Runs
          </Link>
        </div>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        {([
          ["Phase", run.phase],
          ["Run ID", run.run_id.slice(0, 12) + "…"],
          ["Created", run.created_at ?? "-"],
          ["Updated", run.updated_at ?? "-"],
        ] as const).map(([label, value]) => (
          <div key={label} className="rounded-md border border-border bg-[#171815] p-3">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</div>
            <div className="mt-1 break-words text-sm font-semibold text-[#f5f6f4]">{value}</div>
          </div>
        ))}
      </div>

      {jobLinks.length > 0 && (
        <div className="mb-4 rounded-md border border-border bg-[#131412] p-3">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted">Jobs ({jobLinks.length})</div>
          <div className="flex flex-wrap gap-2">
            {jobLinks.map(({ id, label }) => (
              <Link
                key={id}
                href={`/jobs/${id}`}
                className="rounded border border-border px-2 py-1 font-mono text-xs text-accent transition hover:border-accent/60 hover:text-accent-hover"
                title={id}
              >
                {label ?? id}
              </Link>
            ))}
          </div>
        </div>
      )}

      {(lastProgress?.type === "progress" || engine) && (
        <div className="mb-4 rounded-md border border-border bg-[#131412] p-4">
          <div className="flex items-center justify-between font-mono text-xs text-[#bfc2b9]">
            <span>
              {lastProgress?.type === "progress" ? `${lastProgress.done} / ${lastProgress.total}` : ""}
              {engine ? <span className="ml-3 rounded border border-border px-1.5 py-0.5 text-[10px] uppercase text-accent">{engine}</span> : null}
            </span>
            {lastProgress?.type === "progress" && (
              <span className="flex gap-3">
                <span className="text-emerald-400">✓ {lastProgress.approved ?? 0}</span>
                <span className="text-rose-400">✗ {lastProgress.rejected ?? 0}</span>
                <span className="text-amber-400">⚠ {lastProgress.errors ?? 0}</span>
              </span>
            )}
          </div>
          {lastProgress?.type === "progress" && lastProgress.total > 0 && (
            <div className="mt-2 h-1.5 rounded-full bg-[#232421]">
              <div className="h-1.5 rounded-full bg-accent transition-all" style={{ width: `${(lastProgress.done / lastProgress.total) * 100}%` }} />
            </div>
          )}
        </div>
      )}

      <div className="mb-3 flex gap-1">
        {(["feed", "logs", "result"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider transition ${
              tab === t
                ? "border border-border bg-[#1a1b18] text-[#f5f6f4]"
                : "text-muted hover:text-foreground"
            }`}
          >
            {t === "feed" ? `Feed (${jobResults.length})` : t === "logs" ? `Raw Logs (${displayLogs.length})` : "Result"}
          </button>
        ))}
      </div>

      {tab === "feed" && (
        <div className="max-h-[60vh] space-y-1.5 overflow-auto">
          {jobResults.length === 0 ? (
            <div className="rounded-md border border-border bg-[#131412] p-6 text-sm text-muted">
              {isLive ? "Waiting for results…" : "No structured results recorded for this run."}
            </div>
          ) : (
            jobResults.map((e, i) => e.type === "job_result" && (
              <Link key={i} href={`/jobs/${e.job_id}`} className="flex items-start gap-3 rounded-md border border-border bg-[#131412] px-4 py-2.5 hover:bg-[#1a1b18]/70">
                <span className={`mt-0.5 rounded border px-1.5 font-mono text-xs ${resultStyles[e.status] ?? "text-muted border-border"}`}>
                  {resultIcons[e.status] ?? "·"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[#f5f6f4]">{e.company} — {e.title}</span>
                  <span className="block text-xs text-muted">{e.reason}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {e.engine && <span className="rounded border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase text-muted">{e.engine}</span>}
                  <span className={`font-mono text-[10px] uppercase ${(resultStyles[e.status] ?? "").split(" ")[0]}`}>{e.status.replace("_", " ")}</span>
                </span>
              </Link>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      )}

      {tab === "logs" && (
        <div className="max-h-[60vh] overflow-auto rounded-md border border-border bg-black/60 p-4">
          {displayLogs.length === 0 ? (
            <span className="font-mono text-xs text-muted">
              {isLive ? "Waiting for logs…" : "No logs recorded."}
            </span>
          ) : (
            <div className="space-y-0.5">
              {displayLogs.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-green-400/90">
                  {line}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      )}

      {tab === "result" && (
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <section className="rounded-md border border-border bg-[#131412] p-4">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-muted">Summary</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {summary.length > 0 ? summary.map(([label, value]) => (
                <div key={label} className="rounded border border-border bg-[#171815] px-3 py-2">
                  <div className="font-mono text-[10px] uppercase text-muted">{label}</div>
                  <div className="mt-1 text-sm font-semibold text-[#f5f6f4]">{value}</div>
                </div>
              )) : <div className="text-sm text-muted">No result yet.</div>}
            </div>
            {jobIds.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted">Linked Jobs</div>
                <div className="flex flex-wrap gap-2">
                  {jobIds.map((id) => (
                    <Link key={id} href={`/jobs/${id}`} className="rounded border border-border px-2 py-1 font-mono text-xs text-accent hover:text-accent-hover">
                      {id}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="rounded-md border border-border bg-[#131412] p-4">
            <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-muted">Raw JSON</h2>
            <pre className="max-h-80 overflow-auto rounded border border-border bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-[#d7dacd]">
              {JSON.stringify(run.result ?? {}, null, 2)}
            </pre>
          </section>
        </div>
      )}
    </section>
  );
}
