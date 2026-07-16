import { Bell } from "lucide-react";

import { NafiLogo } from "@/components/finance/primitives";

export function BrandHeader() {
  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <NafiLogo className="h-7 w-9" />
        <span className="flex items-baseline gap-1.5">
          <span className="text-xl font-semibold tracking-tight text-foreground">Nafi</span>
          <span className="text-lg text-violet/90">نافع</span>
        </span>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-label="Notifications"
          className="relative grid size-9 place-items-center rounded-full border border-border bg-surface text-muted transition-colors hover:text-foreground"
        >
          <Bell className="size-[18px]" aria-hidden />
          <span className="absolute right-2 top-2 size-1.5 rounded-full bg-orange" />
        </button>
        <button
          type="button"
          aria-label="Profile"
          className="size-9 overflow-hidden rounded-full ring-1 ring-border-strong"
        >
          <span
            className="block size-full"
            style={{
              background:
                "radial-gradient(circle at 30% 30%, #7b74f0, #4a56c7 55%, #2a2f52)",
            }}
          />
        </button>
      </div>
    </header>
  );
}
