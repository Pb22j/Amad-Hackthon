"use client";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import { useLang, useLocalize } from "@/lib/i18n";
import { connectedBanks, type Bank } from "@/lib/nafiData";

function BankRow({ bank }: { bank: Bank }) {
  const loc = useLocalize();
  return (
    <div className="flex items-center gap-3 rounded-xl border border-white/[0.05] bg-card-2 p-2.5">
      <BankLogo bank={bank} size={38} />
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 truncate text-sm font-medium">
          {loc(bank.name, bank.nameAr)}
          {bank.code && (
            <span className="font-mono text-xs text-muted-foreground" dir="ltr">
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

export function ConnectedBanksCard({ className }: { className?: string }) {
  const { t } = useLang();
  return (
    <BentoCard className={className}>
      <CardTitle title={t("connectedBanks")} />
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {connectedBanks.map((bank) => (
          <BankRow key={bank.id} bank={bank} />
        ))}
      </div>
    </BentoCard>
  );
}
