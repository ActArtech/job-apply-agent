"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api-client";
import type { JobSummary } from "@/lib/types";
import { toast } from "@/components/ui/toast";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SkeletonList } from "@/components/ui/skeleton";

const PAGE_SIZE = 20;

export function ReviewQueue() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [filtered, setFiltered] = useState<JobSummary[]>([]);
  const [cursor, setCursor] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [autoSend, setAutoSend] = useState(false);
  const [confirmSend, setConfirmSend] = useState<null | {
    preview: Record<string, { ok: boolean; error?: string; to_email?: string }>;
    dryRun: boolean;
  }>(null);
  const [sendingBulk, setSendingBulk] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [data, s] = await Promise.all([api.jobs.list(), api.settings.get()]);
      setJobs(data);
      setAutoSend(s.auto_send ?? false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const q = search.toLowerCase();
    setFiltered(
      jobs.filter((j) => {
        const matchSearch = !q || j.company.toLowerCase().includes(q) || j.title.toLowerCase().includes(q);
        const matchStatus = statusFilter === "all" || (j.review?.status ?? "pending") === statusFilter;
        return matchSearch && matchStatus;
      })
    );
    setCursor(0);
  }, [jobs, search, statusFilter]);

  const page = filtered.slice(cursor, cursor + PAGE_SIZE);
  const current = page[0] ?? null;

  const act = useCallback(async (jobId: string, status: "approved" | "rejected" | "needs_regen") => {
    try {
      await api.jobs.review(jobId, status);
      toast(status === "approved" ? "Approved" : status === "rejected" ? "Rejected" : "Marked for regen");
      setJobs((prev) => prev.map((j) => j.job_id === jobId ? { ...j, review: { status, notes: "" } } : j));
      if (status === "approved" && autoSend) {
        try {
          const r = await api.jobs.bulkSend([jobId]);
          const res = r.results[jobId];
          if (res?.ok) toast(`Auto-sent to ${res.to_email}`, "success");
          else toast(`Auto-send failed: ${res?.error ?? "unknown"}`, "error");
        } catch (e) {
          toast(e instanceof Error ? e.message : "auto-send failed", "error");
        }
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "action failed", "error");
    }
  }, [autoSend]);

  const bulkAct = async (status: "approved" | "rejected") => {
    const count = selected.size;
    await Promise.all([...selected].map((id) => act(id, status)));
    setSelected(new Set());
    toast(`Bulk ${status} (${count} jobs)`);
  };

  const openBulkSend = async () => {
    if (selected.size === 0) return;
    setSendingBulk(true);
    try {
      const preview = await api.jobs.bulkSend([...selected], true);
      setConfirmSend({ preview: preview.results, dryRun: false });
    } catch (e) {
      toast(e instanceof Error ? e.message : "preview failed", "error");
    } finally {
      setSendingBulk(false);
    }
  };

  const confirmBulkSend = async () => {
    if (!confirmSend) return;
    setSendingBulk(true);
    try {
      const result = await api.jobs.bulkSend([...selected], confirmSend.dryRun);
      let failures = 0;
      for (const [id, res] of Object.entries(result.results)) {
        if (!res.ok) {
          const job = jobs.find((j) => j.job_id === id);
          toast(`${job?.company ?? id}: ${res.error}`, "error");
          failures++;
        }
      }
      if (!confirmSend.dryRun) {
        toast(`Sent ${result.sent} email${result.sent !== 1 ? "s" : ""}${failures > 0 ? `, ${failures} failed` : ""}`, result.sent > 0 ? "success" : "error");
        setSelected(new Set());
        await load();
      } else {
        toast(`Dry run: would send ${result.sent} email${result.sent !== 1 ? "s" : ""}`);
      }
      setConfirmSend(null);
    } catch (e) {
      toast(e instanceof Error ? e.message : "send failed", "error");
    } finally {
      setSendingBulk(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!current || (e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key === "a") act(current.job_id, "approved");
      if (e.key === "r") act(current.job_id, "rejected");
      if (e.key === "g") act(current.job_id, "needs_regen");
      if (e.key === "j") setCursor((c) => Math.min(c + 1, filtered.length - 1));
      if (e.key === "k") setCursor((c) => Math.max(c - 1, 0));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [current, act, filtered.length]);

  if (loading) return <SkeletonList rows={8} />;

  return (
    <div className="flex h-full">
      {confirmSend && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-lg border border-border bg-[#131412] p-6 shadow-xl">
            <h2 className="mb-4 text-base font-semibold text-[#f5f6f4]">Confirm Bulk Send</h2>
            <div className="max-h-60 overflow-auto space-y-1 mb-4">
              {Object.entries(confirmSend.preview).map(([id, res]) => {
                const job = jobs.find((j) => j.job_id === id);
                return (
                  <div key={id} className={`flex items-center justify-between rounded border px-3 py-2 text-xs ${res.ok ? "border-border text-[#f5f6f4]" : "border-rose-900/60 text-rose-400"}`}>
                    <span className="font-semibold">{job?.company ?? id}</span>
                    <span className="font-mono text-muted truncate ml-2">{res.ok ? res.to_email : res.error}</span>
                  </div>
                );
              })}
            </div>
            <label className="flex items-center gap-2 text-xs text-[#bfc2b9] mb-5">
              <input type="checkbox" checked={confirmSend.dryRun}
                onChange={(e) => setConfirmSend({ ...confirmSend, dryRun: e.target.checked })}
                className="accent-accent" />
              Dry run (no emails sent)
            </label>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmSend(null)}
                className="rounded border border-border px-4 py-2 font-mono text-xs text-muted hover:text-foreground">
                Cancel
              </button>
              <button onClick={confirmBulkSend} disabled={sendingBulk}
                className="rounded bg-accent px-4 py-2 font-mono text-xs font-semibold text-accent-foreground hover:bg-accent-hover disabled:opacity-50">
                {sendingBulk ? "Sending…" : confirmSend.dryRun ? "Dry Run" : `Send ${Object.values(confirmSend.preview).filter((r) => r.ok).length}`}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Left: job list */}
      <aside className="w-72 shrink-0 border-r border-border flex flex-col">
        <div className="p-3 border-b border-border space-y-2">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..."
            className="w-full rounded border border-border bg-[#171815] px-3 py-1.5 text-xs text-foreground focus:outline-none" />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full rounded border border-border bg-[#171815] px-2 py-1.5 text-xs text-foreground focus:outline-none">
            {["all", "pending", "approved", "rejected", "needs_regen"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {selected.size > 0 && (
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => bulkAct("approved")} className="flex-1 rounded border border-emerald-800 py-1 text-[10px] font-mono text-emerald-400 hover:bg-emerald-950/30">
                Approve {selected.size}
              </button>
              <button onClick={() => bulkAct("rejected")} className="flex-1 rounded border border-rose-800 py-1 text-[10px] font-mono text-rose-400 hover:bg-rose-950/30">
                Reject {selected.size}
              </button>
              <button onClick={openBulkSend} disabled={sendingBulk}
                className="flex-1 rounded border border-sky-800 py-1 text-[10px] font-mono text-sky-400 hover:bg-sky-950/30 disabled:opacity-50">
                {sendingBulk ? "…" : `✉ Send ${selected.size}`}
              </button>
            </div>
          )}
        </div>
        {error && <ErrorBanner message={error} onRetry={load} />}
        <div className="flex-1 overflow-y-auto divide-y divide-border/30">
          {filtered.length === 0 ? (
            <EmptyState title="No jobs" description="Adjust filters or run Phase 1 to gather jobs." />
          ) : (
            page.map((job, i) => (
              <div key={job.job_id}
                className={`flex items-start gap-2 p-3 cursor-pointer hover:bg-[#1a1b18]/60 ${i === 0 ? "bg-[#181916] border-l-2 border-accent" : ""}`}
                onClick={() => setCursor(cursor - (cursor % PAGE_SIZE) + i)}>
                <input type="checkbox" checked={selected.has(job.job_id)}
                  onChange={(e) => { const s = new Set(selected); e.target.checked ? s.add(job.job_id) : s.delete(job.job_id); setSelected(s); }}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-0.5 accent-accent" />
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold text-[#f5f6f4]">{job.company}</div>
                  <div className="truncate text-[10px] text-muted">{job.title}</div>
                  <div className="mt-1 font-mono text-[10px] text-muted">{job.review?.status ?? "pending"}</div>
                </div>
                {job.package?.match_score && (
                  <span className="shrink-0 font-mono text-[10px] text-accent">{job.package.match_score}%</span>
                )}
              </div>
            ))
          )}
        </div>
        <div className="border-t border-border flex items-center justify-between px-3 py-2 text-[10px] font-mono text-muted">
          <button onClick={() => setCursor(Math.max(0, cursor - PAGE_SIZE))} disabled={cursor === 0} className="disabled:opacity-30">← Prev</button>
          <span>{Math.min(cursor + 1, filtered.length)}–{Math.min(cursor + PAGE_SIZE, filtered.length)} of {filtered.length}</span>
          <button onClick={() => setCursor(Math.min(filtered.length - 1, cursor + PAGE_SIZE))} disabled={cursor + PAGE_SIZE >= filtered.length} className="disabled:opacity-30">Next →</button>
        </div>
      </aside>

      {/* Right: detail + actions */}
      <main className="flex-1 flex flex-col">
        {current ? (
          <>
            <div className="border-b border-border bg-[#131412] px-6 py-2 flex items-center gap-6 text-[10px] font-mono text-muted">
              <span>[A] Approve</span><span>[R] Reject</span><span>[G] Regen</span><span>[J/K] Navigate</span>
              <span className="opacity-40">|</span>
              <span>{cursor + 1} / {filtered.length}</span>
            </div>
            <div className="border-b border-border px-6 py-3 flex items-center gap-3">
              <button onClick={() => act(current.job_id, "approved")}
                className="rounded border border-emerald-800 px-4 py-1.5 text-xs font-mono text-emerald-400 hover:bg-emerald-950/30 transition">
                Approve
              </button>
              <button onClick={() => act(current.job_id, "rejected")}
                className="rounded border border-rose-800 px-4 py-1.5 text-xs font-mono text-rose-400 hover:bg-rose-950/30 transition">
                Reject
              </button>
              <button onClick={() => act(current.job_id, "needs_regen")}
                className="rounded border border-amber-800 px-4 py-1.5 text-xs font-mono text-amber-400 hover:bg-amber-950/30 transition">
                Needs Regen
              </button>
              <Link href={`/jobs/${current.job_id}?fromPhase=review`}
                className="ml-auto rounded border border-border px-3 py-1.5 text-xs font-mono text-muted hover:text-foreground transition">
                Full Detail →
              </Link>
            </div>
            <div className="flex-1 overflow-auto p-6 space-y-4">
              <div>
                <h1 className="text-xl font-semibold text-[#f5f6f4]">{current.company}</h1>
                <div className="text-sm text-muted mt-1">{current.title}</div>
                <div className="mt-2 flex gap-2 text-[10px] font-mono text-muted">
                  <span>{current.source}</span>
                  <span>·</span>
                  <span>{current.location ?? "?"}</span>
                  {current.package?.match_score && <><span>·</span><span className="text-accent">{current.package.match_score}% match</span></>}
                </div>
              </div>
              {current.vetting?.reason && (
                <div className="rounded border border-border bg-[#10110f] p-3 text-xs text-muted">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-muted/60 block mb-1">Vetting Reason</span>
                  {current.vetting.reason}
                </div>
              )}
            </div>
          </>
        ) : (
          <EmptyState title="No job selected" description="Select a job from the list to review." />
        )}
      </main>
    </div>
  );
}
