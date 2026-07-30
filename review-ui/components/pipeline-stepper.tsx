"use client";
import { vettingStatusOf, type JobDetail } from "@/lib/types";

type StepState = "done" | "active" | "error" | "todo";

function steps(job: JobDetail): Array<{ label: string; state: StepState; detail: string; anchor: string }> {
  const vet = vettingStatusOf(job.vetting);
  const generated = job.generation?.status === "generated";
  const contactState: StepState = job.contact?.email
    ? "done"
    : job.contact?.discovery_method
      ? "error"
      : generated
        ? "active"
        : "todo";
  const manual = job.vetting?.engine?.requested === "manual";
  const pageCount = job.generation && "page_count" in job.generation ? job.generation.page_count : undefined;
  return [
    { label: "Gathered", state: "done", detail: job.source, anchor: "" },
    {
      label: "Vetted",
      state: vet === "approved" ? "done" : vet === "error" || vet === "rejected" ? "error" : "active",
      detail: vet === "error" ? "couldn't vet" : vet ? `${vet}${manual ? " (manual)" : ""}` : "pending",
      anchor: "#curation",
    },
    {
      label: "Generated",
      state: generated ? "done" : vet === "approved" ? "active" : "todo",
      detail: generated ? (pageCount ? `${pageCount}p PDF` : "done") : "—",
      anchor: "#metrics",
    },
    {
      label: "Contact",
      state: contactState,
      detail: job.contact?.email ?? job.contact?.discovery_method ?? "—",
      anchor: "#contact",
    },
    {
      label: "Sent",
      state: job.tracking?.status ? "done" : "todo",
      detail: job.tracking?.status ?? "—",
      anchor: "",
    },
  ];
}

const stepStyle: Record<StepState, string> = {
  done: "border-emerald-800/60 text-emerald-400",
  active: "border-accent/60 text-accent",
  error: "border-amber-800/60 text-amber-400",
  todo: "border-border text-muted",
};

const stepIcon: Record<StepState, string> = { done: "✓", active: "●", error: "⚠", todo: "—" };

export function PipelineStepper({ job }: { job: JobDetail }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      {steps(job).map((step, i) => (
        <div key={step.label} className="flex items-center gap-2">
          {i > 0 && <span className="text-muted/40">→</span>}
          <a
            href={step.anchor || undefined}
            className={`flex items-center gap-2 rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider ${stepStyle[step.state]} ${step.anchor ? "hover:bg-[#1a1b18]/70" : "cursor-default"}`}
          >
            <span>{stepIcon[step.state]}</span>
            <span>{step.label}</span>
            <span className="normal-case text-muted">{step.detail}</span>
          </a>
        </div>
      ))}
    </div>
  );
}
