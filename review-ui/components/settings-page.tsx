"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { UserProfile, Criteria, AppSettings } from "@/lib/types";
import { toast } from "@/components/ui/toast";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SkeletonList } from "@/components/ui/skeleton";

type Tab = "profile" | "criteria" | "keys" | "sources";

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("profile");
  const [profile, setProfile] = useState<Partial<UserProfile>>({});
  const [criteria, setCriteria] = useState<Partial<Criteria>>({});
  const [settings, setSettings] = useState<Partial<AppSettings>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([api.profile.get(), api.criteria.get(), api.settings.get()])
      .then(([p, c, s]) => { setProfile(p); setCriteria(c); setSettings(s); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      if (tab === "profile") await api.profile.update(profile);
      if (tab === "criteria") await api.criteria.update(criteria);
      if (tab === "keys") await api.settings.update(settings);
      if (tab === "sources") await api.settings.update(settings);
      toast("Saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "profile", label: "Profile" },
    { key: "criteria", label: "Criteria" },
    { key: "keys", label: "API Keys" },
    { key: "sources", label: "Sources" },
  ];

  if (loading) return <SkeletonList rows={8} />;

  return (
    <div className="p-6 max-w-2xl space-y-6">
      {error && <ErrorBanner message={error} onRetry={() => setError("")} />}

      <div className="flex gap-2">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`rounded border px-4 py-2 text-xs font-mono transition ${tab === t.key ? "border-accent text-accent" : "border-border text-muted hover:text-foreground"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "profile" && (
        <div className="space-y-4">
          {(["name", "email"] as const).map((field) => (
            <label key={field} className="block space-y-1">
              <span className="font-mono text-[10px] uppercase text-muted">{field}</span>
              <input value={(profile as Record<string, string>)[field] ?? ""} onChange={(e) => setProfile({ ...profile, [field]: e.target.value })}
                className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none" />
            </label>
          ))}
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Base Resume</span>
            <textarea value={profile.base_resume_text ?? ""} onChange={(e) => setProfile({ ...profile, base_resume_text: e.target.value })} rows={10}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none font-mono" />
          </label>
        </div>
      )}

      {tab === "criteria" && (
        <div className="space-y-4">
          <label className="flex items-center gap-3">
            <input type="checkbox" checked={criteria.require_remote ?? false}
              onChange={(e) => setCriteria({ ...criteria, require_remote: e.target.checked })}
              className="accent-accent" />
            <span className="text-sm text-foreground">Remote only</span>
          </label>
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Salary Floor (USD/year)</span>
            <input type="number" value={criteria.salary_floor ?? 0}
              onChange={(e) => setCriteria({ ...criteria, salary_floor: Number(e.target.value) })}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none" />
          </label>
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Exclude Keywords (comma-separated)</span>
            <input value={(criteria.exclude_keywords ?? []).join(", ")}
              onChange={(e) => setCriteria({ ...criteria, exclude_keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none" />
          </label>
        </div>
      )}

      {tab === "keys" && (
        <div className="space-y-4">
          {(["gemini_key", "groq_key", "hunter_key", "apollo_key", "serper_key"] as const).map((field) => (
            <label key={field} className="block space-y-1">
              <span className="font-mono text-[10px] uppercase text-muted">{field.replace("_key", "").toUpperCase()} API Key</span>
              <input value={(settings as Record<string, string>)[field] ?? ""} onChange={(e) => setSettings({ ...settings, [field]: e.target.value })}
                type="password"
                className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none font-mono" />
            </label>
          ))}
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Max Jobs Per Source</span>
            <input type="number" value={settings.max_per_source ?? 20}
              onChange={(e) => setSettings({ ...settings, max_per_source: Number(e.target.value) })}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none" />
          </label>
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Default AI Engine</span>
            <select
              value={settings.ai_engine ?? "gemini"}
              onChange={(e) => setSettings({ ...settings, ai_engine: e.target.value as AppSettings["ai_engine"] })}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none font-mono"
            >
              <option value="gemini">Gemini (falls back to Groq)</option>
              <option value="groq">Groq (falls back to Gemini)</option>
              <option value="both">Both (compare)</option>
            </select>
            <span className="block text-[10px] text-muted">Used by Vet and Generate unless overridden per run.</span>
          </label>
        </div>
      )}

      {tab === "sources" && (
        <div className="space-y-6">
          <div>
            <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">Scrapers</div>
            <div className="space-y-3">
              {(["wellfound", "yc", "instahyre"] as const).map((src) => (
                <label key={src} className="flex items-center justify-between rounded border border-border bg-[#171815] px-4 py-3">
                  <span className="text-sm text-foreground">{src === "yc" ? "YC (Work at a Startup)" : src.charAt(0).toUpperCase() + src.slice(1)}</span>
                  <input
                    type="checkbox"
                    checked={settings.scraper_sources?.[src] ?? true}
                    onChange={(e) => setSettings({
                      ...settings,
                      scraper_sources: { ...(settings.scraper_sources ?? {}), [src]: e.target.checked },
                    })}
                    className="accent-accent"
                  />
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted">Automation</div>
            <label className="flex items-center justify-between rounded border border-border bg-[#171815] px-4 py-3">
              <div>
                <div className="text-sm text-foreground">Auto-send on Approve</div>
                <div className="text-[10px] text-muted mt-0.5">Immediately sends email when a job is approved in Review Queue</div>
              </div>
              <input
                type="checkbox"
                checked={settings.auto_send ?? false}
                onChange={(e) => setSettings({ ...settings, auto_send: e.target.checked })}
                className="accent-accent"
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="font-mono text-[10px] uppercase text-muted">Daily Email Limit</span>
            <input
              type="number"
              min={1}
              max={100}
              value={settings.daily_email_limit ?? 10}
              onChange={(e) => setSettings({ ...settings, daily_email_limit: Number(e.target.value) })}
              className="w-full rounded border border-border bg-[#171815] px-3 py-2 text-sm text-foreground focus:border-accent/50 focus:outline-none"
            />
          </label>
        </div>
      )}

      <button onClick={save} disabled={saving}
        className="rounded border border-accent px-6 py-2 text-xs font-mono text-accent hover:bg-accent/10 transition disabled:opacity-50">
        {saving ? "Saving..." : "Save"}
      </button>
    </div>
  );
}
