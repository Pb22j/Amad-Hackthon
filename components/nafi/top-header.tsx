"use client";

import { Bell } from "lucide-react";

import { BrandLogo } from "@/components/nafi/brand-logo";
import { LanguageToggle } from "@/components/i18n/language-toggle";
import { useLang } from "@/lib/i18n";
import { user } from "@/lib/nafiData";

export function TopHeader() {
  const { t, lang } = useLang();
  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <BrandLogo gradient className="h-7 w-9" />
        <span className="text-xl font-semibold tracking-tight">{lang === "ar" ? "نافع" : "Nafi"}</span>
      </div>

      <div className="flex items-center gap-2.5">
        <LanguageToggle />
        <button
          type="button"
          aria-label={t("notifications")}
          className="relative grid size-9 place-items-center rounded-full border border-white/10 bg-white/[0.03] text-muted-foreground transition-colors hover:text-foreground"
        >
          <Bell className="size-4" aria-hidden />
          <span className="absolute end-2 top-2 size-1.5 rounded-full bg-orange" />
        </button>
        <button
          type="button"
          aria-label={t("profile")}
          className="grid size-9 place-items-center rounded-full border border-white/10 bg-white/[0.03]"
        >
          <span className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-primary to-purple text-xs font-semibold text-white" dir="ltr">
            {user.initial}
          </span>
        </button>
      </div>
    </header>
  );
}
