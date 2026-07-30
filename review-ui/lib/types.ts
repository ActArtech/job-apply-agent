export type ReviewStatus = "pending" | "approved" | "rejected" | "needs_regen";
export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export type VettingStatus = "approved" | "rejected" | "error";

export type VettingInfo = {
  status?: VettingStatus;
  approved?: boolean | null;
  reason?: string;
  error?: string;
  score?: number;
  engine?: { requested: string; answered: string | null };
};

export function vettingStatusOf(v: VettingInfo | undefined | null): VettingStatus | null {
  if (!v || Object.keys(v).length === 0) return null;
  if (v.status) return v.status;
  if (typeof v.reason === "string" && v.reason.startsWith("AI vetting failed")) return "error";
  return v.approved === true ? "approved" : "rejected";
}

export type RunEvent =
  | { type: "phase_start"; phase: string; total?: number; engine?: string; at?: string }
  | { type: "job_start"; job_id: string; company: string; title: string; index: number; total: number; at?: string }
  | { type: "job_result"; job_id: string; company: string; title: string; status: string; reason: string; engine?: string | null; score?: number; at?: string }
  | { type: "progress"; done: number; total: number; approved?: number; rejected?: number; errors?: number; at?: string }
  | { type: "phase_done"; phase: string; at?: string; [key: string]: unknown };
export type TrackingStatus = "sent" | "replied" | "interview" | "offer" | "rejected" | "withdrawn";

export type SingleGeneration = {
  status?: string;
  provider?: string;
  page_count?: number;
  impact_signal_ratio?: number;
  numeric_bullets?: number;
  total_bullets?: number;
  pdf_path?: string;
};

export type BothGeneration = {
  status?: string;
  provider: "both";
  selected: "gemini" | "groq" | null;
  gemini: SingleGeneration | null;
  groq: SingleGeneration | null;
};

export type Generation = SingleGeneration | BothGeneration;

export function getGenerationStats(gen: Generation | undefined): SingleGeneration | undefined {
  if (!gen) return undefined;
  if ((gen as BothGeneration).provider === "both") {
    const both = gen as BothGeneration;
    const sel = both.selected;
    return sel ? (both[sel] ?? undefined) : undefined;
  }
  return gen as SingleGeneration;
}

export type JobSummary = {
  job_id: string;
  company: string;
  title: string;
  source: string;
  url: string;
  location?: string;
  work_mode?: "remote" | "hybrid" | "wfo" | "unknown";
  region?: "india" | "foreign" | "unknown";
  remote?: boolean;
  created_at?: string;
  vetting?: VettingInfo;
  generation?: Generation;
  package?: { match_score: number };
  review?: { status: ReviewStatus; notes?: string };
  tracking?: { status: TrackingStatus; updated_at?: string };
  contact?: { email?: string; linkedin_url?: string; discovery_method?: string };
};

export type JobDetail = JobSummary & {
  jd: string;
  artifacts_dir?: string;
  contact?: ContactInfo;
  package?: {
    match_score: number;
    keywords_matched?: string[];
    keywords_missing?: string[];
    tailored_experience?: Array<{ company: string; role: string; bullets: string[] }>;
    tailored_skills?: Record<string, string[]>;
    email_subject?: string;
    email_body?: string;
  };
};

export type RunState = {
  run_id: string;
  phase: string;
  status: RunStatus;
  logs: string[];
  events?: RunEvent[];
  result?: Record<string, unknown> | null;
  error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type AnalyticsFunnel = {
  gathered: number; vetted: number; approved: number;
  generated: number; reviewed: number; sent: number;
};

export type AnalyticsResponseRate = {
  sent: number; replied: number; interview: number; offer: number;
  rate_reply: number; rate_interview: number;
};

export type AnalyticsSource = {
  source: string; total: number; approved: number; generated: number; sent: number;
};

export type UserProfile = {
  name: string; email: string; base_resume_text: string;
  target_roles: string[]; years_experience: number;
};

export type Criteria = {
  require_remote: boolean; salary_floor: number;
  exclude_sources: string[]; exclude_keywords: string[];
};

export type AppSettings = {
  gemini_key: string; groq_key: string; hunter_key: string;
  apollo_key: string; serper_key: string; gmail_token_path: string;
  max_per_source: number; daily_email_limit: number;
  scraper_sources: Record<string, boolean>;
  auto_send?: boolean;
  ai_engine?: "gemini" | "groq" | "both";
};

export type SentToday = { sent_today: number; limit: number };

export type BulkSendResult = {
  results: Record<string, { ok: boolean; error?: string; to_email?: string }>;
  sent: number;
  dry_run: boolean;
};

export type TrackingEntry = {
  status: TrackingStatus; notes?: string; updated_at?: string;
  to_email?: string; sent_at?: string;
  history?: Array<{ status: string; at: string }>;
};

export type HistoryEvent = { event: string; phase?: string; at: string; detail?: string; run_id?: string; hint?: string };

export type ContactInfo = {
  email: string;
  first_name: string;
  last_name: string;
  title?: string;
  linkedin_url?: string;
  discovery_method?: string;
  found_at?: string;
};
