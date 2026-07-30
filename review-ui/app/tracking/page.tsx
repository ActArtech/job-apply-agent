import { DashboardFrame } from "@/components/dashboard-frame";
import { TrackingBoard } from "@/components/tracking-board";

export default function Page() {
  return (
    <DashboardFrame active="tracking">
      <TrackingBoard />
    </DashboardFrame>
  );
}
