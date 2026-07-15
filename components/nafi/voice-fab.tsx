"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";
import { useLang } from "@/lib/i18n";
import { BrandLogo } from "@/components/nafi/brand-logo";

/**
 * VoiceFAB — the persistent Nafi Voice entry point on the dashboard.
 * Fixed to the bottom-right corner; opens the voice-first chat.
 *
 * Idle state breathes: a soft halo inhales and exhales behind the button
 * rather than pinging, so it reads as alive and listening instead of alarming.
 */
export function VoiceFAB() {
  const { t } = useLang();

  return (
    <div className="group fixed bottom-6 right-6 z-50 flex items-center gap-3" dir="ltr">
      {/* Tooltip pill */}
      <span
        className={cn(
          "pointer-events-none rounded-full border border-white/10 bg-popover/80 px-3 py-1.5",
          "text-xs font-medium text-foreground shadow-lg backdrop-blur-md",
          "translate-x-1 opacity-0 transition-all duration-300 ease-out",
          "group-hover:translate-x-0 group-hover:opacity-100"
        )}
      >
        {t("askNafi")}
      </span>

      <Link
        href="/chat"
        aria-label={t("askNafi")}
        className={cn(
          "relative grid size-14 place-items-center rounded-full text-white",
          "bg-gradient-to-br from-primary to-purple",
          "shadow-[0_14px_40px_-8px_rgb(125_151_255/0.75),0_2px_10px_rgb(0_0_0/0.5)]",
          "ring-1 ring-white/20",
          "transition-transform duration-300 ease-out hover:scale-[1.07] active:scale-95",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        )}
      >
        {/* Breathing halo — blurred bloom, paused while hovered. */}
        <span
          aria-hidden
          className="absolute -inset-2 -z-10 animate-breathe rounded-full bg-primary/45 blur-xl group-hover:[animation-play-state:paused]"
        />
        {/* Inner sheen — light catching the top of the sphere. */}
        <span
          aria-hidden
          className="absolute inset-0 rounded-full bg-gradient-to-b from-white/25 to-transparent"
        />
        <BrandLogo className="relative h-5 w-7" aria-hidden />
      </Link>
    </div>
  );
}
