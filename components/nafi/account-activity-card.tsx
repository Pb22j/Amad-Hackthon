"use client";

import { ArrowDownLeft, ArrowLeftRight, FileText, Smartphone } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { useFormat, useLang } from "@/lib/i18n";
import { activity } from "@/lib/nafiData";

const upcomingIcons = { utilities: FileText, phone: Smartphone };
const upcomingKeys = { utilities: "utilities", phone: "phoneBill" } as const;

export function AccountActivityCard({ className }: { className?: string }) {
  const { t, lang } = useLang();
  const fmt = useFormat();

  return (
    <BentoCard className={className}>
      <CardTitle title={t("accountActivity")} tag={`[${activity.cite}]`} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Recent — orange */}
        <div className="rounded-xl bg-gradient-to-br from-[#d97b4c] to-[#c05f3a] p-4 text-[#2a1409]">
          <p className="text-[13px] font-semibold">{t("recentTransactions")}</p>
          <ul className="mt-3 space-y-2.5">
            {activity.recent.map((r) => {
              const Icon = r.kind === "transfer" ? ArrowLeftRight : ArrowDownLeft;
              const name = lang === "ar" ? r.personAr : r.person;
              const label = r.kind === "transfer" ? t("transferTo", { name }) : t("depositFrom", { name });
              return (
                <li key={r.id} className="flex items-center gap-2.5 text-[12px]">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-black/15">
                    <Icon className="size-3.5 rtl:-scale-x-100" aria-hidden />
                  </span>
                  <span className="leading-tight">
                    {label}
                    <span className="mx-1 font-mono text-[10px] opacity-70" dir="ltr">[cite: {r.cite}]</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Upcoming — purple */}
        <div className="rounded-xl bg-gradient-to-br from-[#8f82ea] to-[#7166d6] p-4 text-white">
          <p className="text-[13px] font-semibold">{t("upcomingPayments")}</p>
          <ul className="mt-3 space-y-2.5">
            {activity.upcoming.map((u) => {
              const Icon = upcomingIcons[u.icon];
              return (
                <li key={u.id} className="flex items-center gap-2.5 text-[12px]">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-white/20">
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  {t(upcomingKeys[u.icon])}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {/* Metrics */}
      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {activity.metrics.map((m) => (
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
