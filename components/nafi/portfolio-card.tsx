"use client";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import type { DashboardPortfolio } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useFormat, useLang, useLocalize } from "@/lib/i18n";

export function PortfolioCard({
  data,
  className,
}: {
  data: DashboardPortfolio;
  className?: string;
}) {
  const { t } = useLang();
  const fmt = useFormat();
  const loc = useLocalize();

  return (
    <BentoCard className={className}>
      <CardTitle
        title={t("portfolio")}
        action={
          <span className="rounded-full bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            {fmt.num(data.holdings.length)} {t("holdings")}
          </span>
        }
      />

      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-3xl font-light tracking-tight tabular-nums" dir="ltr">
            {fmt.money(Number(data.value_sar))}
          </p>
          <div className="mt-1.5 text-xs">
            <span className={data.total_return_percent >= 0 ? "text-positive" : "text-negative"} dir="ltr">
              {fmt.pct(data.total_return_percent)} · {t("totalReturn")}
            </span>
          </div>
        </div>
      </div>

      {/* Holdings */}
      <ul className="mt-5 space-y-1">
        {data.holdings.map((hd) => {
          const up = hd.return_percent >= 0;
          return (
            <li key={hd.ticker} className="flex items-center gap-3 border-t border-white/[0.05] py-2 text-[13px] first:border-t-0">
              <span className="w-12 shrink-0 font-mono text-[11px] text-muted-foreground" dir="ltr">
                {hd.ticker}
              </span>
              <span className="min-w-0 flex-1 truncate">{loc(hd.name, hd.name_ar)}</span>
              <span className="w-10 text-end font-mono text-[12px] tabular-nums text-muted-foreground" dir="ltr">
                {hd.weight_percent}%
              </span>
              <span className={cn("w-14 text-end font-mono text-[12px] tabular-nums", up ? "text-positive" : "text-negative")} dir="ltr">
                {fmt.pct(hd.return_percent)}
              </span>
            </li>
          );
        })}
        {data.holdings.length === 0 ? (
          <li className="py-4 text-center text-sm text-muted-foreground">{t("noHoldings")}</li>
        ) : null}
      </ul>
    </BentoCard>
  );
}
