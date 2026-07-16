"use client";

import { AccountActivityCard } from "@/components/nafi/account-activity-card";
import { BentoCard } from "@/components/nafi/bento-card";
import { ConnectedBanksCard } from "@/components/nafi/connected-banks-card";
import { DashboardDataNotice } from "@/components/nafi/dashboard-data-notice";
import { useDashboardData } from "@/components/nafi/dashboard-data-provider";
import { IntegratedServicesCard } from "@/components/nafi/integrated-services-card";
import { NetWorthCard } from "@/components/nafi/net-worth-card";
import { NafiWalletCard } from "@/components/nafi/nafi-wallet-card";
import { PortfolioCard } from "@/components/nafi/portfolio-card";
import { RecipientsGraphCard } from "@/components/nafi/recipients-graph-card";

const RISE = "animate-rise";

export function DashboardOverview() {
  const { snapshot, status, error, refresh } = useDashboardData();

  return (
    <>
      <DashboardDataNotice
        status={status}
        error={error}
        onRetry={() => void refresh()}
      />

      {snapshot ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-5">
          <NetWorthCard
            data={snapshot.net_worth}
            asOf={snapshot.as_of}
            className={`${RISE} lg:col-span-7`}
          />
          <NafiWalletCard
            wallet={snapshot.wallet}
            accounts={snapshot.accounts}
            className={`${RISE} [animation-delay:70ms] lg:col-span-5`}
          />

          <ConnectedBanksCard
            accounts={snapshot.accounts}
            className={`${RISE} [animation-delay:140ms] lg:col-span-5`}
          />
          <PortfolioCard
            data={snapshot.portfolio}
            className={`${RISE} [animation-delay:210ms] lg:col-span-7`}
          />
          <AccountActivityCard
            data={snapshot.activity}
            className={`${RISE} [animation-delay:280ms] lg:col-span-12`}
          />

          <IntegratedServicesCard
            accounts={snapshot.accounts}
            refreshing={status === "refreshing"}
            onRefresh={() => void refresh()}
            className={`${RISE} [animation-delay:350ms] lg:col-span-12`}
          />

          <RecipientsGraphCard
            recipients={snapshot.recipients}
            className={`${RISE} [animation-delay:420ms] lg:col-span-12`}
          />
        </div>
      ) : status === "loading" ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-5" aria-hidden>
          {[
            "lg:col-span-7",
            "lg:col-span-5",
            "lg:col-span-5",
            "lg:col-span-7",
            "lg:col-span-12",
            "lg:col-span-12",
            "lg:col-span-12",
          ].map((spanClass, index) => (
            <BentoCard
              key={`${spanClass}-${index}`}
              className={`min-h-48 animate-pulse ${spanClass}`}
            />
          ))}
        </div>
      ) : null}
    </>
  );
}
