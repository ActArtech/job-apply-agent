import { DashboardFrame } from "@/components/dashboard-frame";
import { SettingsPage } from "@/components/settings-page";

export default function Page() {
  return (
    <DashboardFrame active="settings">
      <SettingsPage />
    </DashboardFrame>
  );
}
