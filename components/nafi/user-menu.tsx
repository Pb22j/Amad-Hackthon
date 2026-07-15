"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useLang, useLocalize } from "@/lib/i18n";
import { user } from "@/lib/nafiData";

/**
 * Profile avatar with a small popover menu. Holds the sign-out action.
 * Closes on outside click, on Escape, and after signing out.
 */
export function UserMenu() {
  const { t } = useLang();
  const loc = useLocalize();
  const { signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;

    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function handleSignOut() {
    setOpen(false);
    signOut();
    router.replace("/");
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={t("profile")}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "grid size-9 place-items-center rounded-full border bg-white/[0.03] transition-colors",
          open ? "border-primary/50" : "border-white/10"
        )}
      >
        <span
          className="grid size-7 place-items-center rounded-full bg-gradient-to-br from-primary to-purple text-xs font-semibold text-white"
          dir="ltr"
        >
          {user.initial}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          aria-label={t("profile")}
          className="absolute end-0 top-11 z-50 w-56 overflow-hidden rounded-2xl border border-white/[0.06] bg-popover shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04),0_18px_40px_-16px_rgb(0_0_0/0.9)]"
        >
          <div className="border-b border-white/[0.06] px-4 py-3">
            <p className="truncate text-sm font-medium">{loc(user.name, user.nameAr)}</p>
            <p className="mt-0.5 truncate text-[11px] text-faint">{t("signedIn")}</p>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={handleSignOut}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-start text-sm text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground"
          >
            <LogOut className="size-4 shrink-0 rtl:-scale-x-100" aria-hidden />
            {t("signOut")}
          </button>
        </div>
      )}
    </div>
  );
}
