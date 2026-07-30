import type { JobSummary } from "./types";

export type Filters = {
  region: string;
  workMode: string;
  source: string;
  scoreBand: string;
  q: string;
};

export const EMPTY_FILTERS: Filters = {
  region: "all",
  workMode: "all",
  source: "all",
  scoreBand: "all",
  q: "",
};

export function isActive(f: Filters): boolean {
  return f.region !== "all" || f.workMode !== "all" || f.source !== "all" || f.scoreBand !== "all" || f.q.trim() !== "";
}

function scoreInBand(score: number | undefined, band: string): boolean {
  if (band === "all") return true;
  if (typeof score !== "number") return false;
  if (band === "90+") return score >= 90;
  if (band === "70-89") return score >= 70 && score < 90;
  if (band === "<70") return score < 70;
  return true;
}

export function matchesFilters(job: JobSummary, f: Filters): boolean {
  if (f.region !== "all" && (job.region ?? "unknown") !== f.region) return false;
  if (f.workMode !== "all" && (job.work_mode ?? "unknown") !== f.workMode) return false;
  if (f.source !== "all" && job.source !== f.source) return false;
  if (!scoreInBand(job.package?.match_score, f.scoreBand)) return false;
  const q = f.q.trim().toLowerCase();
  if (q && !`${job.company} ${job.title}`.toLowerCase().includes(q)) return false;
  return true;
}

export function distinctSources(jobs: JobSummary[]): string[] {
  return Array.from(new Set(jobs.map((j) => j.source).filter(Boolean))).sort();
}
