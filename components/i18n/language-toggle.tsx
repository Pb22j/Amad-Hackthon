"use client";

import { cn } from "@/lib/utils";
import { useLang } from "@/lib/i18n";

/** Clean EN / ع segmented toggle. */
export function LanguageToggle() {
  const { lang, setLang, t } = useLang();
  return (
    <div
      className="flex items-center rounded-full border border-white/10 bg-white/[0.03] p-0.5 text-xs font-medium"
      role="group"
      aria-label={t("language")}
      dir="ltr"
    >
      <button
        type="button"
        onClick={() => setLang("en")}
        aria-pressed={lang === "en"}
        className={cn(
          "rounded-full px-2.5 py-1 transition-colors",
          lang === "en" ? "bg-white/10 text-foreground" : "text-muted-foreground hover:text-foreground"
        )}
      >
        EN
      </button>
      <button
        type="button"
        onClick={() => setLang("ar")}
        aria-pressed={lang === "ar"}
        className={cn(
          "rounded-full px-2.5 py-1 transition-colors",
          lang === "ar" ? "bg-white/10 text-foreground" : "text-muted-foreground hover:text-foreground"
        )}
      >
        ع
      </button>
    </div>
  );
}
