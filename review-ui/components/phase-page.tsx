"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchJson } from "@/lib/api-client";
import { RunLauncherModal, type LaunchPhase } from "@/components/run-launcher-modal";
import type { JobSummary } from "@/lib/types";
import { getGenerationStats, vettingStatusOf } from "@/lib/types";
import { FilterBar } from "@/components/filter-bar";
import { matchesFilters, EMPTY_FILTERS, type Filters } from "@/lib/job-filters";

type PhaseKey = "1" | "2" | "3" | "4";

const phaseConfig: Record<PhaseKey, { title: string; description: string; io: string }> = {
  "1": {
    title: "Gather",
    description: "Scrapes all configured job sources and stores each new job as an artifact. Duplicates are detected and skipped.",
    io: "Input: source configs → Output: job artifacts (jd.txt, job.json)",
  },
  "2": {
    title: "Vet",
    description: "Sends each unvetted job's description to the AI engine against your 5 criteria. Already-vetted jobs are skipped; jobs that couldn't be vetted (rate limit, empty JD) stay retryable.",
    io: "Input: gathered jobs → Output: approved / filtered / couldn't vet",
  },
  "3": {
    title: "Generate",
    description: "Generates a tailored resume, cold email, and compiled PDF for every approved job, with ATS signal metrics.",
    io: "Input: approved jobs → Output: resume.pdf, email.txt, metrics",
  },
  "4": {
    title: "Contacts",
    description: "Searches Hunter, Apollo, and LinkedIn for a hiring-manager contact for each generated application.",
    io: "Input: generated jobs → Output: contact email / LinkedIn profile",
  },
};

type RowStatus =
  | "New" | "Pending" | "Approved" | "Filtered" | "Couldn't vet"
  | "Generated" | "Failed" | "Waiting" | "Found" | "Partial" | "Not found";

function phaseStatus(phase: PhaseKey, job: JobSummary): RowStatus {
  if (phase === "1") return job.vetting || job.generation || job.review ? "Pending" : "New";
  if (phase === "2") {
    const s = vettingStatusOf(job.vetting);
    if (s === "approved") return "Approved";
    if (s === "rejected") return "Filtered";
    if (s === "error") return "Couldn't vet";
    return "Pending";
  }
  if (phase === "3") return job.generation?.status === "generated" ? "Generated" : "Waiting";
  if (job.contact?.email) return "Found";
  if (job.contact?.discovery_method) return "Partial";
  return "Not found";
}

const statusStyle: Record<RowStatus, string> = {
  "Approved": "text-emerald-400", "Generated": "text-emerald-400", "Found": "text-emerald-400",
  "Filtered": "text-rose-400", "Failed": "text-rose-400",
  "Couldn't vet": "text-amber-400", "Partial": "text-amber-400",
  "New": "text-[#bfc2b9]", "Pending": "text-muted", "Waiting": "text-muted", "Not found": "text-muted",
};

function jobHref(phase: PhaseKey, job: JobSummary) {
  const anchor = phase === "2" ? "#curation" : phase === "3" ? "#metrics" : "";
  return `/jobs/${job.job_id}?fromPhase=${phase}${anchor}`;
}

function phaseRows(phase: PhaseKey, jobs: JobSummary[]) {
  if (phase === "3") return jobs.filter((job) => vettingStatusOf(job.vetting) === "approved" || job.generation);
  if (phase === "4") return jobs.filter((job) => job.generation?.status === "generated");
  return jobs;
}

function reasonFor(phase: PhaseKey, job: JobSummary) {
  if (phase === "1") return `${job.source}${job.location ? ` / ${job.location}` : ""}`;
  if (phase === "2") {
    const v = job.vetting;
    if (!v || Object.keys(v).length === 0) return "Not vetted yet";
    const engine = v.engine?.answered ?? (v.engine?.requested === "manual" ? "manual" : null);
    const text = v.reason ?? v.error ?? "No curation reason saved";
    return engine ? `[${engine}] ${text}` : text;
  }
  if (phase === "3") {
    const genStats = getGenerationStats(job.generation);
    const numeric = genStats?.numeric_bullets;
    const total = genStats?.total_bullets;
    const pages = genStats?.page_count;
    return `${numeric ?? 0}/${total ?? 0} numeric bullets${pages ? ` / ${pages} page PDF` : ""}`;
  }
  if (!job.contact) return "No contact searched yet";
  return job.contact.email || job.contact.discovery_method || "LinkedIn only (no email)";
}

