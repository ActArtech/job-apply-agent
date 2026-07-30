"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchJson } from "@/lib/api-client";
import { toast } from "@/components/ui/toast";
import { requestNotificationPermission } from "@/lib/notifications";

export type LaunchPhase = "phase1" | "phase2" | "phase3-all" | "phase4" | "safe-prepare";

const phaseDescriptions: Record<LaunchPhase, string> = {
  "phase1": "Scrapes all configured job sources. Input: source configs. Output: new job artifacts (duplicates skipped).",
  "phase2": "Sends each unvetted job's description to the AI engine against your 5 criteria. Already-vetted jobs are skipped. Output: approved / filtered / couldn't vet.",
  "phase3-all": "Generates tailored resume, email, and PDF for every approved job. Output: application artifacts + ATS metrics.",
  "phase4": "Searches Hunter/Apollo/LinkedIn for a hiring-manager contact for each generated job. Output: contact email or LinkedIn.",
  "safe-prepare": "Runs the selected pipeline stages in order. Nothing is sent — sending stays manual in Review & Send.",
};

interface RunLauncherModalProps {
  defaultPhase?: LaunchPhase;
  onClose: () => void;
}

export function RunLauncherModal({ defaultPhase = "phase1", onClose }: RunLauncherModalProps) {
  const router = useRouter();
  const [phase, setPhase] = useState<LaunchPhase>(defaultPhase);
  const [max, setMax] = useState(20);
  const [dryRun, setDryRun] = useState(false);
  const [applyMode, setApplyMode] = useState<"both" | "email-only" | "direct-only">("both");
  const [minMatch, setMinMatch] = useState(60);
  const [engine, setEngine] = useState<"gemini" | "groq" | "both">("gemini");
  const [force, setForce] = useState(false);
  const [pipelinePhases, setPipelinePhases] = useState<Record<string, boolean>>({
    phase1: true, phase2: true, phase3: true, phase4: false,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.settings.get().then((s) => {
      if (s.ai_engine) setEngine(s.ai_engine);
    }).catch(() => {});
  }, []);

  const showAdvanced = phase === "phase3-all" || phase === "safe-prepare";

  async function launch() {
    setLoading(true);
    try {
      requestNotificationPermission();
      const body: Record<string, unknown> = { max, limit: max, dry_run: dryRun, engine, force };
      if (phase === "safe-prepare") {
        body.phases = Object.entries(pipelinePhases).filter(([, on]) => on).map(([k]) => k);
      }
      if (showAdvanced) {
        body.min_match = minMatch;
        if (applyMode === "email-only") body.email_only = true;
        if (applyMode === "direct-only") body.direct_only = true;
      }
      const endpoint = phase === "safe-prepare" ? "/pipelines/safe-prepare" : `/phases/${phase}`;
      const { run_id } = await fetchJson<{ run_id: string }>(endpoint, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
      });
      onClose();
      router.push(`/runs/${run_id}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to start run", "error");
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-[#131412] p-6 shadow-xl">
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-[#f5f6f4]">Launch Pipeline Run</h2>
            <p className="mt-1 font-mono text-xs text-muted">Configure and start a backend phase run.</p>
          </div>
          <button onClick={onClose} className="font-mono text-sm leading-none text-muted hover:text-foreground">✕</button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-muted">Phase</label>
            <select
              value={phase}
              onChange={(e) => setPhase(e.target.value as LaunchPhase)}
              className="w-full rounded border border-border bg-[#1a1b18] px-3 py-2 font-mono text-sm text-[#f5f6f4]"
            >
              <option value="phase1">1 · Gather</option>
              <option value="phase2">2 · Vet</option>
              <option value="phase3-all">3 · Generate All Approved</option>
              <option value="phase4">4 · Find Contacts</option>
              <option value="safe-prepare">Pipeline (run selected stages)</option>
            </select>
          </div>

          <p className="rounded border border-border/60 bg-[#10110f] p-2.5 text-xs leading-relaxed text-muted">
            {phaseDescriptions[phase]}
          </p>

          <div>
            <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-muted">AI Engine</label>
            <select
              value={engine}
              onChange={(e) => setEngine(e.target.value as "gemini" | "groq" | "both")}
              className="w-full rounded border border-border bg-[#1a1b18] px-3 py-2 font-mono text-sm text-[#f5f6f4]"
            >
              <option value="gemini">Gemini (falls back to Groq)</option>
              <option value="groq">Groq (falls back to Gemini)</option>
              <option value="both">Both (compare side by side)</option>
            </select>
          </div>

          {(phase === "phase2" || phase === "safe-prepare") && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-[#bfc2b9]">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="accent-accent" />
              Force re-vet all (ignore existing verdicts)
            </label>
          )}

          {phase === "safe-prepare" && (
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-muted">Stages To Run</label>
              <div className="grid grid-cols-2 gap-2">
                {([["phase1", "1 · Gather"], ["phase2", "2 · Vet"], ["phase3", "3 · Generate"], ["phase4", "4 · Contacts"]] as const).map(([key, label]) => (
                  <label key={key} className="flex cursor-pointer items-center gap-2 text-xs text-[#bfc2b9]">
                    <input
                      type="checkbox"
                      checked={pipelinePhases[key]}
                      onChange={(e) => setPipelinePhases((prev) => ({ ...prev, [key]: e.target.checked }))}
                      className="accent-accent"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="mb-1.5 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted">
              <span>Max Jobs Per Source</span>
              <span className="text-accent">{max}</span>
            </label>
            <input
              type="range" min={1} max={100} value={max}
              onChange={(e) => setMax(Number(e.target.value))}
              className="w-full accent-accent"
            />
          </div>

          {showAdvanced && (
            <>
              <div>
                <label className="mb-1.5 flex justify-between font-mono text-[10px] uppercase tracking-wider text-muted">
                  <span>Min Match Score</span>
                  <span className="text-accent">{minMatch}%</span>
                </label>
                <input
                  type="range" min={0} max={100} value={minMatch}
                  onChange={(e) => setMinMatch(Number(e.target.value))}
                  className="w-full accent-accent"
                />
              </div>
              <div>
                <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-muted">Apply Mode</label>
                <div className="flex gap-4">
                  {(["both", "email-only", "direct-only"] as const).map((m) => (
                    <label key={m} className="flex cursor-pointer items-center gap-1.5 text-xs text-[#bfc2b9]">
                      <input
                        type="radio" name="applyMode" value={m}
                        checked={applyMode === m} onChange={() => setApplyMode(m)}
                        className="accent-accent"
                      />
                      {m}
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}

          <label className="flex cursor-pointer items-center gap-2 text-xs text-[#bfc2b9]">
            <input
              type="checkbox" checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="accent-accent"
            />
            Dry Run (no emails sent, no artifacts written)
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded border border-border px-4 py-2 font-mono text-xs text-muted hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={launch}
            disabled={loading}
            className="rounded bg-accent px-4 py-2 font-mono text-xs font-semibold text-accent-foreground hover:bg-accent-hover disabled:opacity-50"
          >
            {loading ? "Starting…" : "▶ Launch"}
          </button>
        </div>
      </div>
    </div>
  );
}
