"use client";

import { ArrowDownLeft, ArrowLeftRight, CreditCard, FileText, Smartphone } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import type { DashboardActivity } from "@/lib/dashboard";
import { useFormat, useLang } from "@/lib/i18n";

const upcomingIcons = { utilities: FileText, phone: Smartphone };

export function AccountActivityCard({
  data,
  className,
}: {
  data: DashboardActivity;
  className?: string;
}) {
  const { t } = useLang();
  const fmt = useFormat();
  const metrics = [
    { key: "linkedAccounts", value: data.metrics.linked_accounts },
    { key: "monthlySpend", value: Number(data.metrics.monthly_spend_sar), money: true },
    { key: "unpaidBills", value: data.metrics.unpaid_bills },
    { key: "savedRecipients", value: data.metrics.saved_recipients },
  ];

  return (
    <BentoCard className={className}>
      <CardTitle title={t("accountActivity")} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Recent — orange. Dark ink on the warm fill reads at 7.2:1 (AAA). */}
        <div className="rounded-xl bg-gradient-to-br from-orange to-[#d0754a] p-4 text-[#2a1409]">
          <p className="text-[13px] font-semibold">{t("recentTransactions")}</p>
          <ul className="mt-3 space-y-2.5">
            {data.recent.map((transaction) => {
              const Icon =
                transaction.kind === "transfer"
                  ? ArrowLeftRight
                  : transaction.kind === "deposit"
                    ? ArrowDownLeft
                    : CreditCard;
              const label =
                transaction.kind === "transfer"
                  ? t("transferTo", { name: transaction.counterparty })
                  : transaction.kind === "deposit"
                    ? t("depositFrom", { name: transaction.counterparty })
                    : t("paymentTo", { name: transaction.counterparty });
              return (
                <li key={transaction.id} className="flex items-center gap-2.5 text-[12px]">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-black/15">
                    <Icon className="size-3.5 rtl:-scale-x-100" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1 truncate leading-tight">{label}</span>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums" dir="ltr">
                    {transaction.kind === "deposit" ? "+" : "−"}
                    {fmt.money(Number(transaction.amount_sar))}
                  </span>
                </li>
              );
            })}
            {data.recent.length === 0 ? (
              <li className="text-[12px] opacity-75">{t("noTransactions")}</li>
            ) : null}
          </ul>
        </div>

        {/*
         * Upcoming — purple. Ink is dark, not white: white on this violet was
         * 3.2:1 and failed AA. Dark ink on the softened fill reads at 6.8:1 and
         * matches the orange panel's treatment.
         */}
        <div className="rounded-xl bg-gradient-to-br from-purple to-[#8f7ee8] p-4 text-[#1a1440]">
          <p className="text-[13px] font-semibold">{t("upcomingPayments")}</p>
          <ul className="mt-3 space-y-2.5">
            {data.upcoming.map((payment) => {
              const Icon = upcomingIcons[payment.icon];
              return (
                <li key={payment.id} className="flex items-center gap-2.5 text-[12px]">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-black/15">
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1 truncate">{payment.biller}</span>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums" dir="ltr">
                    {fmt.money(Number(payment.amount_sar))}
                  </span>
                </li>
              );
            })}
            {data.upcoming.length === 0 ? (
              <li className="text-[12px] opacity-75">{t("noUpcomingPayments")}</li>
            ) : null}
          </ul>
        </div>
      </div>

      {/* Metrics */}
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {metrics.map((m) => (
          <div key={m.key} className="rounded-xl border border-white/[0.05] bg-card-2 px-3.5 py-2.5">
            <p className="text-[11px] text-muted-foreground">{t(m.key)}</p>
            <p className="mt-0.5 text-base font-semibold tabular-nums" dir="ltr">
              {m.money ? fmt.money(m.value) : fmt.num(m.value)}
            </p>
          </div>
        ))}
      </div>
    </BentoCard>
  );
}
