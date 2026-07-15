import type { Metadata } from "next";

import { NetWorthCard } from "@/components/nafi/net-worth-card";
import { ConnectedBanksCard } from "@/components/nafi/connected-banks-card";
import { IntegratedServicesCard } from "@/components/nafi/integrated-services-card";
import { PortfolioCard } from "@/components/nafi/portfolio-card";
import { AccountActivityCard } from "@/components/nafi/account-activity-card";
import { RecipientsGraphCard } from "@/components/nafi/recipients-graph-card";
import { DashboardDataNotice } from "@/components/nafi/dashboard-data-notice";

export const metadata: Metadata = {
  title: "Overview",
};

/** Bento dashboard — asymmetric grid on desktop, single stack on mobile. */
export default function OverviewPage() {
  return (
    <>
      <DashboardDataNotice />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <NetWorthCard className="lg:col-span-6" />
        <ConnectedBanksCard className="lg:col-span-6" />

        <IntegratedServicesCard className="lg:col-span-12" />

        <PortfolioCard className="lg:col-span-6" />
        <AccountActivityCard className="lg:col-span-6" />

        <RecipientsGraphCard className="lg:col-span-12" />
      </div>
    </>
  );
}
