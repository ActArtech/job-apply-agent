import { DashboardFrame } from "@/components/dashboard-frame";
import { JobDetailPage } from "@/components/job-detail-page";

export default async function Page({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return (
    <DashboardFrame active="jobs">
      <JobDetailPage jobId={jobId} />
    </DashboardFrame>
  );
}
