"use client";

import { TrendingUp } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { useFormat, useLang } from "@/lib/i18n";
import { asOfDate, netWorth } from "@/lib/nafiData";

export function NetWorthCard({ className }: { className?: string }) {
  const { t } = useLang();
  const fmt = useFormat();

  return (
    <BentoCard className={className}>
      <CardTitle title={t("netWorth")} />

      <p
        dir="ltr"
        className="mt-2 bg-gradient-to-b from-white to-slate-400/80 bg-clip-text text-start text-5xl font-thin leading-none tracking-tight text-transparent tabular-nums sm:text-[3.4rem]"
      >
        {fmt.money(netWorth.amount)}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          {t("aggregatedFunds")}
        </p>
        <span className="inline-flex items-center gap-1 rounded-full bg-positive/10 px-2 py-0.5 text-xs font-medium text-positive" dir="ltr">
          <TrendingUp className="size-3" aria-hidden />
          {fmt.pct(netWorth.deltaPercent)}
        </span>
      </div>

      <p className="mt-3 text-[11px] text-faint">
        {t("asOf")} {fmt.date(asOfDate)}
      </p>
    </BentoCard>
  );
}
