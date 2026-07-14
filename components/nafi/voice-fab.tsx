"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";
import { useLang } from "@/lib/i18n";
import { BrandLogo } from "@/components/nafi/brand-logo";

/**
 * VoiceFAB — the persistent Nafi Voice entry point on the dashboard.
 * Fixed to the bottom-right corner; opens the voice-first chat.
 */
export function VoiceFAB() {
  const { t } = useLang();

  return (
    <div className="group fixed bottom-6 right-6 z-50 flex items-center gap-3" dir="ltr">
      {/* Tooltip pill */}
      <span className="pointer-events-none rounded-full border border-white/10 bg-popover px-3 py-1.5 text-xs font-medium text-foreground opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
        {t("askNafi")}
      </span>

      <Link
        href="/chat"
        aria-label={t("askNafi")}
        className={cn(
          "relative grid size-14 place-items-center rounded-full text-white",
          "bg-gradient-to-br from-primary to-purple",
          "shadow-[0_10px_30px_-8px_rgba(111,141,255,0.6),0_2px_8px_rgba(0,0,0,0.4)]",
          "transition-transform duration-200 hover:scale-105 active:scale-95",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        )}
      >
        {/* Soft breathing ring */}
        <span className="absolute inset-0 animate-ping rounded-full bg-primary/25 [animation-duration:2.6s]" aria-hidden />
        <BrandLogo className="relative h-5 w-7" aria-hidden />
      </Link>
    </div>
  );
}
