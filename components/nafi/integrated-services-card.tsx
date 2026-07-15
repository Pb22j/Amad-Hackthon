"use client";

import { RefreshCw } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import type { DashboardAccount } from "@/lib/dashboard";
import { useLang, useLocalize } from "@/lib/i18n";
import { bankFromDashboard } from "@/lib/nafiData";

export function IntegratedServicesCard({
  accounts,
  refreshing,
  onRefresh,
  className,
}: {
  accounts: DashboardAccount[];
  refreshing: boolean;
  onRefresh: () => void;
  className?: string;
}) {
  const { t } = useLang();
  const loc = useLocalize();
  return (
    <BentoCard className={className}>
      <CardTitle
        title={t("integratedServices")}
        action={
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:cursor-wait disabled:opacity-60"
          >
            <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} aria-hidden />
            {t("refresh")}
          </button>
        }
      />
      <div className="flex flex-wrap gap-2.5">
        {accounts.map((account) => {
          const bank = bankFromDashboard(account);
          return (
          <div
            key={account.id}
            className="inline-flex items-center gap-2.5 rounded-full border border-white/[0.06] bg-card-2 py-1.5 pe-4 ps-1.5"
          >
            <BankLogo bank={bank} size={30} className="rounded-full" />
            <span className="flex items-center gap-1.5 text-sm font-medium">
              {loc(bank.name, bank.nameAr)}
              {bank.code ? (
                <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                  ({bank.code})
                </span>
              ) : null}
            </span>
          </div>
          );
        })}
        {accounts.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noAccounts")}</p>
        ) : null}
      </div>
    </BentoCard>
  );
}
