import { ArrowLeftRight, ArrowDownToLine, FileText, Smartphone } from "lucide-react";

import { Card, CardTitle, Cite } from "@/components/finance/primitives";
import { activity } from "@/lib/financeData";

const recentIcons = [ArrowLeftRight, ArrowDownToLine];
const upcomingIcons = { utilities: FileText, phone: Smartphone };

export function AccountActivityCard({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <CardTitle ar={activity.titleAr} cite={activity.cite}>
        Account Activity &amp; Payments
      </CardTitle>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Recent transactions — orange */}
        <div
          className="rounded-xl p-4"
          style={{ background: "linear-gradient(160deg, #e88a52, #cf6f38)" }}
        >
          <p className="text-[13px] font-semibold text-white">Recent Transactions</p>
          <ul className="mt-3 space-y-2.5">
            {activity.recent.map((t, i) => {
              const Icon = recentIcons[i] ?? ArrowLeftRight;
              return (
                <li key={t.label} className="flex items-center gap-2.5">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-white/20 text-white">
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="flex items-center gap-1.5 text-[12px] leading-tight text-white/95">
                    {t.label}
                    <Cite value={t.cite} />
                  </span>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Upcoming payments — violet */}
        <div
          className="rounded-xl p-4"
          style={{ background: "linear-gradient(160deg, #9a8cf0, #7266d6)" }}
        >
          <p className="text-[13px] font-semibold text-white">Upcoming Payments</p>
          <ul className="mt-3 space-y-2.5">
            {activity.upcoming.map((p) => {
              const Icon = upcomingIcons[p.icon];
              return (
                <li key={p.label} className="flex items-center gap-2.5">
                  <span className="grid size-6 shrink-0 place-items-center rounded-md bg-white/20 text-white">
                    <Icon className="size-3.5" aria-hidden />
                  </span>
                  <span className="text-[12px] text-white/95">{p.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {/* Metrics */}
      <dl className="mt-3 grid grid-cols-2 gap-2.5">
        {activity.metrics.map((m) => (
          <div key={m.label} className="rounded-xl border border-border bg-surface-2 px-3.5 py-2.5">
            <dt className="text-[11px] text-muted-2">{m.label}:</dt>
            <dd className="mt-0.5 text-base font-semibold tabular-nums text-foreground">{m.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
