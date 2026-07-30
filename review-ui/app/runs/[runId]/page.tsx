import { DashboardFrame } from "@/components/dashboard-frame";
import { RunDetailPage } from "@/components/run-detail-page";

export default async function Page({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <DashboardFrame active="runs">
      <RunDetailPage runId={runId} />
    </DashboardFrame>
  );
}
