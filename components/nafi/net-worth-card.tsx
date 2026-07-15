"use client";

import { TrendingUp } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { cn } from "@/lib/utils";
import { useFormat, useLang } from "@/lib/i18n";
import { asOfDate, netWorth } from "@/lib/nafiData";

/**
 * The hero of the bento. The figure is the loudest thing on the page: an
 * oversized, tightly-tracked numeral lit from behind by a primary bloom that
 * bleeds through the card's frost.
 */
export function NetWorthCard({ className }: { className?: string }) {
  const { t } = useLang();
  const fmt = useFormat();

  return (
    <BentoCard className={cn("flex flex-col", className)}>
      {/* Bloom behind the figure — sits under the content, above the glass. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -start-24 -top-28 -z-10 size-[22rem] rounded-full bg-primary/25 blur-[90px]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -end-16 top-1/3 -z-10 size-56 rounded-full bg-purple/20 blur-[80px]"
      />

      <CardTitle title={t("netWorth")} />

      <p
        dir="ltr"
        className="numeral mt-1 bg-gradient-to-b from-white via-white to-slate-300 bg-clip-text text-start text-[3.25rem] font-light leading-[0.95] text-transparent sm:text-[4.25rem]"
      >
        {fmt.money(netWorth.amount)}
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          {t("aggregatedFunds")}
          <span className="mx-1.5 font-mono text-faint" dir="ltr">
            [cite: {netWorth.cite}]
          </span>
        </p>
        <span
          className="inline-flex items-center gap-1 rounded-full border border-positive/25 bg-positive/10 px-2.5 py-1 text-xs font-semibold text-positive shadow-[0_0_22px_-6px_rgb(78_196_155/0.7)]"
          dir="ltr"
        >
          <TrendingUp className="size-3" aria-hidden />
          {fmt.pct(netWorth.deltaPercent)}
        </span>
      </div>

      {/* Pushed to the floor of the card so the hero never leaves a void beneath it. */}
      <p className="mt-auto pt-6 text-[11px] text-faint">
        {t("asOf")} {fmt.date(asOfDate)}
      </p>
    </BentoCard>
  );
}
