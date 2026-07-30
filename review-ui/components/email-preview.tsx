"use client";
import type { JobDetail } from "@/lib/types";

export function EmailPreview({ job }: { job: JobDetail }) {
  const subject = job.package?.email_subject ?? null;
  const body = job.package?.email_body ?? null;
  if (!body) {
    return <p className="text-xs text-muted font-mono">No email generated.</p>;
  }

  return (
    <div className="space-y-3">
      {subject && (
        <div className="rounded border border-border bg-[#10110f] px-3 py-2">
          <span className="font-mono text-[10px] uppercase text-muted/60 block mb-1">Subject</span>
          <p className="text-sm text-foreground">{subject}</p>
        </div>
      )}
      <div className="rounded border border-border bg-[#10110f] px-3 py-3">
        <span className="font-mono text-[10px] uppercase text-muted/60 block mb-2">Body</span>
        <pre className="whitespace-pre-wrap text-xs text-foreground/80 font-sans leading-relaxed">{body}</pre>
      </div>
    </div>
  );
}
