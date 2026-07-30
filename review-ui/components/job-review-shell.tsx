"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiUrl, fetchJson } from "@/lib/api-client";
import type { JobDetail, JobSummary, RunState } from "@/lib/types";
import { JobTable } from "./job-table";
import { JdPanel } from "./jd-panel";
import { ResumePanel } from "./resume-panel";
import { PdfPanel } from "./pdf-panel";
import { EmailPanel } from "./email-panel";
import { ComparePanel } from "./compare-panel";
import { ActionRail } from "./action-rail";
import { CheckCircle, Clock, Filter, Play, PlusCircle, RotateCw } from "lucide-react";

type Tab = "jd" | "resume" | "pdf" | "email" | "compare";
type PhaseRunResult = { ok: boolean; output: string; result?: PhaseResult | null };
type PhaseResult = Record<string, unknown> & { phase?: string };

function phaseTitle(result: PhaseResult) {
  const phase = String(result.phase ?? "phase");
  if (phase === "phase1") return "Phase 1 Gather";
  if (phase === "phase2") return "Phase 2 Vet";
  if (phase === "phase3") return "Phase 3 Generate";
  if (phase === "phase3-all") return "Phase 3 Generate All";
  if (phase === "phase4-review") return "Phase 4 Review";
  if (phase === "safe-prepare") return "Safe Pipeline";
  return phase;
}

function phaseSummaryEntries(result: PhaseResult) {
  const keys = [
    "written",
    "reviewed",
    "approved",
    "rejected",
    "generated",
    "ready",
    "selected",
    "page_count",
    "numeric_bullets",
    "total_bullets",
  ];
  return keys
    .filter((key) => result[key] !== undefined)
    .map((key) => [key.replace(/_/g, " "), String(result[key])] as const);
}

