"use client";

import { ArrowRight, Users } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import type { DashboardRecipient } from "@/lib/dashboard";
import { useLang, useLocalize } from "@/lib/i18n";
import { bankFromDashboard, type Bank } from "@/lib/nafiData";

type RecipientView = {
  id: string;
  name: string;
  nameAr: string;
  bank: Bank;
};

function rowY(index: number, total: number): number {
  return ((index + 1) / (total + 1)) * 100;
}

function RecipientBox({ r }: { r: RecipientView }) {
  const loc = useLocalize();
  const initials = r.name.split(" ")[0][0] + (r.name.split(" ")[1]?.[0] ?? "");
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-white/[0.06] bg-card-2 px-3 py-2">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary/70 to-purple/70 text-[11px] font-semibold text-white" dir="ltr">
        {initials}
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block truncate text-[13px] font-medium">{loc(r.name, r.nameAr)}</span>
      </span>
    </div>
  );
}

function BankNode({ r }: { r: RecipientView }) {
  const loc = useLocalize();
  return (
    <div className="flex flex-col items-center gap-1.5">
      <BankLogo bank={r.bank} size={40} />
      <span className="max-w-[6rem] truncate text-center text-[10px] text-muted-foreground">
        {loc(r.bank.name, r.bank.nameAr)}
      </span>
    </div>
  );
}

export function RecipientsGraphCard({
  recipients,
  className,
}: {
  recipients: DashboardRecipient[];
  className?: string;
}) {
  const { t } = useLang();
  const items: RecipientView[] = recipients.map((recipient) => ({
    id: recipient.id,
    name: recipient.name,
    nameAr: recipient.name_ar,
    bank: bankFromDashboard(recipient.bank),
  }));

  return (
    <BentoCard className={className}>
      <CardTitle title={t("favoriteRecipients")} />

      {items.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t("noRecipients")}</p>
      ) : (
        <>
      {/* Desktop node graph */}
      <div className="relative hidden h-[280px] sm:block">
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full rtl:-scale-x-100"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <g fill="none" stroke="#38466182" strokeWidth="1.4" vectorEffect="non-scaling-stroke">
            {items.map((recipient, index) => {
              const y = rowY(index, items.length);
              return (
                <g key={recipient.id}>
                  <path d={`M25 50 C 30 50 30 ${y} 33 ${y}`} />
                  <path d={`M67 ${y} L 83 ${y}`} />
                </g>
              );
            })}
          </g>
        </svg>

        {/* Quick Contacts (start side, centred) */}
        <div className="absolute top-1/2 w-[24%] -translate-y-1/2" style={{ insetInlineStart: 0 }}>
          <div className="flex flex-col items-center gap-2 rounded-xl border border-white/[0.06] bg-card-2 px-4 py-3">
            <span className="grid size-9 place-items-center rounded-full bg-primary/15 text-primary">
              <Users className="size-4" aria-hidden />
            </span>
            <span className="text-center text-[12px] font-medium leading-tight">{t("quickContacts")}</span>
          </div>
        </div>

        {/* Recipients (middle) */}
        {items.map((r, i) => (
          <div
            key={r.id}
            className="absolute w-[34%] -translate-y-1/2"
            style={{ insetInlineStart: "33%", top: `${rowY(i, items.length)}%` }}
          >
            <RecipientBox r={r} />
          </div>
        ))}

        {/* Arrows */}
        {items.map((r, i) => (
          <ArrowRight
            key={`a-${r.id}`}
            className="absolute size-4 -translate-y-1/2 text-faint rtl:-scale-x-100"
            style={{ insetInlineStart: "75%", top: `${rowY(i, items.length)}%` }}
            aria-hidden
          />
        ))}

        {/* Banks (end side) */}
        {items.map((r, i) => (
          <div key={`b-${r.id}`} className="absolute -translate-y-1/2" style={{ insetInlineEnd: 0, top: `${rowY(i, items.length)}%` }}>
            <BankNode r={r} />
          </div>
        ))}
      </div>

      {/* Mobile stacked fallback */}
      <div className="space-y-2.5 sm:hidden">
        {items.map((r) => (
          <div key={r.id} className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <RecipientBox r={r} />
            </div>
            <ArrowRight className="size-4 shrink-0 text-faint rtl:-scale-x-100" aria-hidden />
            <BankLogo bank={r.bank} size={36} />
          </div>
        ))}
      </div>
        </>
      )}
    </BentoCard>
  );
}
