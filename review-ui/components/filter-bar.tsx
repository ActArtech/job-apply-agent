"use client";
import type { JobSummary } from "@/lib/types";
import { type Filters, EMPTY_FILTERS, isActive, distinctSources } from "@/lib/job-filters";

const selectClass =
  "rounded border border-border bg-[#1a1b18] px-2 py-1.5 font-mono text-xs text-[#f5f6f4]";

export function FilterBar({
  filters,
  onChange,
  jobs,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  jobs: JobSummary[];
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const sources = distinctSources(jobs);

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <select className={selectClass} value={filters.region} onChange={(e) => set({ region: e.target.value })}>
        <option value="all">Region: All</option>
        <option value="india">India</option>
        <option value="foreign">Foreign</option>
        <option value="unknown">Unknown</option>
      </select>
      <select className={selectClass} value={filters.workMode} onChange={(e) => set({ workMode: e.target.value })}>
        <option value="all">Work mode: All</option>
        <option value="remote">Remote</option>
        <option value="hybrid">Hybrid</option>
        <option value="wfo">Onsite</option>
        <option value="unknown">Unknown</option>
      </select>
      <select className={selectClass} value={filters.source} onChange={(e) => set({ source: e.target.value })}>
        <option value="all">Source: All</option>
        {sources.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <select className={selectClass} value={filters.scoreBand} onChange={(e) => set({ scoreBand: e.target.value })}>
        <option value="all">Score: All</option>
        <option value="90+">90+</option>
        <option value="70-89">70–89</option>
        <option value="<70">&lt;70</option>
      </select>
      <input
        type="text"
        value={filters.q}
        onChange={(e) => set({ q: e.target.value })}
        placeholder="Search company / role"
        className="rounded border border-border bg-[#1a1b18] px-2 py-1.5 font-mono text-xs text-[#f5f6f4] placeholder:text-muted"
      />
      {isActive(filters) && (
        <button
          onClick={() => onChange(EMPTY_FILTERS)}
          className="font-mono text-[10px] uppercase tracking-wider text-muted hover:text-accent"
        >
          Clear
        </button>
      )}
    </div>
  );
}
