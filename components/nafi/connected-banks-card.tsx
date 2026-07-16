"use client";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import type { DashboardAccount } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { useLang, useLocalize } from "@/lib/i18n";
import { bankFromDashboard, type Bank } from "@/lib/nafiData";

function BankRow({ bank }: { bank: Bank }) {
  const loc = useLocalize();
  return (
    <div
      className={cn(
        "group/bank flex shrink-0 items-center gap-3 rounded-xl p-2.5",
        "border border-white/[0.07] bg-white/[0.045]",
        "transition-[background-color,border-color,transform] duration-300 ease-out",
        "hover:-translate-y-px hover:border-white/[0.16] hover:bg-white/[0.09]"
      )}
    >
      <BankLogo
        bank={bank}
        size={38}
        className="transition-transform duration-300 ease-out group-hover/bank:scale-[1.06]"
      />
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 truncate text-sm font-medium tracking-[-0.005em]">
          {loc(bank.name, bank.nameAr)}
          {bank.code && (
            <span className="font-mono text-[11px] text-faint" dir="ltr">
              ({bank.code})
            </span>
          )}
        </p>
        <p className="truncate text-[11px] text-muted-foreground">
          {loc(bank.sub ?? bank.name, bank.subAr ?? bank.nameAr)}
        </p>
      </div>
    </div>
  );
}

export function ConnectedBanksCard({
  accounts,
  className,
}: {
  accounts: DashboardAccount[];
  className?: string;
}) {
  const { t } = useLang();
  return (
    <BentoCard className={cn("flex flex-col", className)}>
      <CardTitle title={t("connectedBanks")} />

      {/*
       * The bank list scrolls inside a fixed-height card rather than growing it.
       * At `lg` the scroller is absolutely positioned, so it contributes no
       * intrinsic height and the grid row is sized by the neighbouring card —
       * the two stay level however many banks are connected. `min-h` is the
       * floor that keeps the card from collapsing if it ever loses that
       * neighbour. Below `lg` the cards stack, so it flows normally.
       */}
      <div className="relative min-h-0 flex-1 lg:min-h-[13.5rem]">
        <div className="no-scrollbar overflow-y-auto overscroll-contain scroll-smooth lg:absolute lg:inset-0">
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-1">
            {accounts.map((account) => (
              <BankRow
                key={account.id}
                bank={bankFromDashboard(
                  account,
                  `${account.account_type} · ${account.masked_account_number}`
                )}
              />
            ))}
            {accounts.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                {t("noAccounts")}
              </p>
            ) : null}
          </div>
        </div>

        {/*
         * Bottom fade — signals "more below" without a scrollbar. Must be a
         * translucent black rather than a fixed hex: the card is glass, so the
         * colour behind this strip changes with the ambient field beneath it.
         */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 hidden h-12 bg-gradient-to-t from-black/35 via-black/12 to-transparent lg:block"
        />
      </div>
    </BentoCard>
  );
}
