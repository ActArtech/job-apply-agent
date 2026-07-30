import { DashboardFrame } from "@/components/dashboard-frame";
import { PhasePage } from "@/components/phase-page";

export default async function Page({ params }: { params: Promise<{ phase: string }> }) {
  const { phase } = await params;
  return (
    <DashboardFrame active={`phase-${phase}`}>
      <PhasePage phase={phase} />
    </DashboardFrame>
  );
}
