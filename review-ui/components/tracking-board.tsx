"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { JobSummary, TrackingStatus } from "@/lib/types";
import { toast } from "@/components/ui/toast";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SkeletonList } from "@/components/ui/skeleton";

const COLUMNS: { status: TrackingStatus; label: string; color: string }[] = [
  { status: "sent", label: "Sent", color: "text-blue-400" },
  { status: "replied", label: "Replied", color: "text-amber-400" },
  { status: "interview", label: "Interview", color: "text-purple-400" },
  { status: "offer", label: "Offer", color: "text-emerald-400" },
  { status: "rejected", label: "Rejected", color: "text-rose-400" },
];

export function TrackingBoard() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sendingFollowup, setSendingFollowup] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.jobs.list();
      setJobs(data.filter((j) => j.tracking?.status));
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const move = async (jobId: string, status: TrackingStatus) => {
    try {
      await api.jobs.updateTracking(jobId, status);
      setJobs((prev) =>
        prev.map((j) => j.job_id === jobId ? { ...j, tracking: { ...j.tracking, status } } : j)
      );
      toast(`Moved to ${status}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "update failed", "error");
    }
  };

  const sendFollowup = async (jobId: string) => {
    const email = window.prompt("Recipient email address:");
    if (!email) return;
    setSendingFollowup(jobId);
    try {
      await api.jobs.followup(jobId, email);
      toast("Follow-up sent", "success");
    } catch (e) {
      toast(e instanceof Error ? e.message : "follow-up failed", "error");
    } finally {
      setSendingFollowup(null);
    }
  };

  if (loading) return <SkeletonList rows={8} />;

  return (
    <div className="p-4 h-full flex flex-col gap-3">
      {error && <ErrorBanner message={error} onRetry={load} />}
      <div className="flex gap-3 flex-1 overflow-x-auto">
        {COLUMNS.map((col) => {
          const colJobs = jobs.filter((j) => j.tracking?.status === col.status);
          return (
            <div key={col.status} className="flex flex-col w-56 shrink-0 rounded border border-border bg-[#10110f]">
              <div className={`flex items-center justify-between px-3 py-2 border-b border-border`}>
                <span className={`font-mono text-xs font-semibold ${col.color}`}>{col.label}</span>
                <span className="font-mono text-[10px] text-muted">{colJobs.length}</span>
              </div>
              <div className="flex-1 overflow-y-auto divide-y divide-border/30 p-1 space-y-1">
                {colJobs.length === 0 ? (
                  <div className="py-6 text-center text-[10px] text-muted/50 font-mono">empty</div>
                ) : (
                  colJobs.map((job) => (
                    <div key={job.job_id} className="rounded bg-[#171815] p-2 space-y-1">
                      <div className="truncate text-xs font-semibold text-[#f5f6f4]">{job.company}</div>
                      <div className="truncate text-[10px] text-muted">{job.title}</div>
                      <div className="flex flex-wrap gap-1 pt-1">
                        {COLUMNS.filter((c) => c.status !== col.status).map((c) => (
                          <button key={c.status} onClick={() => move(job.job_id, c.status)}
                            className={`rounded border border-border px-1.5 py-0.5 text-[9px] font-mono text-muted hover:text-foreground transition`}>
                            → {c.label}
                          </button>
                        ))}
                        {col.status === "sent" && (
                          <button
                            onClick={() => sendFollowup(job.job_id)}
                            disabled={sendingFollowup === job.job_id}
                            className="rounded border border-sky-900/60 px-1.5 py-0.5 text-[9px] font-mono text-sky-400 hover:bg-sky-950/30 transition disabled:opacity-50"
                          >
                            {sendingFollowup === job.job_id ? "…" : "↩ Follow-up"}
                          </button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      {jobs.length === 0 && !error && (
        <EmptyState title="No tracked jobs" description="Jobs appear here after emails are sent." />
      )}
    </div>
  );
}
