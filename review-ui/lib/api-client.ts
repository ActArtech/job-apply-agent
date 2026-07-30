const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8008").replace(/\/+$/, "");

export function apiUrl(path: string) {
  return `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  const text = await response.text();
  const contentType = response.headers.get("content-type") ?? "";
  const preview = text.slice(0, 180).replace(/\s+/g, " ").trim();
  if (!response.ok) throw new Error(`${path} failed HTTP ${response.status}: ${preview}`);
  if (!contentType.includes("application/json")) throw new Error(`${path} returned ${contentType}: ${preview}`);
  try { return JSON.parse(text) as T; } catch (e) { throw new Error(`${path} invalid JSON: ${e}`); }
}

export const api = {
  jobs: {
    list: () => fetchJson<import("./types").JobSummary[]>("/jobs"),
    get: (id: string) => fetchJson<import("./types").JobDetail>(`/jobs/${id}`),
    review: (id: string, status: string, notes = "") =>
      fetchJson(`/jobs/${id}/review`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ status, notes }) }),
    vet: (id: string, approved: boolean, reason = "Manual override") =>
      fetchJson<{ ok: boolean; approved: boolean }>(`/jobs/${id}/vet`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ approved, reason }) }),
    send: (id: string, to_email: string) =>
      fetchJson(`/jobs/${id}/send`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ to_email }) }),
    followup: (id: string, to_email: string) =>
      fetchJson(`/jobs/${id}/followup`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ to_email }) }),
    regen: (id: string, hint = "") =>
      fetchJson<{ run_id: string }>(`/jobs/${id}/regen`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hint }) }),
    tracking: (id: string) => fetchJson<import("./types").TrackingEntry>(`/jobs/${id}/tracking`),
    updateTracking: (id: string, status: string, notes = "") =>
      fetchJson<import("./types").TrackingEntry>(`/jobs/${id}/tracking`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ status, notes }) }),
    history: (id: string) => fetchJson<import("./types").HistoryEvent[]>(`/jobs/${id}/history`),
    artifact: (id: string, name: string) => apiUrl(`/jobs/${id}/artifact/${name}`),
    bulkSend: (job_ids: string[], dry_run = false) =>
      fetchJson<import("./types").BulkSendResult>("/jobs/bulk-send", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ job_ids, dry_run }),
      }),
    pdfDownloadUrl: (id: string) => apiUrl(`/jobs/${id}/pdf-download`),
    updateEmailDraft: (id: string, body: string) =>
      fetchJson<{ ok: boolean }>(`/jobs/${id}/email-draft`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ body }) }),
    updateTrackingEmail: (id: string, to_email: string) =>
      fetchJson<import("./types").TrackingEntry>(`/jobs/${id}/tracking/email`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ to_email }) }),
    directApply: (id: string) =>
      fetchJson<{ ok: boolean; message: string }>(`/jobs/${id}/direct-apply`, { method: "POST" }),
    selectProvider: (id: string, provider: "gemini" | "groq") =>
      fetchJson<{ ok: boolean; selected: string }>(`/jobs/${id}/generation/select`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ provider }) }),
  },
  phases: {
    start: (phase: string, body: Record<string, unknown> = {}) =>
      fetchJson<{ run_id: string }>(`/phases/${phase}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
    phase2Single: (jobId: string) =>
      fetchJson<{ run_id: string }>("/phases/phase2-single", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jobId }) }),
  },
  system: {
    openFolder: (path: string) =>
      fetchJson<{ ok: boolean }>("/system/open-folder", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ path }) }),
  },
  runs: {
    list: () => fetchJson<import("./types").RunState[]>("/runs"),
    get: (id: string) => fetchJson<import("./types").RunState>(`/runs/${id}`),
    eventsUrl: (id: string) => apiUrl(`/runs/${id}/events`),
  },
  profile: {
    get: () => fetchJson<import("./types").UserProfile>("/profile"),
    update: (data: Partial<import("./types").UserProfile>) =>
      fetchJson<import("./types").UserProfile>("/profile", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(data) }),
  },
  criteria: {
    get: () => fetchJson<import("./types").Criteria>("/criteria"),
    update: (data: Partial<import("./types").Criteria>) =>
      fetchJson<import("./types").Criteria>("/criteria", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(data) }),
  },
  settings: {
    get: () => fetchJson<import("./types").AppSettings>("/settings"),
    update: (data: Partial<import("./types").AppSettings>) =>
      fetchJson<import("./types").AppSettings>("/settings", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(data) }),
  },
  analytics: {
    funnel: () => fetchJson<import("./types").AnalyticsFunnel>("/analytics/funnel"),
    responseRate: () => fetchJson<import("./types").AnalyticsResponseRate>("/analytics/response-rate"),
    sources: () => fetchJson<import("./types").AnalyticsSource[]>("/analytics/sources"),
    sentToday: () => fetchJson<import("./types").SentToday>("/analytics/sent-today"),
  },
  health: () => fetchJson<{ ok: boolean }>("/health"),
};
