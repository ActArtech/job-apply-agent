"use client";

import { useState } from "react";
import type { JobDetail } from "@/lib/types";
import { Link, MapPin, Briefcase, Calendar, Copy, Check } from "lucide-react";
import { toast } from "@/components/ui/toast";

export function JdPanel({ job }: { job: JobDetail }) {
  const [copied, setCopied] = useState(false);

  async function handleCopyUrl() {
    try {
      await navigator.clipboard.writeText(job.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast("Copy failed", "error");
    }
  }
  const formatDate = (isoString?: string) => {
    if (!isoString) return "-";
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="h-full min-h-0 flex flex-col gap-4 overflow-hidden">
      {/* Job Metadata Card */}
      <div className="bg-[#131412] border border-border p-4 rounded-xl space-y-3 shrink-0">
        <div className="flex flex-wrap gap-4 text-xs font-mono text-muted">
          <div className="flex items-center gap-1.5">
            <MapPin className="h-3.5 w-3.5" />
            <span>{job.location || "Worldwide"}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Briefcase className="h-3.5 w-3.5" />
            <span className="capitalize">{job.work_mode || (job.remote ? "remote" : "onsite")}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5" />
            <span>Gathered {formatDate(job.created_at || (job as any).created_at)}</span>
          </div>
        </div>

        {job.url && (
          <div className="pt-2 border-t border-border/30 flex items-center justify-between">
            <span className="text-xs font-mono text-muted">Original Posting</span>
            <div className="flex items-center gap-3">
              <button
                onClick={handleCopyUrl}
                title="Copy URL"
                className="text-xs font-mono text-muted hover:text-foreground flex items-center gap-1 transition"
              >
                {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                <span>{copied ? "Copied" : "Copy URL"}</span>
              </button>
              <a
                href={job.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-mono text-accent hover:underline flex items-center gap-1 hover:text-accent-hover transition"
              >
                <span>View Source</span>
                <Link className="h-3 w-3" />
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Description Text */}
      <div className="flex-1 overflow-auto rounded-xl border border-border bg-[#131412] p-6 shadow-inner relative">
        <div className="absolute top-4 right-4 text-[10px] font-mono text-muted uppercase tracking-widest bg-[#171815] px-2 py-0.5 rounded border border-border/40 select-none">
          Job Description
        </div>
        <div className="whitespace-pre-wrap text-sm leading-7 text-[#bfc2b9] font-sans pr-2 max-w-3xl">
          {job.jd || "No job description text stored."}
        </div>
      </div>
    </div>
  );
}
