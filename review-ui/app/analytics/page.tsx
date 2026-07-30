import { DashboardFrame } from "@/components/dashboard-frame";
import { AnalyticsPage } from "@/components/analytics-page";

export default function Page() {
  return (
    <DashboardFrame active="analytics">
      <AnalyticsPage />
    </DashboardFrame>
  );
}
