"use client";

import Link from "next/link";
import type { JobSummary } from "@/lib/types";
import { getGenerationStats } from "@/lib/types";
import { Circle, Globe, FileText, CheckCircle, AlertTriangle, XCircle, Search } from "lucide-react";
import { useState } from "react";

const PAGE_SIZE = 20;
const STATUS_OPTIONS = ["all", "pending", "approved", "rejected", "needs_regen"] as const;

export function JobTable({
  jobs,
  selectedId,
  onSelect,
}: {
  jobs: JobSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(0);

  const filteredJobs = jobs.filter(job => {
    const q = filter.toLowerCase();
    const matchText = !q || job.company.toLowerCase().includes(q) || job.title.toLowerCase().includes(q);
    const matchStatus = statusFilter === "all" || (job.review?.status ?? "pending") === statusFilter;
    return matchText && matchStatus;
  });

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageJobs = filteredJobs.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const getStatusBadge = (status: string = "pending") => {
    switch (status) {
      case "approved":
        return <span className="flex items-center gap-1 text-[10px] uppercase font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded-full border border-emerald-900/50">Approved</span>;
      case "rejected":
        return <span className="flex items-center gap-1 text-[10px] uppercase font-mono text-rose-400 bg-rose-950/40 px-2 py-0.5 rounded-full border border-rose-900/50">Rejected</span>;
      case "needs_regen":
        return <span className="flex items-center gap-1 text-[10px] uppercase font-mono text-amber-400 bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-900/50">Regen</span>;
      default:
        return <span className="flex items-center gap-1 text-[10px] uppercase font-mono text-muted bg-[#232421]/50 px-2 py-0.5 rounded-full border border-border">Pending</span>;
    }
  };

  return (
    <aside className="min-h-0 flex flex-col border-r border-border bg-[#131412] h-full overflow-hidden">
      {/* Search and Stats */}
      <div className="p-4 border-b border-border space-y-3">
        <div className="flex justify-between items-center">
          <span className="text-xs font-mono uppercase text-muted tracking-wider">APPLICATIONS</span>
          <span className="text-xs font-mono bg-[#1a1b18] px-2 py-0.5 rounded text-accent border border-border">
            {jobs.length} Total
          </span>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
          <input
            type="text"
            placeholder="Search company or role..."
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setPage(0); }}
            className="w-full bg-[#171815] border border-border rounded-lg pl-9 pr-4 py-2 text-sm text-foreground placeholder-muted focus:outline-none focus:border-accent/50 transition font-sans"
          />
        </div>
        <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
          className="w-full rounded border border-border bg-[#171815] px-2 py-1.5 text-xs text-foreground focus:outline-none font-mono">
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y divide-border/30">
        {pageJobs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted font-sans">
            No applications found
          </div>
        ) : (
          pageJobs.map((job) => {
            const isSelected = selectedId === job.job_id;
            const score = job.package?.match_score ?? (job as any).match_score ?? null;
            const scoreText = score ? `${score}%` : "-";
            
            return (
              <div
                key={job.job_id}
                className={`relative hover:bg-[#1a1b18]/60 transition-all ${
                  isSelected ? "bg-[#181916] border-l-2 border-accent" : ""
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(job.job_id)}
                  className="block w-full p-4 pr-16 text-left"
                >
                <div className="flex justify-between items-start gap-2">
                  <div className="truncate text-sm font-semibold text-foreground tracking-wide font-sans">
                    {job.company}
                  </div>
                  <div className="text-xs font-mono shrink-0">
                    {score ? (
                      <span className={`px-1.5 py-0.5 rounded font-bold ${
                        score >= 80 ? "text-emerald-400 bg-emerald-950/20" : 
                        score >= 70 ? "text-amber-400 bg-amber-950/20" : 
                        "text-rose-400 bg-rose-950/20"
                      }`}>
                        {scoreText}
                      </span>
                    ) : (
                      <span className="text-muted">-</span>
                    )}
                  </div>
                </div>

                <div className="mt-1 line-clamp-1 text-xs text-muted font-sans font-medium">
                  {job.title}
                </div>

                <div className="mt-3 flex justify-between items-center gap-2">
                  <div className="flex items-center gap-2 text-[10px] font-mono text-muted">
                    <span className="capitalize px-1 py-0.2 bg-[#232421]/40 rounded border border-border/40">
                      {job.source}
                    </span>
                    <span>•</span>
                    <span>
                      {getGenerationStats(job.generation)?.page_count ? `${getGenerationStats(job.generation)?.page_count}p` : "no pdf"}
                    </span>
                  </div>
                  {getStatusBadge(job.review?.status)}
                </div>
              </button>
                <Link
                  href={`/jobs/${job.job_id}`}
                  aria-label={`Open ${job.job_id}`}
                  onClick={(event) => event.stopPropagation()}
                  className="absolute right-4 top-4 rounded border border-border px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-muted hover:border-accent/60 hover:text-accent"
                >
                  Open
                </Link>
              </div>
            );
          })
        )}
      </div>
      {totalPages > 1 && (
        <div className="border-t border-border flex items-center justify-between px-3 py-2 text-[10px] font-mono text-muted">
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safePage === 0} className="disabled:opacity-30">← Prev</button>
          <span>{safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, filteredJobs.length)} of {filteredJobs.length}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={safePage >= totalPages - 1} className="disabled:opacity-30">Next →</button>
        </div>
      )}
    </aside>
  );
}
