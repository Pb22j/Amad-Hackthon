"use client";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { cn } from "@/lib/utils";
import { useFormat, useLang, useLocalize } from "@/lib/i18n";
import { portfolio } from "@/lib/nafiData";

/** Lightweight inline sparkline (no chart library). */
function Sparkline({ points, className }: { points: number[]; className?: string }) {
  const w = 100;
  const h = 32;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = w / (points.length - 1);
  const coords = points.map((p, i) => [i * step, h - ((p - min) / span) * (h - 4) - 2]);
  const line = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w} ${h} L0 ${h} Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={className} aria-hidden>
      <defs>
        <linearGradient id="pfFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--positive)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--positive)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#pfFill)" />
      <path d={line} fill="none" stroke="var(--positive)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function PortfolioCard({ className }: { className?: string }) {
  const { t } = useLang();
  const fmt = useFormat();
  const loc = useLocalize();

  return (
    <BentoCard className={className}>
      <CardTitle
        title={t("portfolio")}
        action={
          <span className="rounded-full bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            {t("privateIndex")}
          </span>
        }
      />

      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-3xl font-light tracking-tight tabular-nums" dir="ltr">
            {fmt.money(portfolio.value)}
          </p>
          <div className="mt-1.5 flex items-center gap-3 text-xs">
            <span className="text-positive" dir="ltr">
              {fmt.pct(portfolio.dayPercent)} · {t("today")}
            </span>
            <span className="text-muted-foreground" dir="ltr">
              {fmt.pct(portfolio.totalReturnPercent)} · {t("totalReturn")}
            </span>
          </div>
        </div>
        <Sparkline points={portfolio.spark} className="h-10 w-28 shrink-0" />
      </div>

      {/* Holdings */}
      <ul className="mt-5 space-y-1">
        {portfolio.holdings.map((hd) => {
          const up = hd.dayPercent >= 0;
          return (
            <li key={hd.ticker} className="flex items-center gap-3 border-t border-white/[0.05] py-2 text-[13px] first:border-t-0">
              <span className="w-12 shrink-0 font-mono text-[11px] text-muted-foreground" dir="ltr">
                {hd.ticker}
              </span>
              <span className="min-w-0 flex-1 truncate">{loc(hd.name, hd.nameAr)}</span>
              <span className="w-10 text-end font-mono text-[12px] tabular-nums text-muted-foreground" dir="ltr">
                {hd.weight}%
              </span>
              <span className={cn("w-14 text-end font-mono text-[12px] tabular-nums", up ? "text-positive" : "text-negative")} dir="ltr">
                {fmt.pct(hd.dayPercent)}
              </span>
            </li>
          );
        })}
      </ul>
    </BentoCard>
  );
}
