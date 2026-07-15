import { Plus } from "lucide-react";

import { Card, BankBadge } from "@/components/finance/primitives";
import { integratedServices } from "@/lib/financeData";

export function IntegratedServicesCard({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[17px] font-semibold tracking-tight text-foreground">
            Integrated Bank Services
          </h2>
          <p className="mt-0.5 text-xs text-muted-2">الخدمات المصرفية المدمجة</p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-border-strong hover:text-foreground"
        >
          <Plus className="size-3.5" aria-hidden />
          Scan all
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2.5">
        {integratedServices.map((b) => (
          <div
            key={b.id}
            className="inline-flex items-center gap-2.5 rounded-full border border-border bg-surface-2 py-1.5 pl-1.5 pr-4"
          >
            <BankBadge initials={b.initials} brand={b.brand} size="sm" />
            <span className="text-[13px] font-medium text-foreground">
              {b.name} <span className="font-mono text-[11px] text-muted-2">({b.count})</span>
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
