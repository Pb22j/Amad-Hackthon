import { Card, CardTitle, BankBadge } from "@/components/finance/primitives";
import { connectedBanks } from "@/lib/financeData";

export function ConnectedBanksCard({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <CardTitle ar="البنوك المرتبطة">Connected Banks</CardTitle>

      <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {connectedBanks.map((b) => (
          <div
            key={b.id}
            className="flex items-center gap-3 rounded-xl border border-border bg-surface-2 px-3 py-2.5 transition-colors hover:border-border-strong"
          >
            <BankBadge initials={b.initials} brand={b.brand} />
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 truncate text-[13px] font-medium text-foreground">
                {b.name}
                {b.count != null && (
                  <span className="font-mono text-[11px] text-muted-2">({b.count})</span>
                )}
              </p>
              {b.sub && <p className="truncate text-[11px] text-muted-2">{b.sub}</p>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
