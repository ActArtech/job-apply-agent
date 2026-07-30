import { DashboardFrame } from "@/components/dashboard-frame";
import { ReviewQueue } from "@/components/review-queue";

export default function Page() {
  return (
    <DashboardFrame active="review">
      <ReviewQueue />
    </DashboardFrame>
  );
}
