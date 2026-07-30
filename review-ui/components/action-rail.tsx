"use client";

import type { JobDetail } from "@/lib/types";
import { apiUrl, api } from "@/lib/api-client";
import { useState, useEffect } from "react";
import { FileDown, CheckCircle, RefreshCw, XCircle, AlertCircle, FolderOpen, MousePointerClick, Zap } from "lucide-react";
import { toast } from "@/components/ui/toast";

export function ActionRail({
  job,
  onChanged,
  onRunPhase,
}: {
  job: JobDetail | null;
  onChanged: () => void | Promise<void>;
  onRunPhase: (phaseName: string, body?: Record<string, unknown>) => Promise<{ ok: boolean; output: string }>;
}) {
  const [notes, setNotes] = useState<string>("");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [runningPhase, setRunningPhase] = useState<string | null>(null);
  const [phaseError, setPhaseError] = useState<string>("");
  const [directApplying, setDirectApplying] = useState(false);

  // Sync notes when job changes
  useEffect(() => {
    if (job) {
      setNotes(job.review?.notes ?? "");
    } else {
      setNotes("");
    }
  }, [job]);

  // Handle Mark status
  async function markStatus(status: string) {
    if (!job) return;
    setIsSaving(true);
    try {
      const response = await fetch(apiUrl(`/jobs/${job.job_id}/review`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, notes })
      });
      if (!response.ok) {
        throw new Error(`Review update failed with HTTP ${response.status}`);
      }
      await onChanged();
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  }

  async function runPhase(phaseName: string, body: any = {}) {
    if (runningPhase) return;
    setRunningPhase(phaseName);
    setPhaseError("");
    try {
      const result = await onRunPhase(phaseName, body);
      if (!result.ok) {
        setPhaseError(result.output || "Phase command failed");
        return;
      }
      if (phaseName === "phase2-single") await onChanged();
    } catch (e) {
      console.error(e);
      setPhaseError(e instanceof Error ? e.message : "Phase command failed");
    } finally {
      setRunningPhase(null);
    }
  }

  async function handleDirectApply() {
    if (!job || directApplying) return;
    setDirectApplying(true);
    try {
      const result = await api.jobs.directApply(job.job_id);
      toast(result.message, result.ok ? "success" : "error");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Direct apply failed", "error");
    } finally {
      setDirectApplying(false);
    }
  }

  async function handleOpenFolder() {
    if (!job?.artifacts_dir) return;
    try {
      await api.system.openFolder(job.artifacts_dir);
    } catch {
      toast("Could not open folder", "error");
    }
  }

  const reviewStatus = job?.review?.status ?? "pending";
  const canGenerate = job?.vetting?.approved === true;

  return (
    <aside className="border-l border-border bg-[#131412] p-4 h-full flex flex-col overflow-y-auto space-y-6">
      {/* Active Job Title */}
      <div className="space-y-1.5 shrink-0">
        <span className="text-[10px] font-mono text-muted uppercase tracking-wider">SELECTED TARGET</span>
        <div className="text-sm font-semibold truncate text-foreground font-sans">
          {job ? job.company : "No job selected"}
        </div>
        <div className="text-xs text-muted truncate font-sans">
          {job ? job.title : "Select an application to manage"}
        </div>
      </div>

      {/* Vetting Status Display */}
      {job?.vetting && (
        <div className="p-3 bg-[#171815] border border-border/40 rounded-lg space-y-1 shrink-0">
          <div className="text-[10px] font-mono text-muted uppercase">VETTING REASON</div>
          <div className="text-xs font-sans text-muted leading-relaxed italic">
            "{job.vetting.reason || "Vetted by pipeline"}"
          </div>
        </div>
      )}

      {/* Review Section */}
      <div className="space-y-4 flex-1 flex flex-col min-h-0">
        <div className="border-t border-border/40 pt-4 shrink-0">
          <label className="text-[10px] font-mono text-muted uppercase tracking-wider block mb-2">Review Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={!job}
            placeholder="Add comments or Regen instructions..."
            className="w-full h-24 bg-[#171815] border border-border rounded-lg p-2.5 text-xs text-foreground placeholder-muted focus:outline-none focus:border-accent/40 resize-none font-sans"
          />
        </div>

        {/* Action Status Controls */}
        <div className="space-y-2 shrink-0">
          <span className="text-[10px] font-mono text-muted uppercase tracking-wider block">Decision Actions</span>
          <div className="grid grid-cols-1 gap-2">
            <button
              onClick={() => markStatus("approved")}
              disabled={!job || isSaving}
              className={`w-full flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide border transition-all ${
                reviewStatus === "approved"
                  ? "bg-emerald-950/30 text-emerald-400 border-emerald-800/80"
                  : "bg-transparent text-[#bfc2b9] border-border hover:bg-[#1a1b18]"
              }`}
            >
              <CheckCircle className="h-3.5 w-3.5" />
              <span>Approve Application</span>
            </button>

            <button
              onClick={() => markStatus("needs_regen")}
              disabled={!job || isSaving}
              className={`w-full flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide border transition-all ${
                reviewStatus === "needs_regen"
                  ? "bg-amber-950/30 text-amber-400 border-amber-800/80"
                  : "bg-transparent text-[#bfc2b9] border-border hover:bg-[#1a1b18]"
              }`}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Request Regeneration</span>
            </button>

            <button
              onClick={() => markStatus("rejected")}
              disabled={!job || isSaving}
              className={`w-full flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide border transition-all ${
                reviewStatus === "rejected"
                  ? "bg-rose-950/30 text-rose-400 border-rose-800/80"
                  : "bg-transparent text-[#bfc2b9] border-border hover:bg-[#1a1b18]"
              }`}
            >
              <XCircle className="h-3.5 w-3.5" />
              <span>Reject Application</span>
            </button>
          </div>
        </div>

        {/* Pipeline Phase Runner */}
        <div className="border-t border-border/40 pt-4 space-y-2 shrink-0">
          <span className="text-[10px] font-mono text-muted uppercase tracking-wider block">Pipeline Control</span>
          <div className="space-y-2">
            <button
              onClick={() => runPhase("phase3", { jobId: job?.job_id })}
              disabled={!job || !canGenerate || runningPhase !== null}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-accent text-accent-foreground py-2 text-xs font-semibold tracking-wide hover:bg-accent-hover transition-all active:scale-[0.98]"
            >
              <FileDown className="h-3.5 w-3.5" />
              <span>
                {runningPhase === "phase3" ? "Generating..." : "Generate Selected"}
              </span>
            </button>

            {job && !canGenerate ? (
              <div className="text-[10px] font-mono text-amber-300">
                Phase 2 approval required before generation.
              </div>
            ) : null}

            <button
              onClick={() => runPhase("phase3-all", { limit: 10 })}
              disabled={runningPhase !== null}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border text-[#bfc2b9] bg-transparent py-2 text-xs font-semibold tracking-wide hover:bg-[#1a1b18] transition-all"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${runningPhase === "phase3-all" ? "animate-spin" : ""}`} />
              <span>Generate All Approved</span>
            </button>

            <button
              onClick={() => runPhase("phase2-single", { jobId: job?.job_id })}
              disabled={!job || runningPhase !== null}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border text-[#bfc2b9] bg-transparent py-2 text-xs font-semibold tracking-wide hover:bg-[#1a1b18] transition-all"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${runningPhase === "phase2-single" ? "animate-spin" : ""}`} />
              <span>{runningPhase === "phase2-single" ? "Re-vetting…" : "Re-vet Job"}</span>
            </button>

            <button
              onClick={handleDirectApply}
              disabled={!job || directApplying}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border text-[#bfc2b9] bg-transparent py-2 text-xs font-semibold tracking-wide hover:bg-[#1a1b18] transition-all"
            >
              <Zap className="h-3.5 w-3.5" />
              <span>{directApplying ? "Applying…" : "Direct Apply"}</span>
            </button>

            {phaseError ? (
              <pre className="max-h-28 overflow-auto rounded-lg border border-rose-900/60 bg-rose-950/20 p-2 text-[10px] leading-relaxed text-rose-200 whitespace-pre-wrap">
                {phaseError}
              </pre>
            ) : null}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-border/40 pt-4 flex flex-col gap-1 text-[10px] font-mono text-muted shrink-0">
          <div className="flex items-center gap-1.5">
            <AlertCircle className="h-3 w-3" />
            <span>Apply Mode: Standby</span>
          </div>
          <button
            onClick={handleOpenFolder}
            disabled={!job?.artifacts_dir}
            className="flex items-center gap-1.5 mt-1 hover:text-foreground transition disabled:opacity-40 disabled:cursor-not-allowed"
            title={job?.artifacts_dir ?? "No artifacts dir"}
          >
            <FolderOpen className="h-3 w-3" />
            <span>Open Artifacts Folder</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
