import { Card, Cite } from "@/components/finance/primitives";
import { netWorth } from "@/lib/financeData";

export function NetWorthCard({ className }: { className?: string }) {
  return (
    <Card className={`relative overflow-hidden ${className ?? ""}`}>
      {/* Ambient indigo/violet glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full blur-2xl"
        style={{ background: "radial-gradient(circle, rgba(109,106,246,0.28), transparent 65%)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-24 left-10 size-60 rounded-full blur-2xl"
        style={{ background: "radial-gradient(circle, rgba(154,140,240,0.16), transparent 65%)" }}
      />

      <div className="relative flex h-full flex-col">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium text-foreground">Your Net Worth</h2>
          <span className="text-sm text-muted-2">صافي ثروتك</span>
        </div>

        <p className="mt-6 bg-gradient-to-b from-white to-white/55 bg-clip-text text-[54px] font-thin leading-none tracking-tight text-transparent tabular-nums sm:text-6xl">
          ${netWorth.amount.toLocaleString("en-US")}
        </p>

        <p className="mt-5 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          {netWorth.label}
          <Cite value={netWorth.cite} />
        </p>
      </div>
    </Card>
  );
}
