import { DashboardFrame } from "@/components/dashboard-frame";
import { OverviewPage } from "@/components/overview-page";

export default function Page() {
  return (
    <DashboardFrame active="overview">
      <OverviewPage />
    </DashboardFrame>
  );
}