export function PhasePage({ phase }: { phase: string }) {
  const normalized = (["1", "2", "3", "4"].includes(phase) ? phase : "1") as PhaseKey;
  const config = phaseConfig[normalized];
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("All");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [showLauncher, setShowLauncher] = useState(false);
  const [inlineActing, setInlineActing] = useState<string | null>(null);
  const [inlineGenerating, setInlineGenerating] = useState<string | null>(null);
  const [inlineRefinding, setInlineRefinding] = useState<string | null>(null);
  const launchPhase: LaunchPhase =
    normalized === "1" ? "phase1" :
    normalized === "2" ? "phase2" :
    normalized === "4" ? "phase4" :
    "phase3-all";

  useEffect(() => {
    fetchJson<JobSummary[]>("/jobs")
      .then(setJobs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load jobs"));
  }, []);

  async function inlineVet(jobId: string, approved: boolean) {
    if (inlineActing) return;
    setInlineActing(jobId);
    try {
      await fetchJson(`/jobs/${jobId}/vet`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ approved, reason: "Manual override" }),
      });
      setJobs((prev) =>
        prev.map((j) =>
          j.job_id === jobId
            ? { ...j, vetting: { ...j.vetting, approved, status: approved ? "approved" : "rejected", engine: { requested: "manual", answered: "manual" } } }
            : j
        )
      );
    } catch {
      // silent — row stays, user can retry
    } finally {
      setInlineActing(null);
    }
  }

  async function retryVet(jobId: string) {
    if (inlineActing) return;
    setInlineActing(jobId);
    try {
      const { run_id } = await fetchJson<{ run_id: string }>("/phases/phase2-single", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jobId }),
      });
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const run = await fetchJson<{ status: string }>(`/runs/${run_id}`);
        if (run.status === "succeeded" || run.status === "failed") {
          const refreshed = await fetchJson<JobSummary[]>("/jobs");
          setJobs(refreshed);
          break;
        }
      }
    } catch {
      // silent — row stays, user can retry
    } finally {
      setInlineActing(null);
    }
  }

  async function inlineGenerate(jobId: string) {
    if (inlineGenerating) return;
    setInlineGenerating(jobId);
    try {
      const { run_id } = await fetchJson<{ run_id: string }>("/phases/phase3", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jobId }),
      });
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const run = await fetchJson<{ status: string }>(`/runs/${run_id}`);
        if (run.status === "succeeded") {
          setJobs((prev) =>
            prev.map((j) =>
              j.job_id === jobId ? { ...j, generation: { status: "generated" } } : j
            )
          );
          break;
        }
        if (run.status === "failed") break;
      }
    } catch {
      // silent
    } finally {
      setInlineGenerating(null);
    }
  }

  async function inlineRefind(jobId: string) {
    if (inlineRefinding) return;
    setInlineRefinding(jobId);
    try {
      const { run_id } = await fetchJson<{ run_id: string }>("/phases/phase4-single", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jobId }),
      });
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const run = await fetchJson<{ status: string; result?: Record<string, unknown> }>(`/runs/${run_id}`);
        if (run.status === "succeeded") {
          const found = run.result?.found as boolean;
          setJobs((prev) =>
            prev.map((j) =>
              j.job_id === jobId
                ? { ...j, contact: found ? { email: "found", discovery_method: "Found" } : { discovery_method: "Partial" } }
                : j
            )
          );
          break;
        }
        if (run.status === "failed") break;
      }
    } catch {
      // silent
    } finally {
      setInlineRefinding(null);
    }
  }

  const rows = useMemo(() => phaseRows(normalized, jobs), [normalized, jobs]);

  const filterTabs: Record<PhaseKey, string[]> = {
    "1": ["All", "New", "Pending"],
    "2": ["All", "Pending", "Approved", "Filtered", "Couldn't vet"],
    "3": ["All", "Waiting", "Generated", "Failed"],
    "4": ["All", "Found", "Partial", "Not found"],
  };
  const visibleRows = useMemo(
    () =>
      rows
        .filter((job) => (filter === "All" ? true : phaseStatus(normalized, job) === filter))
        .filter((job) => matchesFilters(job, filters)),
    [filter, filters, rows, normalized]
  );

  const vetStatuses = jobs.map((j) => vettingStatusOf(j.vetting));
  const stats: Array<[string, number]> =
    normalized === "1" ? [
      ["Gathered", jobs.length],
      ["Unvetted", jobs.filter((j) => !j.vetting || Object.keys(j.vetting).length === 0).length],
      ["In pipeline", jobs.filter((j) => j.generation || (j.vetting && Object.keys(j.vetting).length > 0)).length],
      ["Sources", new Set(jobs.map((j) => j.source)).size],
    ] : normalized === "2" ? [
      ["Pending", jobs.filter((j) => vettingStatusOf(j.vetting) === null).length],
      ["Approved", vetStatuses.filter((s) => s === "approved").length],
      ["Filtered", vetStatuses.filter((s) => s === "rejected").length],
      ["Couldn't vet", vetStatuses.filter((s) => s === "error").length],
    ] : normalized === "3" ? [
      ["Eligible", vetStatuses.filter((s) => s === "approved").length],
      ["Generated", jobs.filter((j) => j.generation?.status === "generated").length],
      ["Failed", jobs.filter((j) => j.generation && j.generation.status !== "generated").length],
      ["Waiting", jobs.filter((j) => vettingStatusOf(j.vetting) === "approved" && !j.generation).length],
    ] : [
      ["Generated", jobs.filter((j) => j.generation?.status === "generated").length],
      ["Found", jobs.filter((j) => j.contact?.email).length],
      ["Partial", jobs.filter((j) => j.contact && !j.contact.email && j.contact.discovery_method).length],
      ["Not found", jobs.filter((j) => j.generation?.status === "generated" && !j.contact).length],
    ];

  return (
    <section className="min-h-full bg-background p-6">
      {showLauncher && (
        <RunLauncherModal
          defaultPhase={launchPhase}
          onClose={() => setShowLauncher(false)}
        />
      )}
      <div className="mb-5 flex items-end justify-between gap-4">
        <div className="max-w-2xl">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted">Pipeline Stage {normalized}</p>
          <h1 className="mt-1 text-2xl font-semibold text-[#f5f6f4]">{config.title}</h1>
          <p className="mt-1 text-sm text-muted">{config.description}</p>
          <p className="mt-1 font-mono text-xs text-[#bfc2b9]">{config.io}</p>
          <button
            onClick={() => setShowLauncher(true)}
            className="mt-3 rounded border border-border px-4 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent"
          >
            ▶ Run {config.title}
          </button>
        </div>
        <div className="grid grid-cols-4 gap-2 text-right">
          {stats.map(([label, value]) => (
            <div key={label} className="rounded-md border border-border bg-[#171815] px-3 py-2">
              <div className="font-mono text-[9px] uppercase text-muted">{label}</div>
              <div className="text-lg font-semibold text-[#f5f6f4]">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {error ? <div className="mb-3 rounded-md border border-rose-900 bg-rose-950/30 p-3 text-sm text-rose-200">{error}</div> : null}

      <div className="mb-3 flex gap-1">
        {filterTabs[normalized].map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`rounded px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider transition ${
              filter === t ? "border border-border bg-[#1a1b18] text-[#f5f6f4]" : "text-muted hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <FilterBar filters={filters} onChange={setFilters} jobs={jobs} />

      <div className="overflow-hidden rounded-md border border-border bg-[#131412]">
        <div className={`grid ${normalized === "2" || normalized === "3" || normalized === "4" ? "grid-cols-[1.2fr_0.8fr_0.8fr_1.5fr_80px]" : "grid-cols-[1.2fr_0.8fr_0.8fr_1.5fr]"} border-b border-border bg-[#171815] px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-muted`}>
          <div>Company / Role</div>
          <div>Source</div>
          <div>Status</div>
          <div>Reason / Output</div>
          {(normalized === "2" || normalized === "3" || normalized === "4") && <div>Act</div>}
        </div>
        {visibleRows.length > 0 ? (
          visibleRows.map((job) => (
            <Link key={job.job_id} href={jobHref(normalized, job)} className={`grid ${normalized === "2" || normalized === "3" || normalized === "4" ? "grid-cols-[1.2fr_0.8fr_0.8fr_1.5fr_80px]" : "grid-cols-[1.2fr_0.8fr_0.8fr_1.5fr]"} gap-3 border-b border-border/40 px-4 py-3 text-sm last:border-b-0 hover:bg-[#1a1b18]/70`}>
              <div className="min-w-0">
                <div className="truncate font-medium text-[#f5f6f4]">{job.company}</div>
                <div className="truncate text-xs text-muted">{job.title}</div>
              </div>
              <div className="text-xs text-muted">{job.source}</div>
              <div className={`text-xs font-mono ${statusStyle[phaseStatus(normalized, job)]}`}>{phaseStatus(normalized, job)}</div>
              <div className="truncate text-xs text-muted" title={reasonFor(normalized, job)}>{reasonFor(normalized, job)}</div>
              {normalized === "2" && (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  {vettingStatusOf(job.vetting) === "error" && (
                    <button
                      onClick={() => retryVet(job.job_id)}
                      disabled={inlineActing === job.job_id}
                      className="rounded border border-amber-800/60 px-1.5 py-0.5 text-[10px] font-mono text-amber-400 hover:bg-amber-950/30 transition disabled:opacity-40"
                      title="Retry AI vetting"
                    >↺</button>
                  )}
                  {job.vetting?.approved !== true && (
                    <button
                      onClick={() => inlineVet(job.job_id, true)}
                      disabled={inlineActing === job.job_id}
                      className="rounded border border-emerald-800/60 px-1.5 py-0.5 text-[10px] font-mono text-emerald-400 hover:bg-emerald-950/30 transition disabled:opacity-40"
                      title="Approve manually"
                    >✓</button>
                  )}
                  {job.vetting?.approved !== false && (
                    <button
                      onClick={() => inlineVet(job.job_id, false)}
                      disabled={inlineActing === job.job_id}
                      className="rounded border border-rose-800/60 px-1.5 py-0.5 text-[10px] font-mono text-rose-400 hover:bg-rose-950/30 transition disabled:opacity-40"
                      title="Reject manually"
                    >✗</button>
                  )}
                </div>
              )}
              {normalized === "3" && (
                <div className="flex items-center" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => inlineGenerate(job.job_id)}
                    disabled={inlineGenerating === job.job_id || job.generation?.status === "generated"}
                    className="rounded border border-border px-1.5 py-0.5 text-[10px] font-mono text-muted hover:text-accent hover:border-accent/60 transition disabled:opacity-40"
                    title={job.generation?.status === "generated" ? "Already generated" : "Generate"}
                  >
                    {inlineGenerating === job.job_id ? "…" : "⬇"}
                  </button>
                </div>
              )}
              {normalized === "4" && (
                <div className="flex items-center" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => inlineRefind(job.job_id)}
                    disabled={inlineRefinding === job.job_id}
                    className="rounded border border-border px-1.5 py-0.5 text-[10px] font-mono text-muted hover:text-accent hover:border-accent/60 transition disabled:opacity-40"
                    title="Re-find contact"
                  >
                    {inlineRefinding === job.job_id ? "…" : "↺"}
                  </button>
                </div>
              )}
            </Link>
          ))
        ) : (
          <div className="p-8 text-center text-sm text-muted">No jobs match these filters. yet.</div>
        )}
      </div>
    </section>
  );
}
