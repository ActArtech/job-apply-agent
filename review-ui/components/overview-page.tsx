"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import type { AnalyticsFunnel, JobSummary, RunState } from "@/lib/types";
import { vettingStatusOf } from "@/lib/types";
import { SkeletonList } from "@/components/ui/skeleton";
import { ErrorBanner } from "@/components/ui/error-banner";
import { RunLauncherModal, type LaunchPhase } from "@/components/run-launcher-modal";

function FunnelBar({ funnel }: { funnel: AnalyticsFunnel }) {
  const stages = [
    { label: "Gathered", value: funnel.gathered, href: "/phase/1" },
    { label: "Approved", value: funnel.approved, href: "/phase/2" },
    { label: "Generated", value: funnel.generated, href: "/phase/3" },
    { label: "Reviewed", value: funnel.reviewed, href: "/review" },
    { label: "Sent", value: funnel.sent, href: "/tracking" },
  ];
  const max = funnel.gathered || 1;
  return (
    <div className="space-y-2">
      {stages.map((s) => (
        <Link key={s.label} href={s.href} className="flex items-center gap-3 rounded px-1 transition hover:bg-[#1a1b18]/60">
          <span className="w-20 text-right font-mono text-[10px] text-muted uppercase">{s.label}</span>
          <div className="flex-1 rounded-full bg-[#232421] h-2">
            <div className="h-2 rounded-full bg-accent transition-all" style={{ width: `${(s.value / max) * 100}%` }} />
          </div>
          <span className="w-8 font-mono text-xs text-[#f5f6f4]">{s.value}</span>
        </Link>
      ))}
    </div>
  );
}

export function OverviewPage() {
  const [funnel, setFunnel] = useState<AnalyticsFunnel | null>(null);
  const [sentToday, setSentToday] = useState<{ sent_today: number; limit: number } | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunState[]>([]);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [launcher, setLauncher] = useState<LaunchPhase | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [f, runs, health, st, jobList] = await Promise.all([
        api.analytics.funnel(),
        api.runs.list(),
        api.health(),
        api.analytics.sentToday(),
        api.jobs.list(),
      ]);
      setFunnel(f);
      setRecentRuns(runs.slice(0, 8));
      setApiOk(health.ok);
      setSentToday(st);
      setJobs(jobList);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <SkeletonList rows={6} />;

  const couldntVet = jobs.filter((j) => vettingStatusOf(j.vetting) === "error").length;
  const awaitingGeneration = jobs.filter((j) => vettingStatusOf(j.vetting) === "approved" && !j.generation).length;
  const awaitingReview = funnel ? Math.max(0, funnel.generated - funnel.reviewed) : 0;
  const activeRun = recentRuns.find((r) => r.status === "running" || r.status === "queued") ?? null;

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {launcher && (
        <RunLauncherModal
          defaultPhase={launcher}
          onClose={() => { setLauncher(null); load(); }}
        />
      )}

      {error && <ErrorBanner message={error} onRetry={load} />}

      {activeRun && (
        <Link href={`/runs/${activeRun.run_id}`} className="flex items-center justify-between rounded-md border border-amber-800/60 bg-amber-950/20 px-4 py-3">
          <span className="flex items-center gap-2 font-mono text-xs text-amber-400">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
            {activeRun.phase} running — view live progress
          </span>
          <span className="font-mono text-[10px] uppercase text-amber-400">→</span>
        </Link>
      )}

      <div className="flex items-center gap-4 text-xs font-mono">
        <span className={`flex items-center gap-1.5 ${apiOk ? "text-emerald-400" : "text-rose-400"}`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          {apiOk ? "API CONNECTED" : "API UNREACHABLE"}
        </span>
      </div>

      <section>
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => setLauncher("phase1")}
            className="rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent"
          >
            ▶ Phase 1 — Gather
          </button>
          <button
            onClick={() => setLauncher("safe-prepare")}
            className="rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent"
          >
            ▶ Full Pipeline
          </button>
          <Link href="/review" className="rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent">
            Review Queue {funnel ? `(${Math.max(0, funnel.generated - funnel.reviewed)} pending)` : ""}
          </Link>
          <Link href="/tracking" className="rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent">
            Tracking Board
          </Link>
          <Link href="/analytics" className="rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent">
            Analytics
          </Link>
        </div>
      </section>

      <section>
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">Needs Attention</h2>
        <div className="grid grid-cols-3 gap-3">
          {([
            [couldntVet, "couldn't be vetted", "Retry in Vet", "/phase/2"],
            [awaitingGeneration, "approved, awaiting generation", "Generate", "/phase/3"],
            [awaitingReview, "generated, ready to review", "Review & Send", "/review"],
          ] as const).map(([count, label, action, href]) => (
            <Link key={label} href={href} className={`rounded-md border p-4 transition ${count > 0 ? "border-amber-800/60 bg-amber-950/10 hover:bg-amber-950/20" : "border-border bg-[#10110f] opacity-60"}`}>
              <div className="font-mono text-2xl font-bold text-[#f5f6f4]">{count}</div>
              <div className="mt-1 text-xs text-muted">{label}</div>
              <div className="mt-2 font-mono text-[10px] uppercase text-accent">{action} →</div>
            </Link>
          ))}
        </div>
      </section>

      {funnel && (
        <section>
          <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">Pipeline Funnel</h2>
          <div className="rounded-md border border-border bg-[#10110f] p-4">
            <FunnelBar funnel={funnel} />
          </div>
        </section>
      )}

      {funnel && (
        <section>
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "Gathered", value: String(funnel.gathered) },
              { label: "Approved", value: String(funnel.approved) },
              { label: "Sent Total", value: String(funnel.sent) },
              { label: "Sent Today", value: sentToday ? `${sentToday.sent_today} / ${sentToday.limit}` : "—" },
            ].map((s) => (
              <div key={s.label} className="rounded-md border border-border bg-[#10110f] p-4 text-center">
                <div className="font-mono text-2xl font-bold text-[#f5f6f4]">{s.value}</div>
                <div className="font-mono text-[10px] uppercase text-muted mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-muted mb-3">Recent Runs</h2>
        {recentRuns.length === 0 ? (
          <div className="text-xs text-muted font-mono">No runs yet.</div>
        ) : (
          <div className="rounded-md border border-border bg-[#10110f] divide-y divide-border/40">
            {recentRuns.map((run) => (
              <Link key={run.run_id} href={`/runs/${run.run_id}`} className="flex items-center justify-between px-4 py-3 hover:bg-[#1a1b18]/60 transition">
                <span className="font-mono text-xs text-[#f5f6f4]">{run.phase}</span>
                <span className={`font-mono text-[10px] uppercase ${run.status === "succeeded" ? "text-emerald-400" : run.status === "failed" ? "text-rose-400" : "text-amber-400"}`}>
                  {run.status}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
