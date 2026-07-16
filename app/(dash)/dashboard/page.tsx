import type { Metadata } from "next";

import { DashboardOverview } from "@/components/nafi/dashboard-overview";

export const metadata: Metadata = {
  title: "Overview",
};

export default function OverviewPage() {
  return <DashboardOverview />;
}
