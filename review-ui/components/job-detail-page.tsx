"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { fetchJson, api } from "@/lib/api-client";
import type { JobDetail, HistoryEvent, TrackingEntry, JobSummary } from "@/lib/types";
import { toast } from "@/components/ui/toast";
import { ComparePanel } from "./compare-panel";
import { EmailPanel } from "./email-panel";
import { JdPanel } from "./jd-panel";
import { PdfPanel } from "./pdf-panel";
import { ResumePanel } from "./resume-panel";
import { HistoryTimeline } from "./history-timeline";
import { EmailPreview } from "./email-preview";
import { ChevronLeft, ChevronRight, MoreHorizontal, Pencil, Check, X, FileDown } from "lucide-react";
import { CommandPalette } from "./command-palette";
import { PipelineStepper } from "./pipeline-stepper";

const sectionLinks = [
  { id: "jd", label: "JD" },
  { id: "curation", label: "Curation" },
  { id: "contact", label: "Contact" },
  { id: "resume", label: "Resume" },
  { id: "pdf", label: "PDF" },
  { id: "email", label: "Email" },
  { id: "metrics", label: "Metrics" },
  { id: "history", label: "History" },
];

function statusLabel(job: JobDetail, key: "gathered" | "curated" | "generated" | "review") {
  if (key === "gathered") return "Gathered";
  if (key === "curated") return job.vetting?.approved === true ? "Approved" : job.vetting?.approved === false ? "Filtered" : "Uncurated";
  if (key === "generated") return job.generation?.status === "generated" ? "Generated" : "Not Generated";
  return job.review?.status ?? "pending";
}

function hasData(value: unknown) {
  return Boolean(value && typeof value === "object" && Object.keys(value).length > 0);
}

type JobState = "uncurated" | "filtered" | "approved" | "generated" | "sent";

function deriveJobState(job: JobDetail, tracking: TrackingEntry | null): JobState {
  if (tracking?.status === "sent") return "sent";
  if (job.generation?.status === "generated") return "generated";
  if (job.vetting?.approved === true) return "approved";
  if (job.vetting?.approved === false) return "filtered";
  return "uncurated";
}

