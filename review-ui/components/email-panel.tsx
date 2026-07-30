"use client";

import { useState } from "react";
import type { JobDetail } from "@/lib/types";
import { api } from "@/lib/api-client";
import { Mail, Send, Copy, Check, Pencil, X, Save } from "lucide-react";
import { toast } from "@/components/ui/toast";

export function EmailPanel({
  job,
  onBodySaved,
}: {
  job: JobDetail;
  onBodySaved?: (newBody: string) => void;
}) {
  const pkg = job.package;
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftBody, setDraftBody] = useState(pkg?.email_body ?? "");
  const [saving, setSaving] = useState(false);

  if (!pkg) {
    return (
      <div className="h-full min-h-0 flex flex-col items-center justify-center border border-dashed border-border rounded-xl bg-[#131412] p-8 text-center">
        <Mail className="h-8 w-8 text-muted mb-2 stroke-[1.5]" />
        <h3 className="text-sm font-medium text-foreground mb-1">No email generated</h3>
        <p className="text-xs text-muted max-w-xs">
          The tailored cold email has not been generated yet. Use the Action Rail to generate artifacts.
        </p>
      </div>
    );
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(pkg?.email_body ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast("Copy failed", "error");
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await api.jobs.updateEmailDraft(job.job_id, draftBody);
      toast("Email draft saved", "success");
      onBodySaved?.(draftBody);
      setEditing(false);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  }

  function handleCancelEdit() {
    setDraftBody(pkg?.email_body ?? "");
    setEditing(false);
  }

  return (
    <div className="h-full min-h-0 flex flex-col gap-4 overflow-hidden">
      {/* Email Header Card */}
      <div className="bg-[#131412] border border-border p-4 rounded-xl space-y-3 shrink-0">
        <div className="grid grid-cols-[60px_1fr] items-center text-xs font-mono">
          <span className="text-muted">Subject:</span>
          <span className="text-foreground font-semibold font-sans">{pkg.email_subject || "No subject generated"}</span>
        </div>
        <div className="pt-2 border-t border-border/30 grid grid-cols-[60px_1fr] items-center text-xs font-mono">
          <span className="text-muted">From:</span>
          <span className="text-muted">Sohaib &lt;sohaib@example.com&gt;</span>
        </div>
      </div>

      {/* Email Body Card */}
      <div className="flex-1 overflow-auto rounded-xl border border-border bg-[#131412] p-6 shadow-inner relative flex flex-col">
        <div className="absolute top-4 right-4 flex items-center gap-2">
          {!editing && (
            <>
              <button
                onClick={() => setEditing(true)}
                title="Edit draft"
                className="flex items-center gap-1 text-[10px] font-mono text-muted hover:text-foreground transition"
              >
                <Pencil className="h-3 w-3" />
                <span>Edit</span>
              </button>
              <button
                onClick={handleCopy}
                title="Copy email body"
                className="flex items-center gap-1 text-[10px] font-mono text-muted hover:text-foreground transition"
              >
                {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
            </>
          )}
          {editing && (
            <>
              <button
                onClick={handleCancelEdit}
                title="Cancel edit"
                className="flex items-center gap-1 text-[10px] font-mono text-muted hover:text-foreground transition"
              >
                <X className="h-3 w-3" />
                <span>Cancel</span>
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                title="Save draft"
                className="flex items-center gap-1 text-[10px] font-mono text-accent hover:text-foreground transition"
              >
                <Save className="h-3 w-3" />
                <span>{saving ? "Saving…" : "Save"}</span>
              </button>
            </>
          )}
          {!editing && (
            <div className="text-[10px] font-mono text-muted uppercase tracking-widest bg-[#171815] px-2 py-0.5 rounded border border-border/40 select-none flex items-center gap-1.5">
              <Send className="h-3 w-3" />
              <span>Cold Email Draft</span>
            </div>
          )}
        </div>

        {editing ? (
          <textarea
            value={draftBody}
            onChange={(e) => setDraftBody(e.target.value)}
            className="flex-1 w-full mt-6 bg-transparent text-sm leading-7 text-[#bfc2b9] font-sans resize-none outline-none border border-border/40 rounded p-2 focus:border-accent/60 transition"
            rows={20}
          />
        ) : (
          <pre className="whitespace-pre-wrap text-sm leading-7 text-[#bfc2b9] font-sans pr-2 max-w-3xl pt-2">
            {pkg.email_body || "No email body text generated."}
          </pre>
        )}
      </div>
    </div>
  );
}
