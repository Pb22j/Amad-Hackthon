"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import { useLang } from "@/lib/i18n";
import { BrandLogo } from "@/components/nafi/brand-logo";

const BARS = [0.4, 0.75, 1, 0.6, 0.85];

/**
 * VoiceFAB — the persistent Nafi Voice entry point.
 * Fixed to the bottom-right corner; stays visible while scrolling. Tapping (or
 * pressing Space) toggles listening, which reveals an animated equalizer.
 */
export function VoiceFAB() {
  const { t } = useLang();
  const [active, setActive] = React.useState(false);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.code !== "Space") return;
      const el = document.activeElement;
      if (
        el instanceof HTMLElement &&
        (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)
      )
        return;
      e.preventDefault();
      setActive((v) => !v);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="group fixed bottom-6 right-6 z-50 flex items-center gap-3" dir="ltr">
      {/* Tooltip / status pill */}
      <span
        className={cn(
          "pointer-events-none rounded-full border border-white/10 bg-popover px-3 py-1.5 text-xs font-medium shadow-lg transition-opacity duration-200",
          active ? "text-primary opacity-100" : "text-foreground opacity-0 group-hover:opacity-100"
        )}
      >
        {active ? t("listening") : t("askNafi")}
      </span>

      <button
        type="button"
        aria-pressed={active}
        aria-label={active ? t("listening") : t("askNafi")}
        onClick={() => setActive((v) => !v)}
        className={cn(
          "relative grid size-14 place-items-center rounded-full text-white",
          "bg-gradient-to-br from-primary to-purple",
          "shadow-[0_10px_30px_-8px_rgba(111,141,255,0.6),0_2px_8px_rgba(0,0,0,0.4)]",
          "transition-transform duration-200 hover:scale-105 active:scale-95",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        )}
      >
        {/* Soft breathing ring when idle */}
        {!active && (
          <span className="absolute inset-0 animate-ping rounded-full bg-primary/25 [animation-duration:2.6s]" aria-hidden />
        )}

        {active ? (
          <span className="flex h-5 items-end gap-[3px]" aria-hidden>
            {BARS.map((h, i) => (
              <span
                key={i}
                className="w-[3px] origin-bottom animate-eq rounded-full bg-white"
                style={{ height: `${h * 100}%`, animationDelay: `${i * 90}ms` }}
              />
            ))}
          </span>
        ) : (
          <BrandLogo className="relative h-5 w-7" aria-hidden />
        )}
      </button>
    </div>
  );
}