export function JobDetailPage({ jobId }: { jobId: string }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const fromPhase = searchParams.get("fromPhase");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const [tracking, setTracking] = useState<TrackingEntry | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [kebabOpen, setKebabOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [findingContact, setFindingContact] = useState(false);
  const [vetting, setVetting] = useState(false);
  const [genProvider, setGenProvider] = useState<"gemini" | "groq" | "both">("gemini");
  const [toEmailEditing, setToEmailEditing] = useState(false);
  const [toEmailInput, setToEmailInput] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);
  const kebabRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadJob();
    api.jobs.history(jobId).then(setHistory).catch(() => {});
    api.jobs.tracking(jobId).then((t) => { setTracking(t); setToEmailInput(t.to_email ?? ""); }).catch(() => {});
    api.jobs.list().then((jobs: JobSummary[]) => setJobIds(jobs.map((j) => j.job_id))).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (kebabRef.current && !kebabRef.current.contains(e.target as Node)) setKebabOpen(false);
    }
    function handleCmdK(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setPaletteOpen((o) => !o); }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleCmdK);
    return () => { document.removeEventListener("mousedown", handleClickOutside); document.removeEventListener("keydown", handleCmdK); };
  }, []);

  function loadJob() {
    fetchJson<JobDetail>(`/jobs/${jobId}`)
      .then((data) => { setJob(data); setError(""); })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load job detail"));
  }

  async function runPhase(phase: string, body?: Record<string, unknown>): Promise<{ ok: boolean; output: string }> {
    const { run_id } = await api.phases.start(phase, body ?? {});
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const run = await api.runs.get(run_id);
      if (run.status === "succeeded") {
        loadJob();
        return { ok: true, output: run.logs.join("\n") };
      }
      if (run.status === "failed") {
        return { ok: false, output: run.error ?? run.logs.join("\n") };
      }
    }
    return { ok: false, output: "Timed out waiting for phase" };
  }

  async function sendEmail(email: string) {
    setSending(true);
    try {
      await api.jobs.send(jobId, email);
      const updated = await api.jobs.tracking(jobId);
      setTracking(updated);
      setToEmailInput(updated.to_email ?? email);
      toast("Email sent", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Send failed", "error");
    } finally {
      setSending(false);
    }
  }

  async function sendFollowup(email: string) {
    setSending(true);
    try {
      await api.jobs.followup(jobId, email);
      const updated = await api.jobs.tracking(jobId);
      setTracking(updated);
      toast("Follow-up sent", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Follow-up failed", "error");
    } finally {
      setSending(false);
    }
  }

  async function findContact() {
    setFindingContact(true);
    try {
      const result = await runPhase("phase4-single", { jobId });
      if (!result.ok) toast(result.output || "Contact search failed", "error");
      else {
        loadJob();
        toast("Contact search complete", "success");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Contact search failed", "error");
    } finally {
      setFindingContact(false);
    }
  }

  async function vetJob(approved: boolean) {
    setVetting(true);
    try {
      await api.jobs.vet(jobId, approved);
      loadJob();
      toast(approved ? "Approved" : "Rejected", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Vet failed", "error");
    } finally {
      setVetting(false);
    }
  }

  async function saveToEmail() {
    if (!toEmailInput.trim()) return;
    setSavingEmail(true);
    try {
      const updated = await api.jobs.updateTrackingEmail(jobId, toEmailInput.trim());
      setTracking(updated);
      setToEmailEditing(false);
      toast("Recipient saved", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      setSavingEmail(false);
    }
  }

  const currentIdx = jobIds.indexOf(jobId);
  const prevId = currentIdx > 0 ? jobIds[currentIdx - 1] : null;
  const nextId = currentIdx >= 0 && currentIdx < jobIds.length - 1 ? jobIds[currentIdx + 1] : null;

  if (error) {
    return (
      <section className="min-h-full bg-background p-6">
        <div className="rounded-md border border-rose-900 bg-rose-950/30 p-4 text-sm text-rose-200">{error}</div>
      </section>
    );
  }

  if (!job) {
    return (
      <section className="min-h-full bg-background p-6">
        <div className="rounded-md border border-border bg-[#131412] p-6 text-sm text-muted">Loading job detail...</div>
      </section>
    );
  }

  const score = job.package?.match_score ?? null;
  const breadcrumb = `Overview / ${fromPhase ? `Phase ${fromPhase} / ` : ""}${job.company} ${job.title}`;
  const artifacts = [
    { label: "Curation artifact saved", present: hasData(job.vetting) },
    { label: "Generation artifact saved", present: hasData(job.generation) },
    { label: "Review artifact saved", present: hasData(job.review) },
  ];
  const recipientEmail = tracking?.to_email ?? "";

  return (
    <section className="min-h-full bg-background">
      <div className="sticky top-0 z-20 border-b border-border bg-[#10110f]/95 px-6 py-4 backdrop-blur">
        <div className="mb-3 flex items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{breadcrumb}</div>
            <h1 className="mt-1 truncate text-2xl font-semibold text-[#f5f6f4]">{job.company}</h1>
            <div className="mt-1 text-sm text-muted">{job.title}</div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {/* Prev/Next navigation */}
            {jobIds.length > 0 && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => prevId && router.push(`/jobs/${prevId}`)}
                  disabled={!prevId}
                  className="rounded border border-border p-1.5 text-muted hover:text-foreground hover:border-accent/60 transition disabled:opacity-30 disabled:cursor-not-allowed"
                  title="Previous job"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <span className="text-[10px] font-mono text-muted tabular-nums">
                  {currentIdx + 1}/{jobIds.length}
                </span>
                <button
                  onClick={() => nextId && router.push(`/jobs/${nextId}`)}
                  disabled={!nextId}
                  className="rounded border border-border p-1.5 text-muted hover:text-foreground hover:border-accent/60 transition disabled:opacity-30 disabled:cursor-not-allowed"
                  title="Next job"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {/* State-driven action group */}
            {(() => {
              const state = deriveJobState(job, tracking);
              if (state === "uncurated") return (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => vetJob(true)}
                    disabled={vetting}
                    className="rounded border border-emerald-800/60 px-3 py-2 font-mono text-xs text-emerald-400 hover:bg-emerald-950/30 transition disabled:opacity-50"
                  >
                    {vetting ? "…" : "✓ Approve"}
                  </button>
                  <button
                    onClick={() => vetJob(false)}
                    disabled={vetting}
                    className="rounded border border-rose-800/60 px-3 py-2 font-mono text-xs text-rose-400 hover:bg-rose-950/30 transition disabled:opacity-50"
                  >
                    {vetting ? "…" : "✗ Reject"}
                  </button>
                </div>
              );
              if (state === "filtered") return (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => vetJob(true)}
                    disabled={vetting}
                    className="rounded border border-emerald-800/60 px-3 py-2 font-mono text-xs text-emerald-400 hover:bg-emerald-950/30 transition disabled:opacity-50"
                  >
                    {vetting ? "…" : "✓ Approve"}
                  </button>
                  <button
                    onClick={() => {
                      setGenerating(true);
                      runPhase("phase2-single", { jobId })
                        .then((r) => { if (!r.ok) toast(r.output || "Re-vet failed", "error"); else toast("Re-vetted", "success"); })
                        .finally(() => setGenerating(false));
                    }}
                    disabled={generating}
                    className="rounded border border-amber-800/60 px-3 py-2 font-mono text-xs text-amber-400 hover:bg-amber-950/30 transition disabled:opacity-50"
                  >
                    {generating ? "Re-vetting…" : "↺ Re-vet"}
                  </button>
                </div>
              );
              if (state === "approved") return (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    {(["gemini", "groq", "both"] as const).map((p) => (
                      <label key={p} className="flex cursor-pointer items-center gap-1 font-mono text-[10px] text-muted hover:text-foreground">
                        <input
                          type="radio" name="genProvider" value={p}
                          checked={genProvider === p} onChange={() => setGenProvider(p)}
                          className="accent-accent"
                        />
                        {p}
                      </label>
                    ))}
                  </div>
                  <button
                    onClick={async () => {
                      setGenerating(true);
                      try {
                        const result = await runPhase("phase3", { jobId, provider: genProvider });
                        if (!result.ok) toast(result.output || "Generation failed", "error");
                        else toast("Application generated", "success");
                      } catch (e) {
                        toast(e instanceof Error ? e.message : "Generation failed", "error");
                      } finally {
                        setGenerating(false);
                      }
                    }}
                    disabled={generating}
                    className="rounded border border-border px-3 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <FileDown className={`h-3.5 w-3.5 ${generating ? "animate-pulse" : ""}`} />
                    {generating ? "Generating…" : "Generate"}
                  </button>
                </div>
              );
              if (state === "generated") return (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={async () => {
                      setGenerating(true);
                      try {
                        const result = await runPhase("phase3", { jobId, provider: genProvider });
                        if (!result.ok) toast(result.output || "Generation failed", "error");
                        else toast("Re-generated", "success");
                      } catch (e) {
                        toast(e instanceof Error ? e.message : "Generation failed", "error");
                      } finally {
                        setGenerating(false);
                      }
                    }}
                    disabled={generating}
                    className="rounded border border-border px-3 py-2 font-mono text-xs text-muted hover:text-foreground transition disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <FileDown className={`h-3.5 w-3.5 ${generating ? "animate-pulse" : ""}`} />
                    {generating ? "Generating…" : "↺ Re-gen"}
                  </button>
                  <button
                    onClick={findContact}
                    disabled={findingContact}
                    className="rounded border border-border px-3 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent disabled:opacity-50"
                    title="Find hiring-manager contact (Phase 4)"
                  >
                    {findingContact ? "Finding…" : job.contact ? "↺ Re-find Contact" : "⚲ Find Contact"}
                  </button>
                  <button
                    onClick={() => sendEmail(recipientEmail || window.prompt("Recipient email:", "") || "")}
                    disabled={sending}
                    className="rounded border border-border px-3 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-emerald-600/60 hover:text-emerald-400 disabled:opacity-50"
                  >
                    {sending ? "Sending…" : "✉ Send Email"}
                  </button>
                </div>
              );
              if (state === "sent") return (
                <button
                  onClick={() => sendFollowup(recipientEmail || window.prompt("Recipient email:", "") || "")}
                  disabled={sending}
                  className="rounded border border-border px-3 py-2 font-mono text-xs text-[#bfc2b9] transition hover:border-accent/60 hover:text-accent disabled:opacity-50"
                >
                  {sending ? "Sending…" : "↩ Follow-up"}
                </button>
              );
              return null;
            })()}

            {/* Recipient email inline edit */}
            {toEmailEditing ? (
              <div className="flex items-center gap-1">
                <input
                  autoFocus
                  type="email"
                  value={toEmailInput}
                  onChange={(e) => setToEmailInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") saveToEmail(); if (e.key === "Escape") setToEmailEditing(false); }}
                  className="rounded border border-border bg-[#171815] px-2 py-1 text-xs font-mono text-foreground focus:outline-none focus:border-accent/60 w-44"
                  placeholder="recipient@email.com"
                />
                <button onClick={saveToEmail} disabled={savingEmail} className="text-green-400 hover:text-green-300 transition p-1">
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button onClick={() => setToEmailEditing(false)} className="text-muted hover:text-foreground transition p-1">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setToEmailEditing(true)}
                className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs font-mono text-muted hover:text-foreground hover:border-accent/60 transition"
                title="Edit recipient email"
              >
                <span className="truncate max-w-[120px]">{recipientEmail || "Set recipient"}</span>
                <Pencil className="h-3 w-3 shrink-0" />
              </button>
            )}

            {/* Kebab overflow menu */}
            <div className="relative" ref={kebabRef}>
              <button
                onClick={() => setKebabOpen((o) => !o)}
                className="rounded border border-border p-1.5 text-muted hover:text-foreground hover:border-accent/60 transition"
                title="More actions"
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
              {kebabOpen && (
                <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-border bg-[#131412] shadow-xl z-30 overflow-hidden">
                  {fromPhase && (
                    <Link
                      href={`/phase/${fromPhase}`}
                      className="flex w-full items-center px-3 py-2 text-xs font-mono text-muted hover:bg-[#1a1b18] hover:text-foreground transition"
                      onClick={() => setKebabOpen(false)}
                    >
                      Back to Phase {fromPhase}
                    </Link>
                  )}
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex w-full items-center px-3 py-2 text-xs font-mono text-muted hover:bg-[#1a1b18] hover:text-foreground transition"
                    onClick={() => setKebabOpen(false)}
                  >
                    View Job Source
                  </a>
                  <button
                    onClick={() => { loadJob(); setKebabOpen(false); toast("Refreshed", "success"); }}
                    className="flex w-full items-center px-3 py-2 text-xs font-mono text-muted hover:bg-[#1a1b18] hover:text-foreground transition"
                  >
                    Refresh Data
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        <PipelineStepper job={job} />

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded border border-border bg-[#171815] px-2 py-1 font-mono text-muted">{job.source}</span>
          <span className="rounded border border-border bg-[#171815] px-2 py-1 font-mono text-muted">{job.location || "Location unknown"}</span>
          <span className="rounded border border-border bg-[#171815] px-2 py-1 font-mono text-[#f5f6f4]">{score !== null ? `${score}%` : "no score"}</span>
          {(["gathered", "curated", "generated", "review"] as const).map((key) => (
            <span key={key} className="rounded border border-border bg-[#171815] px-2 py-1 font-mono text-muted">
              {statusLabel(job, key)}
            </span>
          ))}
          {tracking?.status && (
            <span className={`rounded border px-2 py-1 font-mono text-xs ${
              tracking.status === "sent" ? "border-emerald-800/60 bg-emerald-950/20 text-emerald-400"
              : tracking.status === "replied" ? "border-sky-800/60 bg-sky-950/20 text-sky-400"
              : "border-border bg-[#171815] text-muted"
            }`}>
              {tracking.status}
            </span>
          )}
        </div>

        <nav className="mt-3 flex flex-wrap gap-2">
          {sectionLinks.map((item) => (
            <a key={item.id} href={`#${item.id}`} className="rounded border border-border px-3 py-1.5 text-xs font-mono text-[#bfc2b9] hover:border-accent/60 hover:text-accent">
              {item.label}
            </a>
          ))}
        </nav>
      </div>

      <div className="space-y-4 p-6">
        <section id="jd" className="scroll-mt-32 rounded-md border border-border bg-[#10110f] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Job Detail</h2>
            <a href={job.url} className="text-xs font-mono text-accent hover:text-accent-hover" target="_blank" rel="noreferrer">Source</a>
          </div>
          <div className="h-[360px] min-h-0">
            <JdPanel job={job} />
          </div>
        </section>

        <section id="curation" className="scroll-mt-32 rounded-md border border-border bg-[#131412] p-4">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Curation</h2>
          <p className="mt-3 text-sm leading-6 text-[#d7dacd]">{job.vetting?.reason || "No curation reason saved."}</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {artifacts.map((artifact) => (
              <div key={artifact.label} className="rounded border border-border bg-[#171815] px-3 py-2">
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted">{artifact.label}</div>
                <div className="mt-1 text-sm font-semibold text-[#f5f6f4]">{artifact.present ? "Present" : "Missing"}</div>
              </div>
            ))}
          </div>
        </section>

        <section id="contact" className="scroll-mt-32 rounded-md border border-border bg-[#131412] p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="font-mono text-xs uppercase tracking-wider text-muted">Contact</h2>
            <button
              onClick={findContact}
              disabled={findingContact}
              className="rounded border border-border px-2 py-1 font-mono text-[10px] text-muted hover:text-accent hover:border-accent/60 transition disabled:opacity-50"
            >
              {findingContact ? "Searching…" : job.contact ? "↺ Re-find Contact" : "⚲ Find Contact"}
            </button>
          </div>
          {job.contact ? (
            <div className="grid gap-3 sm:grid-cols-2 text-sm">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-1">Name</div>
                <div className="text-[#f5f6f4]">{[job.contact.first_name, job.contact.last_name].filter(Boolean).join(" ") || "—"}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-1">Title</div>
                <div className="text-[#f5f6f4]">{job.contact.title || "—"}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-1">Email</div>
                <div className="text-[#f5f6f4]">{job.contact.email || "—"}</div>
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-1">LinkedIn</div>
                {job.contact.linkedin_url
                  ? <a href={job.contact.linkedin_url} target="_blank" rel="noreferrer" className="text-accent hover:underline truncate block">{job.contact.linkedin_url}</a>
                  : <div className="text-[#f5f6f4]">—</div>}
              </div>
              <div>
                <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-1">Discovery Method</div>
                <div className="text-muted text-xs">{job.contact.discovery_method || "—"}</div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">No contact found yet. Run Phase 4 or click Re-find Contact.</p>
          )}
        </section>

        <section id="resume" className="scroll-mt-32 rounded-md border border-border bg-[#10110f] p-4">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-muted">Resume</h2>
          <div className="h-[420px] min-h-0">
            <ResumePanel job={job} />
          </div>
        </section>

        <section id="pdf" className="scroll-mt-4 rounded-md border border-border bg-[#10110f] p-4">
          <h2 className="mb-3 text-lg font-semibold text-[#f5f6f4]">PDF Preview</h2>
          <div className="h-[min(240px,calc(100vh-260px))] min-h-[160px]">
            <PdfPanel job={job} onRunPhase={runPhase} />
          </div>
        </section>

        <section id="email" className="scroll-mt-32 rounded-md border border-border bg-[#10110f] p-4">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-muted">Cold Email</h2>
          <div className="h-[340px] min-h-0">
            <EmailPanel
              job={job}
              onBodySaved={(newBody) => {
                setJob((prev) => prev ? { ...prev, package: prev.package ? { ...prev.package, email_body: newBody } : prev.package } : prev);
              }}
            />
          </div>
        </section>

        <section id="metrics" className="scroll-mt-32 rounded-md border border-border bg-[#10110f] p-4">
          <h2 className="mb-3 text-lg font-semibold text-[#f5f6f4]">ATS Metrics</h2>
          <div className="h-[420px] min-h-0">
            <ComparePanel job={job} onJobUpdate={loadJob} />
          </div>
        </section>

        <section id="history" className="scroll-mt-32 rounded-md border border-border bg-[#10110f] p-4 space-y-4">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted">History</h2>
          <HistoryTimeline events={history} />
          {job.package?.email_body && (
            <div className="pt-2">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted/60 mb-2">Email Preview</div>
              <EmailPreview job={job} />
            </div>
          )}
        </section>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </section>
  );
}
