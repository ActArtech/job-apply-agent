import type { JobDetail } from "@/lib/types";
import { Award, Briefcase, FileText } from "lucide-react";

export function ResumePanel({ job }: { job: JobDetail }) {
  const pkg = job.package;
  if (!pkg) {
    return (
      <div className="h-full min-h-0 flex flex-col items-center justify-center border border-dashed border-border rounded-xl bg-[#131412] p-8 text-center">
        <FileText className="h-8 w-8 text-muted mb-2 stroke-[1.5]" />
        <h3 className="text-sm font-medium text-foreground mb-1">No generated resume</h3>
        <p className="text-xs text-muted max-w-xs">
          This job application has not had tailored resume bullets generated yet. Use the Action Rail to generate artifacts.
        </p>
      </div>
    );
  }
  const tailoredExperience = pkg.tailored_experience ?? [];
  const tailoredSkills = pkg.tailored_skills ?? {};

  return (
    <div data-testid="resume-panel-scroll" className="h-full min-h-0 overflow-auto space-y-6 pr-2 pb-6">
      {/* Experience Section */}
      <div className="bg-[#131412] border border-border rounded-xl p-6 space-y-6">
        <div className="flex items-center gap-2 pb-3 border-b border-border/40">
          <Briefcase className="h-4 w-4 text-accent" />
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted">Tailored Professional Experience</h2>
        </div>

        <div className="space-y-6">
          {tailoredExperience.map((exp, idx) => (
            <div key={`${exp.company}-${idx}`} className="space-y-2 group">
              <div className="flex justify-between items-baseline">
                <h3 className="text-sm font-semibold text-foreground tracking-wide font-sans group-hover:text-accent transition">
                  {exp.company}
                </h3>
                <span className="text-[10px] font-mono text-muted bg-[#1c1d1a]/50 px-2 py-0.5 rounded border border-border/20">
                  {exp.role.includes("Project") ? "Project" : "Professional"}
                </span>
              </div>
              <div className="text-xs font-mono text-muted">{exp.role}</div>
              <ul className="mt-2 space-y-2 pl-4 border-l border-border/30">
                {exp.bullets.map((bullet, bIdx) => (
                  <li key={bIdx} className="text-sm leading-6 text-[#bfc2b9] font-sans relative before:content-['•'] before:absolute before:-left-3 before:text-accent">
                    {bullet}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Skills Section */}
      <div className="bg-[#131412] border border-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-border/40">
          <Award className="h-4 w-4 text-accent" />
          <h2 className="text-xs font-mono uppercase tracking-wider text-muted">Tailored Technical Skills</h2>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(tailoredSkills).map(([key, items]) => (
            <div key={key} className="p-3 bg-[#171815] border border-border/40 rounded-lg space-y-1">
              <div className="text-xs font-mono text-muted uppercase">{key}</div>
              <div className="text-sm font-sans font-medium text-foreground leading-relaxed">
                {Array.isArray(items) ? items.join(", ") : String(items)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
