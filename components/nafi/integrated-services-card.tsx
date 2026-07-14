"use client";

import { Plus } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import { useLang, useLocalize } from "@/lib/i18n";
import { integratedServices } from "@/lib/nafiData";

export function IntegratedServicesCard({ className }: { className?: string }) {
  const { t } = useLang();
  const loc = useLocalize();
  return (
    <BentoCard className={className}>
      <CardTitle
        title={t("integratedServices")}
        action={
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <Plus className="size-3.5" aria-hidden />
            {t("scanAll")}
          </button>
        }
      />
      <div className="flex flex-wrap gap-2.5">
        {integratedServices.map((bank) => (
          <div
            key={bank.id}
            className="inline-flex items-center gap-2.5 rounded-full border border-white/[0.06] bg-card-2 py-1.5 pe-4 ps-1.5"
          >
            <BankLogo bank={bank} size={30} className="rounded-full" />
            <span className="flex items-center gap-1.5 text-sm font-medium">
              {loc(bank.name, bank.nameAr)}
              <span className="font-mono text-xs text-muted-foreground" dir="ltr">
                ({bank.code})
              </span>
            </span>
          </div>
        ))}
      </div>
    </BentoCard>
  );
}
