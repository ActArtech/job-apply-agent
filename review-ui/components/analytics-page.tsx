"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { AnalyticsFunnel, AnalyticsResponseRate, AnalyticsSource } from "@/lib/types";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SkeletonList } from "@/components/ui/skeleton";

const FUNNEL_STAGES = [
  { key: "gathered", label: "Gathered" },
  { key: "vetted", label: "Vetted" },
  { key: "approved", label: "Approved" },
  { key: "generated", label: "Generated" },
  { key: "reviewed", label: "Reviewed" },
  { key: "sent", label: "Sent" },
] as const;

function FunnelBar({ label, count, max, prev }: { label: string; count: number; max: number; prev: number | null }) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  const drop = prev !== null && prev > 0 ? Math.round((1 - count / prev) * 100) : null;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px] font-mono text-muted">
        <span>{label}</span>
        <div className="flex gap-3">
          {drop !== null && <span className="text-rose-400">-{drop}%</span>}
          <span className="text-foreground">{count}</span>
        </div>
      </div>
      <div className="h-2 rounded bg-[#1a1b18] overflow-hidden">
        <div className="h-full rounded bg-accent transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [funnel, setFunnel] = useState<AnalyticsFunnel | null>(null);
  const [rate, setRate] = useState<AnalyticsResponseRate | null>(null);
  const [sources, setSources] = useState<AnalyticsSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [f, r, s] = await Promise.all([
        api.analytics.funnel(),
        api.analytics.responseRate(),
        api.analytics.sources(),
      ]);
      setFunnel(f);
      setRate(r);
      setSources(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return <SkeletonList rows={10} />;

  const max = funnel?.gathered ?? 1;

  return (
    <div className="p-6 space-y-8 max-w-2xl">
      {error && <ErrorBanner message={error} onRetry={load} />}

      <section className="space-y-3">
        <h2 className="font-mono text-xs uppercase tracking-wider text-muted/60">Pipeline Funnel</h2>
        {funnel && FUNNEL_STAGES.map((stage, i) => {
          const count = funnel[stage.key as keyof AnalyticsFunnel] as number;
          const prevKey = i > 0 ? FUNNEL_STAGES[i - 1].key : null;
          const prev = prevKey ? (funnel[prevKey as keyof AnalyticsFunnel] as number) : null;
          return <FunnelBar key={stage.key} label={stage.label} count={count} max={max} prev={prev} />;
        })}
      </section>

      {rate && (
        <section className="space-y-3">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted/60">Response Rate</h2>
          <div className="grid grid-cols-3 gap-3">
            {([
              { label: "Sent", value: rate.sent },
              { label: "Replied", value: rate.replied },
              { label: "Rate", value: `${Math.round(rate.rate_reply * 100)}%` },
            ] as const).map((item) => (
              <div key={item.label} className="rounded border border-border bg-[#10110f] p-3 text-center">
                <div className="font-mono text-lg text-accent">{item.value}</div>
                <div className="font-mono text-[10px] text-muted mt-1">{item.label}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {sources.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-mono text-xs uppercase tracking-wider text-muted/60">Sources</h2>
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border bg-[#10110f]">
                  <th className="px-3 py-2 text-left text-muted font-normal">Source</th>
                  <th className="px-3 py-2 text-right text-muted font-normal">Jobs</th>
                  <th className="px-3 py-2 text-right text-muted font-normal">Sent</th>
                  <th className="px-3 py-2 text-right text-muted font-normal">Approved</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {sources.map((s) => (
                  <tr key={s.source} className="hover:bg-[#1a1b18]/40">
                    <td className="px-3 py-2 text-foreground">{s.source}</td>
                    <td className="px-3 py-2 text-right text-muted">{s.total}</td>
                    <td className="px-3 py-2 text-right text-muted">{s.sent}</td>
                    <td className="px-3 py-2 text-right text-accent">{s.approved}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
