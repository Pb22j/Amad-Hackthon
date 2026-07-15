import type { Metadata } from "next";

import { NetWorthCard } from "@/components/nafi/net-worth-card";
import { ConnectedBanksCard } from "@/components/nafi/connected-banks-card";
import { IntegratedServicesCard } from "@/components/nafi/integrated-services-card";
import { PortfolioCard } from "@/components/nafi/portfolio-card";
import { AccountActivityCard } from "@/components/nafi/account-activity-card";
import { RecipientsGraphCard } from "@/components/nafi/recipients-graph-card";

export const metadata: Metadata = {
  title: "Overview",
};

/**
 * Bento dashboard — asymmetric grid on desktop, single stack on mobile.
 *
 * The spans zigzag (7/5 then 5/7) so the eye travels diagonally instead of
 * reading a uniform tile wall. Each card rises in on mount, staggered by
 * position. NetWorthCard must stay paired with ConnectedBanksCard on row 1:
 * the bank list is height-driven by its neighbour (see that component).
 */
const RISE = "animate-rise";

export default function OverviewPage() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-5">
      {/* Row 1 — hero figure, bank list beside it. */}
      <NetWorthCard className={`${RISE} lg:col-span-7`} />
      <ConnectedBanksCard className={`${RISE} [animation-delay:70ms] lg:col-span-5`} />

      {/* Row 2 — mirrored spans. */}
      <PortfolioCard className={`${RISE} [animation-delay:140ms] lg:col-span-5`} />
      <AccountActivityCard className={`${RISE} [animation-delay:210ms] lg:col-span-7`} />

      {/* Row 3 — slim full-width strip. */}
      <IntegratedServicesCard className={`${RISE} [animation-delay:280ms] lg:col-span-12`} />

      {/* Row 4 — the relationship graph gets the full width it needs. */}
      <RecipientsGraphCard className={`${RISE} [animation-delay:350ms] lg:col-span-12`} />
    </div>
  );
}