export function JobReviewShell() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [tab, setTab] = useState<Tab>("jd");
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [runningPhase1, setRunningPhase1] = useState<boolean>(false);
  const [runningPhase2, setRunningPhase2] = useState<boolean>(false);
  const [activePhase, setActivePhase] = useState<string>("");
  const [runLog, setRunLog] = useState<string>("");
  const [runLogOpen, setRunLogOpen] = useState<boolean>(false);
  const [phaseResults, setPhaseResults] = useState<PhaseResult[]>([]);
  const [runningPipeline, setRunningPipeline] = useState<boolean>(false);
  const logRef = useRef<HTMLPreElement | null>(null);
  
  // Real-time Clock logic inspired by the 11:37 AM Time in the image
  const [timeStr, setTimeStr] = useState<string>("");
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true
      }));
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [runLog]);

  async function refreshJobs() {
    try {
      const data = await fetchJson<JobSummary[]>("/jobs");
      setJobs(data);
      if (data.length > 0) {
        // Keep existing selectedId if it exists in data, otherwise default to first
        const exists = data.some((j: JobSummary) => j.job_id === selectedId);
        if (!selectedId || !exists) {
          setSelectedId(data[0].job_id);
        }
      } else {
        setSelectedId("");
        setDetail(null);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to refresh jobs";
      console.error("Failed to refresh jobs", e);
      setRunLogOpen(true);
      setRunLog(`[ui-error] ${message}\n`);
      setJobs([]);
      setSelectedId("");
      setDetail(null);
    }
  }

  useEffect(() => {
    refreshJobs();
  }, []);

  async function refreshDetail(jobId = selectedId) {
    if (!jobId) {
      setDetail(null);
      return;
    }
    setIsLoadingDetail(true);
    try {
      const data = await fetchJson<JobDetail>(`/jobs/${jobId}`);
      setDetail(data);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to refresh job detail";
      console.error("Failed to refresh job detail", e);
      setRunLogOpen(true);
      setRunLog((prev) => `${prev}${prev ? "\n" : ""}[ui-error] ${message}\n`);
      setDetail(null);
    } finally {
      setIsLoadingDetail(false);
    }
  }

  useEffect(() => {
    refreshDetail(selectedId);
  }, [selectedId]);

  async function refreshCurrentView() {
    await refreshJobs();
    await refreshDetail();
  }

  async function runBackendRunWithLogs(
    startPath: string,
    displayName: string,
    body: Record<string, unknown> = {},
    options: { append?: boolean } = {}
  ): Promise<PhaseRunResult> {
    setActivePhase(displayName);
    setRunLogOpen(true);
    if (options.append) {
      setRunLog((prev) => `${prev}${prev ? "\n" : ""}--- ${displayName} ---\n`);
    } else {
      setRunLog("");
      setPhaseResults([]);
    }

    let output = "";
    const appendLog = (chunk: string) => {
      output += chunk;
      setRunLog((prev) => prev + chunk);
    };

    try {
      const started = await fetchJson<{ run_id: string; phase: string; status: string }>(startPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      appendLog(`[run] ${started.phase} ${started.run_id} started\n`);

      const streamedRun = await new Promise<RunState>((resolve, reject) => {
        const events = new EventSource(apiUrl(`/runs/${started.run_id}/events`));
        const close = () => events.close();

        events.addEventListener("log", (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data) as { message?: string };
            appendLog(`${payload.message ?? ""}\n`);
          } catch {
            appendLog(`${(event as MessageEvent).data}\n`);
          }
        });

        events.addEventListener("done", (event) => {
          close();
          resolve(JSON.parse((event as MessageEvent).data) as RunState);
        });

        events.addEventListener("error", () => {
          close();
          reject(new Error("Run event stream failed"));
        });
      });

      const finalRun = await fetchJson<RunState>(`/runs/${started.run_id}`).catch(() => streamedRun);
      const ok = finalRun.status === "succeeded";
      const result = (finalRun.result ?? streamedRun.result ?? null) as PhaseResult | null;
      if (result) {
        setPhaseResults((prev) => [...prev, result]);
      }
      if (!ok) {
        appendLog(`[failed] ${finalRun.error ?? "Run failed"}\n`);
      }
      await refreshCurrentView();
      return { ok, output, result };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Phase command failed";
      appendLog(`\n[ui-error] ${message}\n`);
      return { ok: false, output };
    } finally {
      setActivePhase("");
    }
  }

  async function runPhaseWithLogs(
    phaseName: string,
    body: Record<string, unknown> = {},
    options: { append?: boolean } = {}
  ): Promise<PhaseRunResult> {
    return runBackendRunWithLogs(`/phases/${phaseName}`, phaseName, body, options);
  }

  // Phase Runners
  async function runGatherPhase1() {
    if (runningPhase1) return;
    setRunningPhase1(true);
    try {
      await runPhaseWithLogs("phase1", { max: 10 });
    } catch (e) {
      console.error(e);
    } finally {
      setRunningPhase1(false);
    }
  }

  async function runVetPhase2() {
    if (runningPhase2) return;
    setRunningPhase2(true);
    try {
      await runPhaseWithLogs("phase2", { max: 10 });
    } catch (e) {
      console.error(e);
    } finally {
      setRunningPhase2(false);
    }
  }

  async function runGeneratePhase3All() {
    if (activePhase) return;
    await runPhaseWithLogs("phase3-all", { limit: 20 });
  }

  async function runSafePipeline() {
    if (activePhase || runningPipeline) return;
    setRunningPipeline(true);
    setRunLog("");
    setPhaseResults([]);
    setRunLogOpen(true);
    try {
      await runBackendRunWithLogs(
        "/pipelines/safe-prepare",
        "safe-prepare",
        { max: 10, limit: 20 },
        { append: true }
      );
    } finally {
      setRunningPipeline(false);
    }
  }

  async function openPhase4Review() {
    setRunLogOpen(true);
    setRunLog("");
    try {
      const reviewJobs = await fetchJson<JobSummary[]>("/review-queue");
      const selected = reviewJobs[0];
      setPhaseResults([{
        phase: "phase4-review",
        ready: reviewJobs.length,
        selected: selected?.job_id ?? "none",
      }]);

      if (selected) {
        setSelectedId(selected.job_id);
        setTab("compare");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Review queue failed";
      setRunLog(`[ui-error] ${message}\n`);
    }
  }

  const tabLabels: Record<Tab, string> = {
    jd: "Job Spec (JD)",
    resume: "Tailored Bullets",
    pdf: "PDF Preview",
    email: "Cold Email",
    compare: "ATS Metrics"
  };
  const approvedJobList = jobs.filter((job) => job.vetting?.approved === true);
  const filteredJobList = jobs.filter((job) => job.vetting?.approved === false);
  const generatedJobList = jobs.filter((job) => job.generation?.status === "generated");
  const reviewQueueList = generatedJobList.filter((job) => (job.review?.status ?? "pending") === "pending");
  const approvedJobs = approvedJobList.length;
  const generatedJobs = generatedJobList.length;
  const controlsDisabled = runningPhase1 || runningPhase2 || Boolean(activePhase) || runningPipeline;
  const curatedJobs = approvedJobList.length + filteredJobList.length;
  const curationRows = [...approvedJobList.slice(0, 3), ...filteredJobList.slice(0, 3)].slice(0, 6);

  return (
    <div className="flex min-h-full flex-col">
      {/* Sub-Header bar for metrics, phase execution controls, and clock */}
      <div className="bg-[#131412] border-b border-border px-6 py-3 flex justify-between items-center gap-4 shrink-0">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={runSafePipeline}
            disabled={controlsDisabled}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-accent bg-accent text-accent-foreground text-xs font-mono font-semibold hover:bg-accent-hover active:scale-[0.98] transition disabled:opacity-50"
          >
            <Play className={`h-3 w-3 ${runningPipeline ? "animate-pulse" : ""}`} />
            <span>{runningPipeline ? "Running 1 -> 2 -> 3..." : "Run 1 -> 2 -> 3"}</span>
          </button>

          <button
            onClick={runGatherPhase1}
            disabled={controlsDisabled}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-[#bfc2b9] hover:bg-[#232421] active:scale-[0.98] transition disabled:opacity-50"
          >
            <Play className={`h-3 w-3 ${runningPhase1 ? "animate-pulse" : ""}`} />
            <span>{runningPhase1 ? "Gathering..." : "Phase 1 Gather"}</span>
          </button>
          
          <button
            onClick={runVetPhase2}
            disabled={controlsDisabled}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-[#bfc2b9] hover:bg-[#232421] active:scale-[0.98] transition disabled:opacity-50"
          >
            <Play className={`h-3 w-3 ${runningPhase2 ? "animate-pulse" : ""}`} />
            <span>{runningPhase2 ? "Vetting..." : `Phase 2 Vet (${approvedJobs} approved)`}</span>
          </button>

          <button
            onClick={runGeneratePhase3All}
            disabled={controlsDisabled || approvedJobs === 0}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-[#bfc2b9] hover:bg-[#232421] active:scale-[0.98] transition disabled:opacity-50"
          >
            <Play className={`h-3 w-3 ${activePhase === "phase3-all" ? "animate-pulse" : ""}`} />
            <span>Phase 3 Generate All</span>
          </button>

          <button
            onClick={openPhase4Review}
            disabled={controlsDisabled || generatedJobs === 0}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-[#bfc2b9] hover:bg-[#232421] active:scale-[0.98] transition disabled:opacity-50"
          >
            <PlusCircle className="h-3 w-3" />
            <span>{`Phase 4 Review (${generatedJobs})`}</span>
          </button>

          <button
            disabled
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-muted opacity-50"
            title="Phase 5 apply stays disabled until a reviewed application is explicitly approved."
          >
            <Play className="h-3 w-3" />
            <span>Phase 5 Apply Later</span>
          </button>
          
          <button
            onClick={refreshJobs}
            className="p-1.5 rounded-lg border border-border bg-[#181916] text-xs font-mono text-[#bfc2b9] hover:bg-[#232421] transition"
            title="Refresh jobs list"
          >
            <RotateCw className="h-3 w-3" />
          </button>
        </div>

        {/* Real-time Clock displaying styled Time matching the image exactly */}
        <div className="flex items-center gap-2 font-mono text-muted text-xs bg-[#171815] px-3 py-1.5 rounded-lg border border-border/40 select-none">
          <Clock className="h-3.5 w-3.5 text-accent animate-pulse" />
          <span className="text-[#bfc2b9] font-medium">{timeStr}</span>
          <span className="opacity-50 text-[10px]">TIME</span>
        </div>
      </div>

      <section className="border-b border-border bg-[#10110f] px-6 py-3 shrink-0">
        <div className="grid gap-3 xl:grid-cols-[1.15fr_1fr]">
          <div className="grid gap-2 sm:grid-cols-4">
            <div className="rounded-md border border-border bg-[#171815] p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Curation Done</div>
              <div className="mt-1 text-xl font-semibold text-[#f5f6f4]">{jobs.length}</div>
              <div className="mt-1 text-[11px] text-muted">Phase 1 gathered</div>
            </div>
            <div className="rounded-md border border-border bg-[#171815] p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Phase 2 Curated</div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-xl font-semibold text-emerald-300">{approvedJobList.length}</span>
                <span className="text-[11px] font-mono text-emerald-300">Approved</span>
              </div>
              <div className="mt-1 flex items-baseline gap-3">
                <span className="text-lg font-semibold text-rose-300">{filteredJobList.length}</span>
                <span className="text-[11px] font-mono text-rose-300">Filtered</span>
              </div>
            </div>
            <div className="rounded-md border border-border bg-[#171815] p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Phase 3 Generated</div>
              <div className="mt-1 text-xl font-semibold text-[#f5f6f4]">{generatedJobList.length}</div>
              <div className="mt-1 text-[11px] text-muted">resume/email/PDF ready</div>
              <div className="mt-2 space-y-1">
                {generatedJobList.slice(0, 2).map((job) => (
                  <Link
                    key={job.job_id}
                    href={`/jobs/${job.job_id}#metrics`}
                    className="block truncate text-[11px] font-mono text-accent hover:text-accent-hover"
                  >
                    {job.company} metrics
                  </Link>
                ))}
              </div>
            </div>
            <div className="rounded-md border border-border bg-[#171815] p-3">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">Phase 4 Review</div>
              <div className="mt-1 text-xl font-semibold text-[#f5f6f4]">{reviewQueueList.length}</div>
              <div className="mt-1 text-[11px] text-muted">waiting for decision</div>
            </div>
          </div>

          <div className="rounded-md border border-border bg-[#171815] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted">What Curation Did</div>
              <div className="text-[10px] font-mono text-muted">{curatedJobs}/{jobs.length} decided</div>
            </div>
            {curationRows.length > 0 ? (
              <div className="grid gap-1.5">
                {curationRows.map((job) => {
                  const approved = job.vetting?.approved === true;
                  const reason = job.vetting?.reason || "No curation reason saved";
                  return (
                    <Link key={job.job_id} href={`/jobs/${job.job_id}#curation`} className="grid grid-cols-[90px_1fr] gap-2 rounded border border-border/50 bg-black/10 px-2 py-1.5 hover:border-accent/50 hover:bg-[#232421]/40">
                      <div className={`flex items-center gap-1 text-[10px] font-mono uppercase ${approved ? "text-emerald-300" : "text-rose-300"}`}>
                        {approved ? <CheckCircle className="h-3 w-3" /> : <Filter className="h-3 w-3" />}
                        <span>{approved ? "Approved" : "Filtered"}</span>
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-[12px] font-medium text-[#f5f6f4]" title={`${job.company} - ${job.title}`}>
                          {job.company} - {job.title}
                        </div>
                        <div className="truncate text-[11px] text-muted" title={reason}>{reason}</div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className="rounded border border-dashed border-border/60 px-2 py-3 text-[11px] text-muted">
                Run Phase 1 and Phase 2 to see approved and filtered jobs here.
              </div>
            )}
          </div>
        </div>
      </section>

      {runLogOpen ? (
        <section className="border-b border-border bg-[#10110f] px-6 py-3 shrink-0">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${activePhase ? "animate-pulse bg-accent" : runLog.includes("[failed]") || runLog.includes("[ui-error]") ? "bg-rose-400" : "bg-emerald-400"}`} />
              <span className="font-mono text-[11px] uppercase tracking-wider text-[#bfc2b9]">
                {activePhase ? `Running ${activePhase}` : "Last Run Log"}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setRunLogOpen(false)}
              className="rounded border border-border px-2 py-1 text-[10px] font-mono text-muted hover:text-foreground"
            >
              Hide
            </button>
          </div>
          {phaseResults.length > 0 ? (
            <div className="mb-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {phaseResults.map((result, index) => (
                <div key={`${result.phase ?? "phase"}-${index}`} className="rounded-lg border border-border bg-[#171815] p-3">
                  <div className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted">
                    {phaseTitle(result)}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {phaseSummaryEntries(result).map(([label, value]) => (
                      <div key={label}>
                        <div className="font-mono text-[9px] uppercase text-muted">{label}</div>
                        <div className="truncate text-sm font-semibold text-[#f5f6f4]" title={value}>{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          <pre
            ref={logRef}
            className="max-h-40 overflow-auto rounded-lg border border-border bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-[#d7dacd] whitespace-pre-wrap"
          >
            {runLog || "Starting backend run..."}
          </pre>
        </section>
      ) : null}

      <div className="grid h-[min(500px,calc(100vh-310px))] min-h-[300px] shrink-0 grid-cols-[360px_1fr_280px] overflow-hidden">
        {/* Left column: Job Table */}
        <JobTable jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} />

        {/* Middle column: Detail Panels with Tab bar */}
        <section className="min-w-0 p-6 flex flex-col h-full bg-background overflow-hidden">
          {/* Custom Tabs Navigation inspired by horizontal minimal text nav in the image */}
          <div className="mb-6 flex gap-2 shrink-0 border-b border-border/30 pb-3">
            {(["jd", "resume", "pdf", "email", "compare"] as Tab[]).map((item) => (
              <button
                key={item}
                onClick={() => setTab(item)}
                className={`rounded-lg px-4 py-2 text-xs font-mono tracking-wide transition border ${
                  tab === item
                    ? "border-accent text-accent bg-accent/5 font-semibold"
                    : "border-transparent text-muted hover:text-foreground hover:border-border/40"
                }`}
              >
                {tabLabels[item]}
              </button>
            ))}
          </div>

          {/* Tab Panel Content */}
          <div className="flex-1 min-h-0 overflow-hidden relative">
            {isLoadingDetail ? (
              <div className="absolute inset-0 flex items-center justify-center bg-background/50 backdrop-blur-sm z-10">
                <div className="flex flex-col items-center gap-3">
                  <div className="w-8 h-8 rounded-full border-2 border-border border-t-accent animate-spin"></div>
                  <span className="text-xs font-mono text-muted">Loading details...</span>
                </div>
              </div>
            ) : null}

            {!detail ? (
              <div className="h-full flex flex-col items-center justify-center border border-dashed border-border rounded-xl bg-[#131412] p-8 text-center">
                <PlusCircle className="h-8 w-8 text-muted mb-2 stroke-[1.5]" />
                <h3 className="text-sm font-medium text-foreground mb-1">No target selected</h3>
                <p className="text-xs text-muted max-w-xs">
                  Please select a job application target from the sidebar or click "Run Phase 1 Gather" to scrape new listings.
                </p>
              </div>
            ) : (
              <>
                {tab === "jd" && <JdPanel job={detail} />}
                {tab === "resume" && <ResumePanel job={detail} />}
                {tab === "pdf" && <PdfPanel job={detail} />}
                {tab === "email" && <EmailPanel job={detail} />}
                {tab === "compare" && <ComparePanel job={detail} />}
              </>
            )}
          </div>
        </section>

        {/* Right column: Action Rail */}
        <ActionRail job={detail} onChanged={refreshCurrentView} onRunPhase={runPhaseWithLogs} />
      </div>
    </div>
  );
}
