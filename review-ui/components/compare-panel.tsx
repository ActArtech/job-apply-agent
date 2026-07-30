"use client";

import { useState } from "react";
import type { JobDetail, SingleGeneration, BothGeneration } from "@/lib/types";
import { getGenerationStats } from "@/lib/types";
import { api } from "@/lib/api-client";
import { toast } from "@/components/ui/toast";
import { CheckCircle2, AlertCircle, BarChart3, Star, CheckCheck } from "lucide-react";

function isBothGeneration(gen: JobDetail["generation"]): gen is BothGeneration {
  return !!gen && (gen as BothGeneration).provider === "both";
}

function MetricBar({ numerator, denominator }: { numerator: number; denominator: number }) {
  const pct = denominator > 0 ? Math.round((numerator / denominator) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] font-mono text-muted">
        <span>Metric Density</span>
        <span>{pct}%</span>
      </div>
      <div className="w-full bg-[#232421] h-1.5 rounded-full overflow-hidden">
        <div className="bg-accent h-full rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SingleProviderStats({ gen, label, isSelected, onSelect, selecting }: {
  gen: SingleGeneration | null;
  label: string;
  isSelected: boolean;
  onSelect?: () => void;
  selecting?: boolean;
}) {
  const pageCount = gen?.page_count ?? null;
  const impactRatio = gen?.impact_signal_ratio !== undefined ? Math.round(gen.impact_signal_ratio * 100) : null;
  const numeric = gen?.numeric_bullets ?? 0;
  const total = gen?.total_bullets ?? 0;

  return (
    <div className={`flex flex-col gap-3 rounded-xl border p-4 transition ${isSelected ? "border-accent bg-accent/5" : "border-border bg-[#131412]"}`}>
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wider text-muted">{label}</span>
        {isSelected && <span className="flex items-center gap-1 text-[10px] font-mono text-accent"><CheckCheck className="h-3 w-3" />Selected</span>}
      </div>

      {gen ? (
        <>
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg border border-border/40 bg-[#171815] p-2 text-center">
              <div className="text-[10px] font-mono text-muted uppercase">Pages</div>
              <div className="mt-1 text-lg font-semibold font-mono text-foreground">{pageCount ?? "-"}</div>
            </div>
            <div className="rounded-lg border border-border/40 bg-[#171815] p-2 text-center">
              <div className="text-[10px] font-mono text-muted uppercase">Impact</div>
              <div className="mt-1 text-lg font-semibold font-mono text-foreground">{impactRatio !== null ? `${impactRatio}%` : "-"}</div>
            </div>
            <div className="rounded-lg border border-border/40 bg-[#171815] p-2 text-center">
              <div className="text-[10px] font-mono text-muted uppercase">Numeric</div>
              <div className="mt-1 text-lg font-semibold font-mono text-foreground">{total > 0 ? `${numeric}/${total}` : "-"}</div>
            </div>
          </div>
          {total > 0 && <MetricBar numerator={numeric} denominator={total} />}
        </>
      ) : (
        <div className="py-4 text-center text-xs text-muted font-mono">Generation failed</div>
      )}

      {onSelect && !isSelected && gen && (
        <button
          onClick={onSelect}
          disabled={selecting}
          className="mt-1 rounded border border-border px-3 py-1.5 font-mono text-xs text-muted transition hover:border-accent/60 hover:text-accent disabled:opacity-50"
        >
          {selecting ? "Selecting…" : "Use this"}
        </button>
      )}
    </div>
  );
}

function BothModeCard({ gen, jobId, onJobUpdate }: {
  gen: BothGeneration;
  jobId: string;
  onJobUpdate?: () => void;
}) {
  const [selecting, setSelecting] = useState<"gemini" | "groq" | null>(null);

  async function handleSelect(provider: "gemini" | "groq") {
    setSelecting(provider);
    try {
      await api.jobs.selectProvider(jobId, provider);
      toast(`Using ${provider} output`, "success");
      onJobUpdate?.();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Select failed", "error");
    } finally {
      setSelecting(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-[#171815] px-3 py-2">
        <BarChart3 className="h-3.5 w-3.5 text-accent" />
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Both-Mode — pick your output</span>
        {gen.selected && (
          <span className="ml-auto font-mono text-[10px] text-accent">{gen.selected} active</span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <SingleProviderStats
          gen={gen.gemini}
          label="Gemini"
          isSelected={gen.selected === "gemini"}
          onSelect={() => handleSelect("gemini")}
          selecting={selecting === "gemini"}
        />
        <SingleProviderStats
          gen={gen.groq}
          label="Groq"
          isSelected={gen.selected === "groq"}
          onSelect={() => handleSelect("groq")}
          selecting={selecting === "groq"}
        />
      </div>
    </div>
  );
}

export function ComparePanel({ job, onJobUpdate }: { job: JobDetail; onJobUpdate?: () => void }) {
  const pkg = job.package;
  const gen = job.generation;
  const stats = getGenerationStats(gen);

  const score = pkg?.match_score ?? null;
  const pageCount = stats?.page_count ?? null;
  const impactRatio = stats?.impact_signal_ratio !== undefined ? Math.round(stats.impact_signal_ratio * 100) : null;
  const numericBullets = stats?.numeric_bullets ?? 0;
  const totalBullets = stats?.total_bullets ?? 0;

  return (
    <div className="h-full min-h-0 overflow-auto pr-2 pb-6 space-y-4">
      {/* Overview Grid */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-[#131412] border border-border p-6 rounded-xl flex flex-col justify-between relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-accent/5 rounded-full blur-xl group-hover:bg-accent/10 transition" />
          <div>
            <div className="text-xs font-mono text-muted uppercase tracking-wider">ATS MATCH SCORE</div>
            <div className="text-xs font-mono text-emerald-400 mt-1 flex items-center gap-1">
              <Star className="h-3 w-3 fill-current" /><span>Optimized</span>
            </div>
          </div>
          <div className="mt-8 flex items-baseline gap-1">
            <span className="text-4xl font-semibold tracking-tight font-mono">{score ?? "-"}</span>
            <span className="text-xs font-mono text-muted">% Match</span>
          </div>
        </div>

        <div className="bg-[#131412] border border-border p-6 rounded-xl flex flex-col justify-between relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-emerald-500/5 rounded-full blur-xl group-hover:bg-emerald-500/10 transition" />
          <div>
            <div className="text-xs font-mono text-muted uppercase tracking-wider">IMPACT RATIO</div>
            <div className="text-xs font-mono text-emerald-400 mt-1">Numeric Metrics</div>
          </div>
          <div className="mt-8 flex items-baseline gap-1">
            <span className="text-4xl font-semibold tracking-tight font-mono">
              {impactRatio !== null ? `${impactRatio}%` : "-"}
            </span>
            <span className="text-xs font-mono text-muted">Bullets</span>
          </div>
        </div>
      </div>

      {/* Both-mode comparison or single generation report */}
      {isBothGeneration(gen) ? (
        <BothModeCard gen={gen} jobId={job.job_id} onJobUpdate={onJobUpdate} />
      ) : (
        <div className="bg-[#131412] border border-border p-6 rounded-xl space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-border/40">
            <BarChart3 className="h-4 w-4 text-accent" />
            <h2 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">Generation Report</h2>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="p-3 bg-[#171815] border border-border/40 rounded-lg text-center">
              <div className="text-[10px] font-mono text-muted uppercase">PDF Pages</div>
              <div className="text-lg font-semibold font-mono text-foreground mt-1">{pageCount ?? "-"}</div>
            </div>
            <div className="p-3 bg-[#171815] border border-border/40 rounded-lg text-center">
              <div className="text-[10px] font-mono text-muted uppercase">Quantified</div>
              <div className="text-lg font-semibold font-mono text-foreground mt-1">
                {totalBullets > 0 ? `${numericBullets}/${totalBullets}` : "-"}
              </div>
            </div>
            <div className="p-3 bg-[#171815] border border-border/40 rounded-lg text-center">
              <div className="text-[10px] font-mono text-muted uppercase">Version</div>
              <div className="text-lg font-semibold font-mono text-foreground mt-1">v1.0</div>
            </div>
          </div>
          {totalBullets > 0 && <MetricBar numerator={numericBullets} denominator={totalBullets} />}
        </div>
      )}

      {/* Keywords */}
      <div className="grid grid-cols-1 gap-4">
        <div className="bg-[#131412] border border-border p-6 rounded-xl space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b border-border/40">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <h3 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">Matched Keywords</h3>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {pkg?.keywords_matched?.length ? (
              pkg.keywords_matched.map((kw) => (
                <span key={kw} className="rounded px-2.5 py-1 text-xs font-mono font-medium text-emerald-300 bg-emerald-950/30 border border-emerald-900/40">{kw}</span>
              ))
            ) : (
              <span className="text-xs font-sans text-muted">No keywords matched.</span>
            )}
          </div>
        </div>

        <div className="bg-[#131412] border border-border p-6 rounded-xl space-y-3">
          <div className="flex items-center gap-2 pb-2 border-b border-border/40">
            <AlertCircle className="h-4 w-4 text-amber-400" />
            <h3 className="text-xs font-mono uppercase tracking-wider text-muted font-semibold">Missing Keywords</h3>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {pkg?.keywords_missing?.length ? (
              pkg.keywords_missing.map((kw) => (
                <span key={kw} className="rounded px-2.5 py-1 text-xs font-mono font-medium text-amber-300 bg-amber-950/30 border border-amber-900/40">{kw}</span>
              ))
            ) : (
              <span className="text-xs font-sans text-muted">No missing keywords detected.</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
