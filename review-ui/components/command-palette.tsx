"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import type { JobSummary } from "@/lib/types";
import { Search, ArrowRight } from "lucide-react";

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIdx(0);
      api.jobs.list().then(setJobs).catch(() => {});
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  const filtered = query.trim()
    ? jobs.filter((j) => {
        const q = query.toLowerCase();
        return j.company.toLowerCase().includes(q) || j.title.toLowerCase().includes(q) || j.source.toLowerCase().includes(q);
      })
    : jobs.slice(0, 8);

  function select(job: JobSummary) {
    onClose();
    router.push(`/jobs/${job.job_id}`);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIdx]) {
      select(filtered[selectedIdx]);
    } else if (e.key === "Escape") {
      onClose();
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-[#131412] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Search className="h-4 w-4 text-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelectedIdx(0); }}
            onKeyDown={handleKeyDown}
            placeholder="Search jobs…"
            className="flex-1 bg-transparent text-sm text-foreground placeholder-muted outline-none font-mono"
          />
          <kbd className="text-[10px] font-mono text-muted border border-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>

        {/* Results */}
        <div className="max-h-72 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs font-mono text-muted">No jobs found</div>
          ) : (
            filtered.map((job, i) => (
              <button
                key={job.job_id}
                onClick={() => select(job)}
                onMouseEnter={() => setSelectedIdx(i)}
                className={`w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left transition ${
                  i === selectedIdx ? "bg-[#1a1b18]" : "hover:bg-[#171815]"
                }`}
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">{job.company}</div>
                  <div className="text-xs text-muted truncate">{job.title}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] font-mono text-muted">{job.source}</span>
                  {i === selectedIdx && <ArrowRight className="h-3 w-3 text-muted" />}
                </div>
              </button>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="border-t border-border px-4 py-2 flex items-center gap-3 text-[10px] font-mono text-muted/60">
          <span><kbd className="border border-border/60 rounded px-1">↑↓</kbd> navigate</span>
          <span><kbd className="border border-border/60 rounded px-1">↵</kbd> open</span>
          <span><kbd className="border border-border/60 rounded px-1">esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
