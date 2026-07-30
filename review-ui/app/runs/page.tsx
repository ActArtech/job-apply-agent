import { DashboardFrame } from "@/components/dashboard-frame";
import { RunsPage } from "@/components/runs-page";

export default function Page() {
  return (
    <DashboardFrame active="runs">
      <RunsPage />
    </DashboardFrame>
  );
}
