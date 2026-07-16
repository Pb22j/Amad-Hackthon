"use client";

import { WalletCards } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { WalletDepositButton } from "@/components/nafi/wallet-deposit-button";
import type { DashboardAccount, DashboardWallet } from "@/lib/dashboard";
import { useFormat, useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function NafiWalletCard({
  wallet,
  accounts,
  className,
}: {
  wallet: DashboardWallet;
  accounts: DashboardAccount[];
  className?: string;
}) {
  const { t } = useLang();
  const fmt = useFormat();

  return (
    <BentoCard className={cn("flex min-h-56 flex-col", className)}>
      <div
        aria-hidden
        className="pointer-events-none absolute -end-20 -top-24 -z-10 size-64 rounded-full bg-primary/20 blur-[75px]"
      />
      <CardTitle
        title={t("nafiWalletBalance")}
        action={
          <span className="grid size-9 place-items-center rounded-xl bg-primary/15 text-primary">
            <WalletCards className="size-4" aria-hidden />
          </span>
        }
      />
      <p
        className="numeral mt-2 bg-gradient-to-b from-white to-slate-300 bg-clip-text text-4xl font-light text-transparent sm:text-5xl"
        dir="ltr"
      >
        {fmt.money(Number(wallet.balance_sar))}
      </p>
      <div className="mt-auto pt-8">
        <WalletDepositButton wallet={wallet} accounts={accounts} />
      </div>
    </BentoCard>
  );
}
