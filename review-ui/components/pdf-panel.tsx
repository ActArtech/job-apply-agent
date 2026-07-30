"use client";

import { useState } from "react";
import type { JobDetail } from "@/lib/types";
import { getGenerationStats } from "@/lib/types";
import { apiUrl, api } from "@/lib/api-client";
import { Download, RefreshCw, EyeOff, FileDown } from "lucide-react";
import { toast } from "@/components/ui/toast";

export function PdfPanel({
  job,
  onRunPhase,
}: {
  job: JobDetail;
  onRunPhase?: (phase: string, body?: Record<string, unknown>) => Promise<{ ok: boolean; output: string }>;
}) {
  const [regenning, setRegenning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const hasPdf = job.generation?.status === "generated";
  const isApproved = job.vetting?.approved === true;

  async function handleRegen() {
    if (!onRunPhase) return;
    setRegenning(true);
    try {
      const result = await onRunPhase("phase3-pdf-only", { jobId: job.job_id });
      if (!result.ok) {
        toast(result.output || "Regen failed", "error");
      } else {
        toast("PDF recompiled", "success");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Regen failed", "error");
    } finally {
      setRegenning(false);
    }
  }

  async function handleGenerate() {
    if (!onRunPhase) return;
    setGenerating(true);
    try {
      const result = await onRunPhase("phase3", { jobId: job.job_id });
      if (!result.ok) {
        toast(result.output || "Generation failed", "error");
      } else {
        toast("Application generated", "success");
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Generation failed", "error");
    } finally {
      setGenerating(false);
    }
  }

  function handleDownload() {
    window.open(api.jobs.pdfDownloadUrl(job.job_id), "_blank");
  }

  if (!hasPdf) {
    return (
      <div className="h-full min-h-0 flex flex-col items-center justify-center border border-dashed border-border rounded-xl bg-[#131412] p-8 text-center">
        <EyeOff className="h-8 w-8 text-muted mb-2 stroke-[1.5]" />
        <h3 className="text-sm font-medium text-foreground mb-1">No PDF preview available</h3>
        <p className="text-xs text-muted max-w-xs">
          PDF has not been compiled yet. Use the Action Rail to generate application artifacts.
        </p>
        {onRunPhase && isApproved ? (
          <div className="mt-4 flex flex-col items-center gap-2">
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-mono text-muted hover:text-foreground hover:border-accent/60 transition"
            >
              <FileDown className={`h-3 w-3 ${generating ? "animate-pulse" : ""}`} />
              {generating ? "Generating…" : "Generate Application"}
            </button>
          </div>
        ) : onRunPhase && !isApproved ? (
          <p className="mt-4 text-xs font-mono text-muted">Requires Phase 2 approval</p>
        ) : null}
      </div>
    );
  }

  return (
    <div data-testid="pdf-panel" className="h-full min-h-0 bg-neutral-900 border border-border rounded-xl overflow-hidden relative flex flex-col">
      <div className="bg-[#131412] px-4 py-2 border-b border-border flex justify-between items-center text-xs font-mono text-muted shrink-0">
        <span>Artifact: resume.pdf</span>
        <div className="flex items-center gap-3">
          <span>Page Count: {getGenerationStats(job.generation)?.page_count ?? 1}p</span>
          {onRunPhase && (
            <button
              onClick={handleRegen}
              disabled={regenning}
              title="Recompile PDF from existing LaTeX"
              className="flex items-center gap-1 hover:text-foreground transition"
            >
              <RefreshCw className={`h-3 w-3 ${regenning ? "animate-spin" : ""}`} />
              <span>{regenning ? "Compiling…" : "Regen"}</span>
            </button>
          )}
          <button
            onClick={handleDownload}
            title="Download PDF"
            className="flex items-center gap-1 hover:text-foreground transition"
          >
            <Download className="h-3 w-3" />
            <span>Download</span>
          </button>
        </div>
      </div>
      <iframe
        title="Generated resume"
        src={`${apiUrl(`/jobs/${job.job_id}/artifact/resume.pdf`)}#toolbar=0&navpanes=0&statusbar=0`}
        className="flex-1 min-h-0 w-full bg-white border-none"
      />
    </div>
  );
}
