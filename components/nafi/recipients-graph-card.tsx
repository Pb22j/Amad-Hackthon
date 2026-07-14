"use client";

import { ArrowRight, Users } from "lucide-react";

import { BentoCard, CardTitle } from "@/components/nafi/bento-card";
import { BankLogo } from "@/components/nafi/bank-logo";
import { useLang, useLocalize } from "@/lib/i18n";
import { contactsCount, recipients, type Recipient } from "@/lib/nafiData";

const ROW_Y = [16, 50, 84]; // vertical centres (%)

function RecipientBox({ r }: { r: Recipient }) {
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

function BankNode({ r }: { r: Recipient }) {
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

export function RecipientsGraphCard({ className }: { className?: string }) {
  const { t } = useLang();

  return (
    <BentoCard className={className}>
      <CardTitle title={t("favoriteRecipients")} tag={`[${contactsCount}]`} />

      {/* Desktop node graph */}
      <div className="relative hidden h-[280px] sm:block">
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full rtl:-scale-x-100"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          <g fill="none" stroke="#38466182" strokeWidth="1.4" vectorEffect="non-scaling-stroke">
            <path d="M25 50 C 30 50 30 16 33 16" />
            <path d="M25 50 L 33 50" />
            <path d="M25 50 C 30 50 30 84 33 84" />
            <path d="M67 16 L 83 16" />
            <path d="M67 50 L 83 50" />
            <path d="M67 84 L 83 84" />
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
        {recipients.map((r, i) => (
          <div
            key={r.id}
            className="absolute w-[34%] -translate-y-1/2"
            style={{ insetInlineStart: "33%", top: `${ROW_Y[i]}%` }}
          >
            <RecipientBox r={r} />
          </div>
        ))}

        {/* Arrows */}
        {recipients.map((r, i) => (
          <ArrowRight
            key={`a-${r.id}`}
            className="absolute size-4 -translate-y-1/2 text-faint rtl:-scale-x-100"
            style={{ insetInlineStart: "75%", top: `${ROW_Y[i]}%` }}
            aria-hidden
          />
        ))}

        {/* Banks (end side) */}
        {recipients.map((r, i) => (
          <div key={`b-${r.id}`} className="absolute -translate-y-1/2" style={{ insetInlineEnd: 0, top: `${ROW_Y[i]}%` }}>
            <BankNode r={r} />
          </div>
        ))}
      </div>

      {/* Mobile stacked fallback */}
      <div className="space-y-2.5 sm:hidden">
        {recipients.map((r) => (
          <div key={r.id} className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <RecipientBox r={r} />
            </div>
            <ArrowRight className="size-4 shrink-0 text-faint rtl:-scale-x-100" aria-hidden />
            <BankLogo bank={r.bank} size={36} />
          </div>
        ))}
      </div>
    </BentoCard>
  );
}
